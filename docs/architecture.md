# RobotClaw architecture

RobotClaw uses a thin TypeScript gateway around Pi and keeps robot-domain work in Python services.

```text
apps/web
   │ WebSocket
   ▼
apps/gateway ─── npm: @earendil-works/pi-ai
   │             npm: @earendil-works/pi-agent-core
   │             npm: @earendil-works/pi-coding-agent
   │ HTTP/RPC
   ├──────────► services/knowledge   (Python, automatic RAG)
   └──────────► services/robot       (Python, later: ROS/recovery)
```

## Responsibilities

### Web

Owns rendering, interaction and the WebSocket client. It does not hold provider secrets or execute robot operations.

### Gateway

Owns Pi agent sessions, model configuration, context compaction, streaming events and browser protocol adaptation. It should remain a thin integration layer instead of accumulating robot business logic.

### Knowledge service

Owns retrieval and source metadata. The Gateway calls it automatically before each normal user prompt and injects the results as hidden context; RAG is not exposed as an agent tool. The current implementation reads the existing JSON index, uses vector + lexical hybrid retrieval when the embedding model is available, and falls back to lexical retrieval when it is not.

The gateway injects only a bounded set of snippets into the active request: by default Top 3 hits, with each snippet capped before it reaches Pi. It does not use this service as long-term memory.

### Robot service

Will own ROS adapters and recovery workflows. Every mutating operation will require validation, timeout, audit information and an explicit approval policy.

### Protocol

Cross-process request and response schemas belong in `packages/protocol/`. The existing browser wire protocol remains in the gateway until it is extracted without breaking the imported UI.

## Source policy

Pi libraries are normal npm dependencies. Their source is not copied into this repository. The separately archived `vendor/pi-web-ui/` content is retained only as upstream reference for UI secondary development.
