# backend/agent

这里按领域收口，方便后续维护时先定位职责，再看实现文件。

## 现有实现文件

当前 `backend/agent/` 已经拍平，核心实现直接放在本目录下：

- `backend/common/`
  - `confirmation_utils.py`
  - `logging_utils.py`
  - `text_utils.py`
- `backend/tools/`
  - `base.py`
  - `common.py`
  - `registry.py`
- `backend/rules/`
  - `schema.py`
  - `engine.py`
- `backend/playbooks/`
  - `loader.py`
  - `matcher.py`
  - `executor.py`
  - `catalog.py`
- `backend/agent/`
  - `graph_builder.py`
  - `graph_nodes.py`
  - `graph_state.py`
  - `model_factory.py`
  - `playbook_state.py`
  - `prompt_builder.py`
  - `render_barrier.py`
  - `thread_context.py`

## 工具模块

- 新增工具、调整工具注册或执行逻辑时，统一修改 `backend/tools/`
