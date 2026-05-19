const CHAT_DEFAULT_PLACEHOLDER = "例如：底盘模块启动后没有速度反馈，帮我先分析可能原因";
const CHAT_MAP_SELECTION_PLACEHOLDER = "请输入序号";

chatState.playbook = chatState.playbook || null;
chatState.playbookExecution = chatState.playbookExecution || null;
chatState.continuation = chatState.continuation || null;

const chatMain = document.getElementById("chatMain");
const playbookPanel = document.getElementById("playbookPanel");
const playbookToggleBtn = document.getElementById("playbookToggleBtn");
const playbookGraph = document.getElementById("playbookGraph");
const playbookZoomOutBtn = document.getElementById("playbookZoomOutBtn");
const playbookZoomInBtn = document.getElementById("playbookZoomInBtn");
const playbookZoomResetBtn = document.getElementById("playbookZoomResetBtn");
const playbookZoomValue = document.getElementById("playbookZoomValue");

const PLAYBOOK_MIN_ZOOM = 0.6;
const PLAYBOOK_MAX_ZOOM = 1.8;
const PLAYBOOK_ZOOM_STEP = 0.1;
const PLAYBOOK_EVENT_PLAYBACK_MS = 180;
const PLAYBOOK_STREAM_RETRY_MS = 1000;
let playbookZoom = 1;
let livePlaybookVersion = 0;
let livePlaybookEventQueue = [];
let livePlaybookPlaybackTimer = null;
let livePlaybookEventSource = null;
let livePlaybookReconnectTimer = null;
let playbookPanelCollapsed = false;

function nextPaint() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(resolve);
    });
  });
}

function renderChatMessages() {
  if (!chatMessageList) return;
  chatMessageList.replaceChildren();
  if (!chatState.messages.length) {
    const empty = document.createElement("div");
    empty.className = "chat-empty-state";
    empty.innerHTML = "<strong>开始对话</strong><p>你可以先描述一个故障现象，或者直接问机器人相关问题。</p>";
    chatMessageList.appendChild(empty);
    return;
  }
  chatState.messages.forEach((message) => {
    const item = document.createElement("article");
    item.className = `chat-message-item chat-message-item-${message.role}`;

    const badge = document.createElement("div");
    badge.className = "chat-message-role";
    badge.textContent = message.role === "assistant" ? "助手" : "你";

    const body = document.createElement("div");
    body.className = "chat-message-body";
    body.textContent = message.content || "";

    item.append(badge, body);
    chatMessageList.appendChild(item);
  });

  chatMessageList.scrollTop = chatMessageList.scrollHeight;
}

function setChatPending(pending) {
  chatState.pending = Boolean(pending);
  if (chatSubmitBtn) {
    chatSubmitBtn.disabled = chatState.pending;
    chatSubmitBtn.textContent = chatState.pending ? "发送中..." : "发送";
  }
  if (chatInput) {
    chatInput.disabled = chatState.pending;
  }
}

function setChatClarifyState(clarify = null) {
  chatState.pendingClarify = clarify && typeof clarify === "object" ? clarify : null;
  if (!chatInput) return;
  const mode = String(chatState.pendingClarify?.mode || "").trim();
  chatInput.placeholder = mode === "map_selection"
    ? CHAT_MAP_SELECTION_PLACEHOLDER
    : CHAT_DEFAULT_PLACEHOLDER;
}

function clearChatClientState() {
  chatState.messages = [];
  chatState.playbook = null;
  chatState.playbookExecution = null;
  chatState.continuation = null;
  setChatClarifyState(null);
  resetPlaybookGraph();
  renderChatMessages();
}

function getRecentConversationHistory() {
  return chatState.messages
    .filter((item) => item && (item.role === "user" || item.role === "assistant") && item.content)
    .slice(-10)
    .map((item) => ({
      role: item.role,
      content: String(item.content || "").trim(),
    }));
}

function updatePlaybookPanelVisibility() {
  if (chatMain) chatMain.classList.toggle("is-playbook-collapsed", playbookPanelCollapsed);
  if (playbookToggleBtn) {
    playbookToggleBtn.textContent = playbookPanelCollapsed ? "展开流程图" : "关闭流程图";
    playbookToggleBtn.setAttribute("aria-expanded", playbookPanelCollapsed ? "false" : "true");
  }
}

