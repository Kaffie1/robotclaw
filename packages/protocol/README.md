# Protocol

This module will contain language-neutral HTTP/RPC schemas shared by the TypeScript gateway and Python services.

The browser WebSocket protocol currently remains at `apps/gateway/src/protocol.ts` because the imported UI consumes it directly. It can be extracted here incrementally after the conversation surface is simplified.
