# Knowledge service

Python RAG retrieval service for RobotClaw. It loads the existing `data/vectorstore/index.json` and exposes:

- `GET /health`
- `POST /retrieve` with `{ "query": "…", "top_k": 3 }`

The current implementation is selective hybrid retrieval, not full-index prompt injection. It embeds the user query with the index model when available, combines vector similarity with BM25-style lexical scoring, and returns only the requested top snippets. If the embedding runtime is unavailable, the service keeps the same API and falls back to lexical retrieval.

The gateway defaults to `top_k = 3` and caps each injected snippet at 1500 characters.

## Chunking and Indexing

Document chunking is part of this service. Markdown and txt files under `data/knowledge` can be split into retrieval chunks and rebuilt into `data/vectorstore/index.json`.

```bash
npm run knowledge:preview -- "data/knowledge/new/chassis接口(1.5.0).md"
npm run knowledge:rebuild
```

The chunker preserves Markdown heading metadata (`section_title`, `parent_title`, `selected_heading_level`) and assigns `chunk_id` values compatible with the retrieval service. Rebuilds try to embed chunks with `BAAI/bge-small-zh-v1.5`; if the embedding runtime is unavailable, the CLI can still build a lexical-only index. Use `-- --no-embed` for an explicit lexical-only rebuild.