function resetPlaybookGraph() {
  if (playbookGraph) {
    playbookGraph.innerHTML = '<div class="playbook-empty">匹配到恢复流程后，这里会直接展示流程图。</div>';
  }
}

function showPlaybook(playbook) {
  if (!playbookPanel) return;
  chatState.playbook = playbook || {};
  renderPlaybookGraph(chatState.playbook.root || chatState.playbook);
}

function hidePlaybook() {
  chatState.playbook = null;
  livePlaybookEventQueue = [];
  if (livePlaybookPlaybackTimer) {
    window.clearTimeout(livePlaybookPlaybackTimer);
    livePlaybookPlaybackTimer = null;
  }
  resetPlaybookGraph();
}

function renderPlaybookGraph(root) {
  if (!playbookGraph) return;
  playbookGraph.replaceChildren();
  if (!root || typeof root !== "object") {
    const empty = document.createElement("div");
    empty.className = "playbook-empty";
    empty.textContent = "暂无流程图数据";
    playbookGraph.appendChild(empty);
    return;
  }

  const scene = document.createElement("div");
  scene.className = "flow-scene";
  const overlay = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  overlay.setAttribute("class", "flow-overlay");
  scene.appendChild(renderFlowNode(root, "root"));
  scene.appendChild(overlay);
  playbookGraph.appendChild(scene);
  refreshFlowConnections(root, scene);
  applyPlaybookZoom();
}

function renderFlowNode(node, path = "root") {
  if (!node || typeof node !== "object") {
    const empty = document.createElement("div");
    empty.className = "flow-node-empty";
    return empty;
  }
  const nodeType = normalizeNodeType(node.type);
  if (nodeType === "selector") return renderSelectorFlow(node, path);
  if (nodeType === "sequence") return renderSequenceFlow(node, path);
  if (nodeType === "call_playbook") return renderCallPlaybookFlow(node, path);
  return renderLeafFlow(node, path);
}

function renderLeafFlow(node, path) {
  const wrapper = document.createElement("div");
  wrapper.className = "flow-leaf";
  wrapper.appendChild(createFlowNodeCard(node, path));
  return wrapper;
}

function renderSequenceFlow(node, path) {
  const container = document.createElement("div");
  container.className = "flow-sequence";
  container.appendChild(createFlowNodeCard(node, path));
  const children = Array.isArray(node.children) ? node.children : [];
  children.forEach((child, index) => {
    const step = document.createElement("div");
    step.className = "flow-sequence-step";
    const connector = document.createElement("div");
    connector.className = "flow-sequence-connector";
    step.append(connector, renderFlowNode(child, `${path}.children[${index}]`));
    container.appendChild(step);
  });
  return container;
}

function renderSelectorFlow(node, path) {
  const container = document.createElement("div");
  container.className = "flow-selector";
  container.appendChild(createFlowNodeCard(node, path));
  const children = Array.isArray(node.children) ? node.children : [];
  const fanout = document.createElement("div");
  fanout.className = "flow-selector-fanout";
  const branches = document.createElement("div");
  branches.className = "flow-selector-branches";
  branches.style.setProperty("--branch-count", String(Math.max(children.length, 1)));
  Array.from({ length: children.length }, (_, index) => index).forEach((index) => {
    const branch = document.createElement("div");
    branch.className = "flow-selector-branch";
    branch.append(renderFlowNode(children[index], `${path}.children[${index}]`));
    branches.appendChild(branch);
  });
  fanout.append(branches);
  container.appendChild(fanout);
  return container;
}

function renderCallPlaybookFlow(node, path) {
  const children = Array.isArray(node.children) ? node.children : [];
  if (!children.length) return renderLeafFlow(node, path);

  const container = document.createElement("div");
  container.className = "flow-call-playbook";
  container.appendChild(createFlowNodeCard(node, path));

  const content = document.createElement("div");
  content.className = "flow-call-playbook-content";
  children.forEach((child, index) => {
    const branch = document.createElement("div");
    branch.className = "flow-call-playbook-branch";
    branch.appendChild(renderFlowNode(child, `${path}.children[${index}]`));
    content.appendChild(branch);
  });
  container.appendChild(content);
  return container;
}

