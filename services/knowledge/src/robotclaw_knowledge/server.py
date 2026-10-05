"""HTTP entry point for the RobotClaw knowledge service."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .retrieval import KnowledgeIndex


class KnowledgeHandler(BaseHTTPRequestHandler):
	index: KnowledgeIndex
	embed_query: Any = None

	def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
		body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)

	def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
		if self.path != "/health":
			self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
			return
		self._json(
			HTTPStatus.OK,
			{
				"ok": True,
				"records": len(self.index.records),
				"index": str(self.index.index_file),
				"embedding_signature": self.index.signature,
				"retrieval": "hybrid" if self.embed_query else "lexical",
			},
		)

	def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
		if self.path != "/retrieve":
			self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
			return
		try:
			length = int(self.headers.get("Content-Length") or "0")
			if length <= 0 or length > 64 * 1024:
				raise ValueError("invalid request size")
			payload = json.loads(self.rfile.read(length).decode("utf-8"))
			query = str(payload.get("query") or "").strip()
			if not query:
				raise ValueError("query is required")
			top_k = int(payload.get("top_k") or 3)
			query_embedding = self.embed_query(query) if self.embed_query else None
			hits = self.index.search(query, top_k=top_k, query_embedding=query_embedding)
			self._json(HTTPStatus.OK, {"query": query, "hits": [hit.to_dict() for hit in hits]})
		except (ValueError, TypeError, json.JSONDecodeError) as error:
			self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

	def log_message(self, message: str, *args: object) -> None:
		print(f"[knowledge] {self.address_string()} {message % args}")


def main() -> None:
	parser = argparse.ArgumentParser(description="RobotClaw knowledge retrieval service")
	parser.add_argument("--host", default="127.0.0.1")
	parser.add_argument("--port", type=int, default=8790)
	parser.add_argument("--index", type=Path, default=Path("data/vectorstore/index.json"))
	args = parser.parse_args()

	index = KnowledgeIndex(args.index.resolve())
	KnowledgeHandler.index = index
	try:
		from sentence_transformers import SentenceTransformer

		model_name = str(index.signature.get("model") or "BAAI/bge-small-zh-v1.5")
		model = SentenceTransformer(model_name)
		KnowledgeHandler.embed_query = staticmethod(
			lambda query: model.encode([query], normalize_embeddings=True)[0].tolist()
		)
		print(f"[knowledge] vector retrieval enabled with {model_name}", flush=True)
	except (ImportError, OSError, RuntimeError) as error:
		KnowledgeHandler.embed_query = None
		print(f"[knowledge] vector model unavailable; lexical fallback active: {error}", flush=True)
	server = ThreadingHTTPServer((args.host, args.port), KnowledgeHandler)
	print(f"[knowledge] loaded {len(index.records)} records from {index.index_file}", flush=True)
	print(f"[knowledge] listening on http://{args.host}:{args.port}", flush=True)
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		pass
	finally:
		server.server_close()


if __name__ == "__main__":
	main()
