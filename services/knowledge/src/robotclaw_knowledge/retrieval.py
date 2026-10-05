"""Lightweight hybrid retrieval over RobotClaw's existing JSON index.

The service searches the chunks stored in index.json and returns only a small
set of relevant snippets. When the Python runtime has the configured embedding
model available, BM25-style lexical scoring is fused with vector similarity;
otherwise the same HTTP boundary falls back to lexical retrieval.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ASCII_WORD = re.compile(r"[a-z0-9_./:-]+")
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")


def _normalize(text: str) -> str:
	return unicodedata.normalize("NFKC", text).lower()


def tokenize(text: str) -> list[str]:
	"""Tokenize English identifiers and Chinese text without third-party libs."""
	text = _normalize(text)
	tokens = _ASCII_WORD.findall(text)
	for run in _CJK_RUN.findall(text):
		if len(run) == 1:
			tokens.append(run)
			continue
		# Bigrams retain Chinese word-like signals; trigrams improve precision for
		# interface names and fault phrases such as “电池信息”.
		tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
		if len(run) >= 3:
			tokens.extend(run[i : i + 3] for i in range(len(run) - 2))
	return tokens


@dataclass(frozen=True)
class Hit:
	content: str
	filename: str
	section: str
	score: float
	chunk_id: int | None
	lexical_score: float
	vector_score: float | None

	def to_dict(self) -> dict[str, Any]:
		return {
			"content": self.content,
			"filename": self.filename,
			"section": self.section,
			"score": round(self.score, 4),
			"chunk_id": self.chunk_id,
			"lexical_score": round(self.lexical_score, 4),
			"vector_score": None if self.vector_score is None else round(self.vector_score, 4),
		}


class KnowledgeIndex:
	def __init__(self, index_file: Path) -> None:
		self.index_file = index_file
		payload = json.loads(index_file.read_text(encoding="utf-8"))
		records = payload.get("records")
		if not isinstance(records, list):
			raise ValueError("knowledge index must contain a records array")

		self.signature = payload.get("embedding_signature") or {}
		self.records: list[dict[str, Any]] = []
		self.term_counts: list[Counter[str]] = []
		self.lengths: list[int] = []
		self.embeddings: list[list[float] | None] = []
		document_frequency: Counter[str] = Counter()

		for raw in records:
			if not isinstance(raw, dict):
				continue
			content = str(raw.get("page_content") or "").strip()
			if not content:
				continue
			metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
			filename = str(metadata.get("filename") or Path(str(metadata.get("source") or "unknown")).name)
			section = str(metadata.get("section_title") or metadata.get("parent_title") or "")
			search_text = f"{filename}\n{section}\n{content}"
			counts = Counter(tokenize(search_text))
			self.records.append({"content": content, "metadata": metadata, "filename": filename, "section": section})
			self.term_counts.append(counts)
			self.lengths.append(sum(counts.values()))
			embedding = raw.get("embedding")
			self.embeddings.append(
				[float(value) for value in embedding]
				if isinstance(embedding, list) and embedding and all(isinstance(value, (int, float)) for value in embedding)
				else None
			)
			document_frequency.update(counts.keys())

		self.avg_length = sum(self.lengths) / max(1, len(self.lengths))
		count = max(1, len(self.records))
		self.idf = {
			term: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
			for term, frequency in document_frequency.items()
		}

	def search(
		self,
		query: str,
		top_k: int = 3,
		min_score: float = 1.5,
		query_embedding: list[float] | None = None,
	) -> list[Hit]:
		query_tokens = list(dict.fromkeys(tokenize(query)))
		if not query_tokens:
			return []

		query_normalized = _normalize(query).strip()
		lexical_scores: list[float] = []
		k1 = 1.5
		b = 0.75

		for index, record in enumerate(self.records):
			counts = self.term_counts[index]
			length = self.lengths[index]
			score = 0.0
			for term in query_tokens:
				frequency = counts.get(term, 0)
				if not frequency:
					continue
				denominator = frequency + k1 * (1.0 - b + b * length / max(1.0, self.avg_length))
				score += self.idf.get(term, 0.0) * (frequency * (k1 + 1.0)) / denominator

			metadata_text = _normalize(f"{record['filename']} {record['section']}")
			for term in query_tokens:
				if term in metadata_text:
					score += self.idf.get(term, 0.0) * 0.8
			if len(query_normalized) >= 3 and query_normalized in _normalize(record["content"]):
				score += 5.0

			lexical_scores.append(score)

		vector_scores: list[float | None] = [None] * len(self.records)
		if query_embedding:
			query_norm = math.sqrt(sum(value * value for value in query_embedding))
			if query_norm > 0:
				for index, embedding in enumerate(self.embeddings):
					if embedding is None or len(embedding) != len(query_embedding):
						continue
					doc_norm = math.sqrt(sum(value * value for value in embedding))
					if doc_norm == 0:
						continue
					vector_scores[index] = sum(a * b for a, b in zip(query_embedding, embedding)) / (query_norm * doc_norm)

		# Reciprocal-rank fusion keeps incomparable BM25 and cosine scales stable.
		lexical_order = sorted(range(len(self.records)), key=lambda i: lexical_scores[i], reverse=True)
		lexical_rank = {index: rank for rank, index in enumerate(lexical_order, start=1)}
		vector_order = sorted(
			(index for index, score in enumerate(vector_scores) if score is not None),
			key=lambda i: vector_scores[i] or -1.0,
			reverse=True,
		)
		vector_rank = {index: rank for rank, index in enumerate(vector_order, start=1)}

		results: list[Hit] = []
		for index, record in enumerate(self.records):
			lexical_score = lexical_scores[index]
			vector_score = vector_scores[index]
			if lexical_score < min_score and (vector_score is None or vector_score < 0.45):
				continue
			if vector_rank:
				score = 0.45 / (60 + lexical_rank[index]) + 0.55 / (60 + vector_rank.get(index, len(self.records) + 1))
			else:
				score = lexical_score
			metadata = record["metadata"]
			chunk_id = metadata.get("chunk_id")
			results.append(
				Hit(
					content=record["content"],
					filename=record["filename"],
					section=record["section"],
					score=score,
					chunk_id=chunk_id if isinstance(chunk_id, int) else None,
					lexical_score=lexical_score,
					vector_score=vector_score,
				)
			)

		results.sort(key=lambda hit: hit.score, reverse=True)
		return results[: max(1, min(top_k, 10))]