function refreshFlowConnections(root, scene) {
  if (!(scene instanceof HTMLElement)) return;
  const svg = scene.querySelector(":scope > .flow-overlay");
  if (!(svg instanceof SVGElement)) return;
  const zoom = Number(playbookZoom) || 1;

  const width = Math.max(scene.scrollWidth, scene.clientWidth);
  const height = Math.max(scene.scrollHeight, scene.clientHeight);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.replaceChildren();

  const graph = buildFlowEdgeGraph(root, "root");
  const incomingEdgeCounts = graph.edges.reduce((counts, edge) => {
    counts[edge.to] = (counts[edge.to] || 0) + 1;
    return counts;
  }, {});
  const sceneRect = scene.getBoundingClientRect();

  graph.edges.forEach((edge) => {
    const fromCard = scene.querySelector(`.flow-node-card[data-node-path="${cssEscape(edge.from)}"]`);
    const toCard = scene.querySelector(`.flow-node-card[data-node-path="${cssEscape(edge.to)}"]`);
    if (!(fromCard instanceof HTMLElement) || !(toCard instanceof HTMLElement)) return;

    const fromRect = fromCard.getBoundingClientRect();
    const toRect = toCard.getBoundingClientRect();
    const startX = (fromRect.left - sceneRect.left + fromRect.width / 2) / zoom;
    const startY = (fromRect.bottom - sceneRect.top) / zoom;
    const endX = (toRect.left - sceneRect.left + toRect.width / 2) / zoom;
    const endY = (toRect.top - sceneRect.top) / zoom;
    const renderKind = incomingEdgeCounts[edge.to] > 1 ? "branch" : edge.kind;
    const geometry = buildConnectorGeometry(startX, startY, endX, endY, renderKind);

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", geometry.pathD);
    path.setAttribute("class", renderKind === "sequence" ? "flow-edge-sequence" : "flow-edge-branch");
    svg.appendChild(path);

    const arrowHead = document.createElementNS("http://www.w3.org/2000/svg", "path");
    arrowHead.setAttribute("d", buildArrowHeadPath(geometry.tip, geometry.baseCenter, geometry.arrowWidth));
    arrowHead.setAttribute("class", renderKind === "sequence" ? "flow-arrow-sequence" : "flow-arrow-branch");
    svg.appendChild(arrowHead);
  });
}

function buildFlowEdgeGraph(node, path = "root") {
  if (!node || typeof node !== "object") {
    return { entryId: path, exitIds: [path], edges: [] };
  }
  const nodeType = normalizeNodeType(node.type);
  const children = Array.isArray(node.children) ? node.children : [];
  if (!children.length) {
    return { entryId: path, exitIds: [path], edges: [] };
  }
  if (nodeType === "sequence") {
    let previousExitIds = [path];
    let edges = [];
    children.forEach((child, index) => {
      const childGraph = buildFlowEdgeGraph(child, `${path}.children[${index}]`);
      previousExitIds.forEach((fromId) => {
        edges.push({ from: fromId, to: childGraph.entryId, kind: "sequence" });
      });
      edges = edges.concat(childGraph.edges);
      previousExitIds = childGraph.exitIds.length ? childGraph.exitIds : previousExitIds;
    });
    return { entryId: path, exitIds: previousExitIds, edges };
  }
  if (nodeType === "selector") {
    let edges = [];
    let exitIds = [];
    children.forEach((child, index) => {
      const childGraph = buildFlowEdgeGraph(child, `${path}.children[${index}]`);
      edges.push({ from: path, to: childGraph.entryId, kind: "branch" });
      edges = edges.concat(childGraph.edges);
      exitIds = exitIds.concat(childGraph.exitIds);
    });
    return { entryId: path, exitIds: exitIds.length ? exitIds : [path], edges };
  }
  if (children.length) {
    let edges = [];
    let exitIds = [];
    children.forEach((child, index) => {
      const childGraph = buildFlowEdgeGraph(child, `${path}.children[${index}]`);
      edges.push({ from: path, to: childGraph.entryId, kind: "sequence" });
      edges = edges.concat(childGraph.edges);
      exitIds = exitIds.concat(childGraph.exitIds);
    });
    return { entryId: path, exitIds: exitIds.length ? exitIds : [path], edges };
  }
  return { entryId: path, exitIds: [path], edges: [] };
}

