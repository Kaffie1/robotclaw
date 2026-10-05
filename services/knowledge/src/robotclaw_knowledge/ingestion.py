"""Document loading, chunking and index building for RobotClaw knowledge.

This keeps the indexing pipeline inside the new knowledge service instead of
reviving the old monolithic backend. It intentionally supports the formats that
RobotClaw currently stores in data/knowledge: Markdown and plain text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SUPPORTED_SUFFIXES = {".md", ".txt"}
DEFAULT_CHUNK_SIZE = 1800
DEFAULT_CHUNK_OVERLAP = 180
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
FENCED_CODE_PATTERN = re.compile(r"^(```|~~~)")


@dataclass
class KnowledgeDocument:
	page_content: str
	metadata: dict[str, Any]


def _hash_text(text: str) -> str:
	return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _is_fenced_code_line(line: str) -> bool:
	return bool(FENCED_CODE_PATTERN.match(line.strip()))


def _parse_heading(line: str) -> tuple[int, str] | None:
	match = HEADING_PATTERN.match(line.strip())
	if not match:
		return None
	return len(match.group(1)), match.group(2).strip()


def _iter_headings(text: str) -> Iterable[tuple[int, str]]:
	in_code = False
	for line in text.splitlines():
		if _is_fenced_code_line(line):
			in_code = not in_code
			continue
		if in_code:
			continue
		parsed = _parse_heading(line)
		if parsed:
			yield parsed


def load_document(path: Path, *, source_root: Path | None = None) -> KnowledgeDocument:
	suffix = path.suffix.lower()
	if suffix not in SUPPORTED_SUFFIXES:
		raise ValueError(f"unsupported knowledge file type: {path}")
	text = path.read_text(encoding="utf-8").strip()
	relative_name = path.name if source_root is None else path.relative_to(source_root).as_posix()
	return KnowledgeDocument(
		page_content=text,
		metadata={
			"source": str(path),
			"filename": relative_name,
			"filetype": suffix.removeprefix("."),
			"doc_id": _hash_text(f"{relative_name}\n{text}"),
		},
	)


def load_documents(source_dir: Path) -> list[KnowledgeDocument]:
	root = source_dir.resolve()
	documents: list[KnowledgeDocument] = []
	for path in sorted(root.rglob("*")):
		if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
			documents.append(load_document(path, source_root=root))
	return documents


def choose_section_heading_level(document: KnowledgeDocument) -> int | None:
	levels = {level for level, _ in _iter_headings(document.page_content)}
	if 1 in levels:
		return 1
	if 2 in levels:
		return 2
	return None


def split_document_by_heading_level(document: KnowledgeDocument, selected_level: int | None) -> list[KnowledgeDocument]:
	if selected_level is None:
		metadata = dict(document.metadata)
		metadata["selected_heading_level"] = None
		return [KnowledgeDocument(document.page_content, metadata)]

	sections: list[KnowledgeDocument] = []
	preamble: list[str] = []
	current: list[str] = []
	current_title: str | None = None
	current_parent: str | None = None
	active_parent: str | None = None
	started = False
	in_code = False

	def flush() -> None:
		nonlocal current, current_title, current_parent
		content = "\n".join(current).strip()
		if content:
			metadata = dict(document.metadata)
			metadata["selected_heading_level"] = selected_level
			metadata["section_title"] = current_title
			if current_parent:
				metadata["parent_title"] = current_parent
			else:
				metadata.pop("parent_title", None)
			sections.append(KnowledgeDocument(content, metadata))
		current = []
		current_title = None
		current_parent = None

	for line in document.page_content.splitlines():
		if _is_fenced_code_line(line):
			in_code = not in_code
			parsed = None
		elif in_code:
			parsed = None
		else:
			parsed = _parse_heading(line)

		if parsed:
			level, title = parsed
			if level == 1:
				active_parent = title
			if level == selected_level:
				if started:
					flush()
				started = True
				current_title = title
				current_parent = active_parent if selected_level > 1 else None
				current = []
				if preamble:
					current.extend(preamble)
					preamble = []
				current.append(line)
				continue

		if started:
			current.append(line)
		else:
			preamble.append(line)

	if started:
		flush()
	else:
		metadata = dict(document.metadata)
		metadata["selected_heading_level"] = None
		metadata.pop("parent_title", None)
		metadata.pop("section_title", None)
		return [KnowledgeDocument(document.page_content, metadata)]

	return sections


def _char_split(document: KnowledgeDocument, *, chunk_size: int, chunk_overlap: int) -> list[KnowledgeDocument]:
	text = document.page_content.strip()
	if len(text) <= chunk_size:
		return [document]
	chunks: list[KnowledgeDocument] = []
	start = 0
	while start < len(text):
		end = min(len(text), start + chunk_size)
		if end < len(text):
			for sep in ("\n\n", "\n", "。", ".", " "):
				pos = text.rfind(sep, start, end)
				if pos > start + chunk_size // 2:
					end = pos + len(sep)
					break
		content = text[start:end].strip()
		if content:
			chunks.append(KnowledgeDocument(content, dict(document.metadata)))
		if end >= len(text):
			break
		start = max(end - chunk_overlap, start + 1)
	return chunks


def _pack_sections(sections: list[KnowledgeDocument], *, chunk_size: int, chunk_overlap: int) -> list[KnowledgeDocument]:
	out: list[KnowledgeDocument] = []
	pending: list[KnowledgeDocument] = []
	pending_len = 0

	def flush() -> None:
		nonlocal pending, pending_len
		if not pending:
			return
		content = "\n\n".join(section.page_content.strip() for section in pending if section.page_content.strip()).strip()
		metadata = dict(pending[0].metadata)
		identity = (
			metadata.get("selected_heading_level"),
			metadata.get("parent_title"),
			metadata.get("section_title"),
		)
		if any(
			(
				section.metadata.get("selected_heading_level"),
				section.metadata.get("parent_title"),
				section.metadata.get("section_title"),
			)
			!= identity
			for section in pending[1:]
		):
			metadata["selected_heading_level"] = None
			metadata.pop("parent_title", None)
			metadata.pop("section_title", None)
		out.append(KnowledgeDocument(content, metadata))
		pending = []
		pending_len = 0

	for section in sections:
		content = section.page_content.strip()
		if not content:
			continue
		if len(content) > chunk_size:
			flush()
			out.extend(split_document(section, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
			continue
		extra = len(content) + (2 if pending else 0)
		if pending and pending_len + extra > chunk_size:
			flush()
		pending.append(section)
		pending_len += extra
	flush()
	return out


def split_document(
	document: KnowledgeDocument,
	*,
	chunk_size: int = DEFAULT_CHUNK_SIZE,
	chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[KnowledgeDocument]:
	if len(document.page_content.strip()) <= chunk_size:
		return [document]

	current_level = document.metadata.get("selected_heading_level")
	if isinstance(current_level, int) and current_level >= 4:
		return _char_split(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
	selected_level = current_level + 1 if isinstance(current_level, int) else choose_section_heading_level(document)
	if selected_level is None:
		return _char_split(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

	sections = split_document_by_heading_level(document, selected_level)
	downgraded: list[KnowledgeDocument] = []
	for section in sections:
		if len(section.page_content.strip()) <= chunk_size:
			downgraded.append(section)
			continue
		level = section.metadata.get("selected_heading_level")
		if isinstance(level, int) and level < 4:
			child_sections = split_document_by_heading_level(section, level + 1)
			has_child = any(child.metadata.get("section_title") for child in child_sections)
			if has_child:
				downgraded.extend(_pack_sections(child_sections, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
				continue
		downgraded.extend(_char_split(section, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
	return _pack_sections(downgraded, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def split_documents(
	documents: list[KnowledgeDocument],
	*,
	chunk_size: int = DEFAULT_CHUNK_SIZE,
	chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[KnowledgeDocument]:
	chunks: list[KnowledgeDocument] = []
	for document in documents:
		chunks.extend(split_document(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
	for index, chunk in enumerate(chunks):
		chunk.metadata["chunk_id"] = index
	return chunks


def build_index_payload(
	chunks: list[KnowledgeDocument],
	*,
	embedding_model: str = DEFAULT_EMBEDDING_MODEL,
	embed: bool = True,
	require_embeddings: bool = False,
) -> dict[str, Any]:
	records = [{"page_content": chunk.page_content, "metadata": chunk.metadata} for chunk in chunks]
	signature: dict[str, str] = {}
	if embed:
		try:
			from sentence_transformers import SentenceTransformer

			model = SentenceTransformer(embedding_model)
			vectors = model.encode(
				[record["page_content"] for record in records],
				normalize_embeddings=True,
				show_progress_bar=False,
			)
			for record, vector in zip(records, vectors):
				record["embedding"] = vector.tolist()
			signature = {"provider": "huggingface", "model": embedding_model, "base_url": ""}
		except (ImportError, OSError, RuntimeError) as error:
			if require_embeddings:
				raise RuntimeError(f"embedding model unavailable: {error}") from error
			print(f"[knowledge] embeddings skipped; lexical index will be built: {error}")
	return {"embedding_signature": signature, "records": records}


def rebuild_index(
	source_dir: Path,
	index_file: Path,
	*,
	chunk_size: int = DEFAULT_CHUNK_SIZE,
	chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
	embedding_model: str = DEFAULT_EMBEDDING_MODEL,
	embed: bool = True,
	require_embeddings: bool = False,
) -> dict[str, Any]:
	documents = load_documents(source_dir)
	chunks = split_documents(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
	payload = build_index_payload(
		chunks,
		embedding_model=embedding_model,
		embed=embed,
		require_embeddings=require_embeddings,
	)
	index_file.parent.mkdir(parents=True, exist_ok=True)
	index_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
	return {
		"source_dir": str(source_dir),
		"index_file": str(index_file),
		"documents": len(documents),
		"chunks": len(chunks),
		"embedded": bool(payload.get("embedding_signature")),
	}


def preview_file(path: Path, *, chunk_size: int, chunk_overlap: int) -> dict[str, Any]:
	document = load_document(path)
	chunks = split_documents([document], chunk_size=chunk_size, chunk_overlap=chunk_overlap)
	return {
		"file": str(path),
		"chunks": [
			{
				"chunk_id": chunk.metadata.get("chunk_id"),
				"filename": chunk.metadata.get("filename"),
				"section_title": chunk.metadata.get("section_title"),
				"parent_title": chunk.metadata.get("parent_title"),
				"length": len(chunk.page_content),
				"preview": chunk.page_content[:240],
			}
			for chunk in chunks
		],
	}


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="RobotClaw knowledge document chunking and index builder")
	subparsers = parser.add_subparsers(dest="command", required=True)

	preview = subparsers.add_parser("preview", help="preview chunking for one md/txt file")
	preview.add_argument("file", type=Path)
	preview.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
	preview.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)

	rebuild = subparsers.add_parser("rebuild", help="rebuild data/vectorstore/index.json from data/knowledge")
	rebuild.add_argument("--source", type=Path, default=Path("data/knowledge"))
	rebuild.add_argument("--index", type=Path, default=Path("data/vectorstore/index.json"))
	rebuild.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
	rebuild.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
	rebuild.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
	rebuild.add_argument("--no-embed", action="store_true", help="build lexical-only index")
	rebuild.add_argument("--require-embeddings", action="store_true", help="fail if embedding model cannot be loaded")
	return parser


def main() -> None:
	parser = build_parser()
	args = parser.parse_args()
	if args.command == "preview":
		payload = preview_file(args.file, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
	else:
		payload = rebuild_index(
			args.source,
			args.index,
			chunk_size=args.chunk_size,
			chunk_overlap=args.chunk_overlap,
			embedding_model=args.embedding_model,
			embed=not args.no_embed,
			require_embeddings=args.require_embeddings,
		)
	print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
