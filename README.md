# RobotClaw

RobotClaw 是一个面向机器人故障问答与执行恢复的对话助手。项目以 Pi 的 agent runtime 和社区版 pi-web-ui 为技术基座，在其上开发机器人领域界面、RAG 检索与后续受控执行能力。

当前阶段实现多轮问答与自动 RAG 检索：模型可以结合会话和本地机器人知识库回答问题，但默认不开放文件、终端、ROS、子代理或其他执行工具，也不建设长期记忆。

## 技术基线

- Model API：`@earendil-works/pi-ai`（npm 依赖）
- Agent loop：`@earendil-works/pi-agent-core`（npm 依赖）
- Pi 集成：`@earendil-works/pi-coding-agent`（npm 依赖）
- Web：React 19 + Vite 8
- Server：Node.js + Express + WebSocket
- UI 基座：[xing-shuyin/pi-web-ui](https://github.com/xing-shuyin/pi-web-ui)
- 导入基线：`05ced8082bc9d83415364ddf46f78f1e444a0854`（2026-10-04）
- Node.js：推荐 Node 24 LTS（最低支持 `22.22.2`；当前依赖不支持 Node 25）

上游 UI 源码按 MIT License 引入，便于在本仓库内进行二次开发；版权与许可信息见 [LICENSE](LICENSE)。

Pi 的三个库都由根目录 `package.json` 和 `package-lock.json` 管理，执行 `npm install` 即可，不需要下载或复制 Pi 源码。

## 项目结构

```text
apps/
├── web/                  # React 前端，基于 pi-web-ui 二次开发
└── gateway/              # TypeScript：Pi 会话、流式响应、浏览器协议
services/
├── knowledge/            # Python：RAG 检索服务
└── robot/                # Python：ROS 与执行恢复（后续阶段）
packages/
└── protocol/             # TS/Python 跨服务协议
data/
├── knowledge/
└── vectorstore/
vendor/
└── pi-web-ui/            # 上游可选功能与参考代码，不参与主应用构建
```

详细边界见 [docs/architecture.md](docs/architecture.md)。

## 开发

```bash
npm install
npm run dev
```

开发模式默认启动：

- Web：<http://127.0.0.1:5173>
- Server：<http://127.0.0.1:8788>
- Knowledge：<http://127.0.0.1:8790>

生产构建与启动：

```bash
npm run build
npm start
```

首次使用时，在界面的模型设置中配置 provider 和 API key。密钥只保存在服务端，不会发送到浏览器。

## 第一阶段边界

- 保留 Pi 的会话、流式响应、模型管理和上下文压缩能力。
- 不实现长期记忆；现有会话记录只用于恢复当前对话。
- `.pi/settings.json` 将 Pi 内置工具集设为空。
- 服务端默认禁用 UI 注册工具，并关闭工具延迟加载入口，避免向模型暴露 `load_tools`。
- Python Knowledge Service 读取 `data/vectorstore/index.json`，Gateway 在每轮提问前自动检索并以隐藏上下文注入 Pi。
- 文档切分与索引重建保留在 `services/knowledge`，支持从 `data/knowledge` 的 Markdown / txt 文档重建 `data/vectorstore/index.json`。
- RAG 不会把完整知识库塞给模型：默认只取 Top 3 命中片段，每段最多注入 1500 字符，只参与当前请求上下文。
- Knowledge Service 优先使用索引中的 BGE 向量做混合检索，并与 BM25 风格词法评分融合；如果本机没有可用向量模型，会自动退回词法检索。

后续阶段再按业务边界逐个加入 RAG 和 ROS/文件/终端适配器；每个执行工具都应有参数校验、超时、权限控制、审计和人工确认策略。

## 常用检查

```bash
npm run typecheck
npm test
npm run build
```