function buildConnectorGeometry(startX, startY, endX, endY, kind) {
  const arrowLength = kind === "sequence" ? 14 : 13;
  const arrowWidth = kind === "sequence" ? 8 : 7;
  const tip = { x: endX, y: endY };
  const baseCenter = { x: endX, y: endY - arrowLength };
  if (kind === "sequence") {
    return { pathD: `M ${startX} ${startY} L ${baseCenter.x} ${baseCenter.y}`, tip, baseCenter, arrowWidth };
  }
  const curveLift = Math.max(36, (endY - startY) * 0.34);
  return {
    pathD: `M ${startX} ${startY} C ${startX} ${startY + curveLift}, ${baseCenter.x} ${baseCenter.y - curveLift}, ${baseCenter.x} ${baseCenter.y}`,
    tip,
    baseCenter,
    arrowWidth,
  };
}

function buildArrowHeadPath(tip, baseCenter, halfWidth) {
  const leftX = baseCenter.x - halfWidth;
  const rightX = baseCenter.x + halfWidth;
  return `M ${leftX} ${baseCenter.y} L ${tip.x} ${tip.y} L ${rightX} ${baseCenter.y} Z`;
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
  return String(value).replace(/"/g, "\\\"");
}

function createFlowNodeCard(node, path) {
  const status = getNodeExecutionStatus(path);
  const card = document.createElement("div");
  card.className = `flow-node-card status-${status}`;
  card.dataset.nodePath = path;

  const dot = document.createElement("span");
  dot.className = `flow-node-dot status-${status}`;
  dot.setAttribute("aria-hidden", "true");

  const title = document.createElement("div");
  title.className = "flow-node-title";
  title.textContent = truncateText(getFlowNodeTitle(node), 22);

  const meta = getFlowNodeMeta(node);
  const content = document.createElement("div");
  content.className = "flow-node-content";
  content.appendChild(title);
  if (meta) {
    const metaText = document.createElement("div");
    metaText.className = "flow-node-meta";
    metaText.textContent = truncateText(meta, 28);
    content.appendChild(metaText);
  }
  card.append(dot, content);
  return card;
}

function getFlowNodeTitle(node) {
  return String(
    node.display_name ||
    node.name ||
    node.title ||
    node.tool_name ||
    node.playbook_id ||
    node.type ||
    "未命名节点"
  ).trim();
}

function getFlowNodeMeta(node) {
  const nodeType = normalizeNodeType(node.type);
  if (nodeType === "call_playbook") {
    return String(node.expanded_playbook_title || node.expanded_playbook_id || node.playbook_id || "").trim();
  }
  return "";
}

function normalizeNodeType(nodeType) {
  return String(nodeType || "unknown").trim().toLowerCase();
}

function normalizeExecutionStatus(status) {
  return ["unstarted", "pending", "success", "failed", "skipped"].includes(String(status || ""))
    ? String(status)
    : "unstarted";
}

function getNodeExecutionStatus(path) {
  const execution = chatState.playbookExecution?.node_statuses?.[path];
  return normalizeExecutionStatus(execution?.status);
}

