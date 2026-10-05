# RobotClaw repository guide

## Module boundaries

- `apps/web/`: React UI based on pi-web-ui. UI-only code lives here.
- `apps/gateway/`: TypeScript gateway that owns Pi sessions, streaming and the browser protocol.
- `services/knowledge/`: future Python RAG service. Do not put Pi session logic here.
- `services/robot/`: future Python ROS and recovery service. Execution must remain explicitly authorized.
- `packages/protocol/`: cross-service contracts. Keep transport models independent from implementations.
- `data/knowledge/` and `data/vectorstore/`: user knowledge assets; never delete them during cleanup.
- `vendor/pi-web-ui/`: archived upstream examples and optional features. It is reference material, not application source.

## Current product boundary

The current phase is conversation plus automatic RAG. All Pi core tools and bundled agent tools remain disabled by default. Do not add ROS, shell or file execution until its phase is explicitly requested.

## Validation

After TypeScript changes, run formatting on changed files, then:

```bash
npm run typecheck
npm run check:protocol
npm run test:unit
npm run build
```

Use Node 24 LTS. Preserve unrelated `.env` changes and never print credentials.
