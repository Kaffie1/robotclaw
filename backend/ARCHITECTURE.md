# Backend Architecture

## Current Structure

The backend now treats these directories as the primary implementation layers:

- `gateway/`
  - External entrypoint layer.
  - Owns FastAPI app creation, route registration, request/session binding, and HTTP/SSE responses.
- `agent/`
  - Chat reasoning, routing, prompts, graph state, and node execution for the assistant flow.
  - Primary substructure:
    - `agent/graph/`
    - `agent/prompts/`
    - `agent/shared/`
- `runtime/`
  - Workflow / BT execution layer.
  - Owns playbook loading, rule evaluation, workflow state, task lifecycle, and BT execution.
  - Primary substructure:
    - `runtime/playbooks/`
    - `runtime/rules/`
    - `runtime/workflow/`
    - `runtime/tasks/`
    - `runtime/bt/`
- `runtime/tools/`
  - Tool registry plus executable tool handlers.
- `data/`
  - Persistent stores and data access objects.
- `infra/`
  - Robot clients and dependency container.
  - `infra/container.py` is the primary runtime container.
- `core/`
  - Shared config, models, and low-level stable helpers such as `core/time.py`.

## Compatibility Layers

There are no remaining compatibility wrapper modules in active use.

Already removed because they had no in-repo callers:

- `web/*`
- `web/pages/*`
- `web/support/*`
- `playbooks/*`
- `rules/*`
- `shared/*`
- `tools/*`
- `operations/*`
- `backend/static/*`
- old flat `agent/*.py` wrappers
- `infra/stores/*`

## Dependency Direction

Preferred dependency flow:

`gateway -> agent -> runtime -> runtime/tools -> infra/data`

Additional notes:

- `agent` may read workflow state from `runtime/workflow`.
- `runtime/tools` may use `infra/container` for session/container access.

## Practical Rules

- New HTTP endpoints should go under `gateway/routes/`.
- New playbook/rule execution logic should go under `runtime/`, not `playbooks/` or `rules/`.
- New stores should go under `data/`.
- New global runtime singletons should be defined in `infra/container.py`.
- New imports should prefer primary paths, not compatibility wrappers.

## Cleanup Status

The old compatibility layers have been removed from the in-repo import graph.
Any future cleanup should focus on:

1. Removing stale `__pycache__` artifacts if desired.
2. Simplifying package `__init__.py` exports when the public surface is settled.