function truncateText(text, maxLength = 24) {
  const normalized = String(text || "").trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength - 1)}…`;
}

function applyPlaybookZoom() {
  if (!playbookGraph) return;
  const scene = playbookGraph.querySelector(".flow-scene");
  if (scene) {
    scene.style.zoom = String(playbookZoom);
    if (chatState.playbook) {
      refreshFlowConnections(chatState.playbook.root || chatState.playbook, scene);
    }
  }
  if (playbookZoomValue) playbookZoomValue.textContent = `${Math.round(playbookZoom * 100)}%`;
  if (playbookZoomOutBtn) playbookZoomOutBtn.disabled = playbookZoom <= PLAYBOOK_MIN_ZOOM;
  if (playbookZoomInBtn) playbookZoomInBtn.disabled = playbookZoom >= PLAYBOOK_MAX_ZOOM;
}

function setPlaybookZoom(nextZoom) {
  const clamped = Math.min(PLAYBOOK_MAX_ZOOM, Math.max(PLAYBOOK_MIN_ZOOM, Number(nextZoom) || 1));
  playbookZoom = Math.round(clamped * 100) / 100;
  applyPlaybookZoom();
}

function maybeShowPlaybookFromResponse(data) {
  chatState.playbookExecution = data.playbook_execution && typeof data.playbook_execution === "object"
    ? data.playbook_execution
    : null;
  if (Number.isFinite(Number(data?.version))) {
    livePlaybookVersion = Math.max(livePlaybookVersion, Number(data.version) || 0);
  }
  const playbook = data.playbook || data.matched_playbook || data.matched_context || data.playbook_context || null;
  if (playbook && typeof playbook === "object") {
    showPlaybook(playbook);
    return;
  }
  if (Object.prototype.hasOwnProperty.call(data || {}, "playbook") || Object.prototype.hasOwnProperty.call(data || {}, "playbook_execution")) {
    chatState.playbook = null;
    hidePlaybook();
  }
}

function enqueuePlaybookStateUpdate(data) {
  livePlaybookEventQueue.push(data);
  if (Number.isFinite(Number(data?.version))) {
    livePlaybookVersion = Math.max(livePlaybookVersion, Number(data.version) || 0);
  }
}

function applyLivePlaybookEvents(data) {
  const events = Array.isArray(data?.events) ? data.events : [];
  if (!events.length) {
    maybeShowPlaybookFromResponse(data || {});
    return;
  }
  events.forEach((event) => enqueuePlaybookStateUpdate(event));
  playNextLivePlaybookEvent();
}

function playNextLivePlaybookEvent() {
  if (livePlaybookPlaybackTimer || !livePlaybookEventQueue.length) return;
  const nextEvent = livePlaybookEventQueue.shift();
  maybeShowPlaybookFromResponse(nextEvent || {});
  livePlaybookPlaybackTimer = window.setTimeout(() => {
    livePlaybookPlaybackTimer = null;
    playNextLivePlaybookEvent();
  }, PLAYBOOK_EVENT_PLAYBACK_MS);
}

function scheduleLivePlaybookReconnect() {
  if (livePlaybookReconnectTimer) return;
  livePlaybookReconnectTimer = window.setTimeout(() => {
    livePlaybookReconnectTimer = null;
    connectLivePlaybookStream();
  }, PLAYBOOK_STREAM_RETRY_MS);
}

function disconnectLivePlaybookStream() {
  if (livePlaybookReconnectTimer) {
    window.clearTimeout(livePlaybookReconnectTimer);
    livePlaybookReconnectTimer = null;
  }
  if (livePlaybookEventSource) {
    livePlaybookEventSource.close();
    livePlaybookEventSource = null;
  }
}

function connectLivePlaybookStream() {
  if (livePlaybookEventSource) return;
  const eventSource = new EventSource(`/api/chat/events?since_version=${livePlaybookVersion}`);
  livePlaybookEventSource = eventSource;
  eventSource.addEventListener("playbook_state", (event) => {
    try {
      applyLivePlaybookEvents(JSON.parse(String(event.data || "{}")));
    } catch (error) {
      appendLog("流程图状态解析失败", error.message);
    }
  });
  eventSource.addEventListener("heartbeat", () => {});
  eventSource.onerror = () => {
    disconnectLivePlaybookStream();
    scheduleLivePlaybookReconnect();
  };
}

function startLivePlaybookStreaming() {
  livePlaybookEventQueue = [];
  if (livePlaybookPlaybackTimer) {
    window.clearTimeout(livePlaybookPlaybackTimer);
    livePlaybookPlaybackTimer = null;
  }
  connectLivePlaybookStream();
}

function stopLivePlaybookStreaming() {
  while (livePlaybookEventQueue.length) {
    maybeShowPlaybookFromResponse(livePlaybookEventQueue.shift());
  }
}

async function submitChatMessage(event) {
  event.preventDefault();
  const content = String(chatInput?.value || "").trim();
  if (!content) throw new Error("请输入聊天内容");
  const historyBeforeSubmit = getRecentConversationHistory();
  chatState.messages.push({ role: "user", content });
  renderChatMessages();
  if (chatInput) chatInput.value = "";
  setChatPending(true);
  startLivePlaybookStreaming();

  try {
    const initialPayload = {
      message: content,
      history: historyBeforeSubmit,
    };
    if (chatState.continuation && typeof chatState.continuation === "object") {
      initialPayload.continuation = chatState.continuation;
    }
    let data = await request("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(initialPayload),
    });

    if (data.continuation?.kind === "playbook_render_ready") {
      maybeShowPlaybookFromResponse(data);
      await nextPaint();

      const routeSelection = {
        playbook_id: String(data.continuation.playbook_id || "").trim(),
        playbook_title: String(data.continuation.playbook_title || "").trim(),
        reason: String(data.continuation.reason || "").trim(),
      };
      const readyContinuation = {
        kind: "playbook_render_ready",
        user_message: String(data.continuation.user_message || content).trim(),
        playbook_id: routeSelection.playbook_id,
        playbook_title: routeSelection.playbook_title,
        reason: routeSelection.reason,
        thread_id: String(data.continuation.thread_id || "").trim(),
      };

      data = await request("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "",
          history: historyBeforeSubmit,
          continuation: readyContinuation,
          route_selection: routeSelection,
        }),
      });
    }

    chatState.messages.push({
      role: "assistant",
      content: String(data.message || "").trim(),
    });
    chatState.continuation = data.continuation && typeof data.continuation === "object"
      ? data.continuation
      : null;
    setChatClarifyState(data.clarify || null);
    maybeShowPlaybookFromResponse(data);
    renderChatMessages();
    appendLog("聊天助手回复完成", data.model || "");
  } catch (error) {
    chatState.messages.push({
      role: "assistant",
      content: `调用失败：${error.message}`,
    });
    renderChatMessages();
    throw error;
  } finally {
    stopLivePlaybookStreaming();
    setChatPending(false);
    if (!chatState.pendingClarify && chatInput) {
      chatInput.placeholder = CHAT_DEFAULT_PLACEHOLDER;
    }
  }
}

window.addEventListener("beforeunload", () => {
  disconnectLivePlaybookStream();
});

if (chatForm) {
  chatForm.addEventListener("submit", async (event) => {
    try {
      await submitChatMessage(event);
    } catch (error) {
      appendLog("聊天发送失败", error.message);
      alert(error.message);
    }
  });
}

if (chatClearBtn) {
  chatClearBtn.addEventListener("click", async () => {
    try {
      await request("/api/chat/reset", { method: "POST" });
    } catch (error) {
      appendLog("清空聊天上下文失败", error.message);
    } finally {
      clearChatClientState();
    }
  });
}

if (playbookToggleBtn) {
  playbookToggleBtn.addEventListener("click", () => {
    playbookPanelCollapsed = !playbookPanelCollapsed;
    updatePlaybookPanelVisibility();
  });
}

if (playbookZoomOutBtn) {
  playbookZoomOutBtn.addEventListener("click", () => setPlaybookZoom(playbookZoom - PLAYBOOK_ZOOM_STEP));
}

if (playbookZoomInBtn) {
  playbookZoomInBtn.addEventListener("click", () => setPlaybookZoom(playbookZoom + PLAYBOOK_ZOOM_STEP));
}

if (playbookZoomResetBtn) {
  playbookZoomResetBtn.addEventListener("click", () => setPlaybookZoom(1));
}

if (playbookGraph) {
  playbookGraph.addEventListener("wheel", (event) => {
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    const delta = event.deltaY < 0 ? PLAYBOOK_ZOOM_STEP : -PLAYBOOK_ZOOM_STEP;
    setPlaybookZoom(playbookZoom + delta);
  }, { passive: false });
}

renderChatMessages();
applyPlaybookZoom();
connectLivePlaybookStream();
updatePlaybookPanelVisibility();
