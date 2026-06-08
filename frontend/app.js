const state = {
  sessions: [],
  activeSessionId: "",
  connection: {
    connected: false,
    name: "",
    host: "",
  },
};

const refs = {
  sessionList: document.getElementById("sessionList"),
  chatScroll: document.getElementById("chatScroll"),
  messageInput: document.getElementById("messageInput"),
  sendButton: document.getElementById("sendButton"),
  newSessionButton: document.getElementById("newSessionButton"),
  sessionTemplate: document.getElementById("sessionTemplate"),
  messageTemplate: document.getElementById("messageTemplate"),
  connectionPanel: document.querySelector(".connection-panel"),
  connectionCard: document.getElementById("connectionCard"),
  connectionStatus: document.getElementById("connectionStatus"),
  robotName: document.getElementById("robotName"),
  robotHost: document.getElementById("robotHost"),
  connectionForm: document.getElementById("connectionForm"),
  disconnectButton: document.getElementById("disconnectButton"),
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function activeSession() {
  return state.sessions.find((item) => item.id === state.activeSessionId);
}

function renderSessions() {
  refs.sessionList.innerHTML = "";
  for (const session of state.sessions) {
    const fragment = refs.sessionTemplate.content.cloneNode(true);
    const button = fragment.querySelector(".session-item");
    fragment.querySelector(".session-title").textContent = session.title;
    fragment.querySelector(".session-preview").textContent = session.preview || "暂无消息";
    if (session.id === state.activeSessionId) {
      button.classList.add("active");
    }
    button.addEventListener("click", () => {
      state.activeSessionId = session.id;
      renderAll();
    });
    refs.sessionList.appendChild(fragment);
  }
}

function renderMessages() {
  refs.chatScroll.innerHTML = "";
  const session = activeSession();
  if (!session) return;

  for (const message of session.messages) {
    const fragment = refs.messageTemplate.content.cloneNode(true);
    const container = fragment.querySelector(".message");
    const bubble = fragment.querySelector(".message-bubble");
    const time = fragment.querySelector(".message-time");
    container.classList.add(message.role);
    bubble.textContent = message.content;
    time.textContent = message.created_at || "";
    refs.chatScroll.appendChild(fragment);
  }

  refs.chatScroll.scrollTop = refs.chatScroll.scrollHeight;
}

function renderConnection() {
  const { connected, name, host } = state.connection;
  refs.connectionPanel.classList.toggle("is-connected", connected);
  refs.connectionCard.classList.toggle("connected", connected);
  refs.connectionStatus.classList.toggle("connected", connected);
  refs.connectionStatus.querySelector(".status-text").textContent = connected ? "已连接" : "未连接";
  refs.robotName.textContent = name || "未选择机器人";
  refs.robotHost.textContent = host || "-";
}

function renderAll() {
  renderSessions();
  renderMessages();
  renderConnection();
}

function upsertSession(session) {
  const index = state.sessions.findIndex((item) => item.id === session.id);
  if (index >= 0) {
    state.sessions.splice(index, 1, session);
  } else {
    state.sessions.unshift(session);
  }
}

function promoteSession(sessionId) {
  const session = state.sessions.find((item) => item.id === sessionId);
  if (!session) return;
  state.sessions = [session, ...state.sessions.filter((item) => item.id !== sessionId)];
}

async function bootstrap() {
  const data = await request("/api/bootstrap");
  state.sessions = data.sessions || [];
  state.activeSessionId = data.active_session_id || state.sessions[0]?.id || "";
  state.connection = data.connection || state.connection;
  renderAll();
}

async function sendMessage() {
  const content = refs.messageInput.value.trim();
  if (!content || !state.activeSessionId) return;

  refs.sendButton.disabled = true;
  try {
    const data = await request("/api/chat/send", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.activeSessionId,
        content,
      }),
    });
    refs.messageInput.value = "";
    state.activeSessionId = data.active_session_id;
    upsertSession(data.session);
    promoteSession(state.activeSessionId);
    renderAll();
  } catch (error) {
    window.alert(error.message);
  } finally {
    refs.sendButton.disabled = false;
  }
}

async function createSession() {
  refs.newSessionButton.disabled = true;
  try {
    const data = await request("/api/sessions", {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.activeSessionId = data.active_session_id;
    upsertSession(data.session);
    promoteSession(state.activeSessionId);
    renderAll();
  } catch (error) {
    window.alert(error.message);
  } finally {
    refs.newSessionButton.disabled = false;
  }
}

async function connectRobot(event) {
  event.preventDefault();
  const form = new FormData(refs.connectionForm);
  try {
    state.connection = await request("/api/robot/connect", {
      method: "POST",
      body: JSON.stringify({
        name: String(form.get("name") || "").trim(),
        host: String(form.get("host") || "").trim(),
      }),
    });
    renderConnection();
  } catch (error) {
    window.alert(error.message);
  }
}

async function disconnectRobot() {
  try {
    state.connection = await request("/api/robot/disconnect", {
      method: "POST",
      body: JSON.stringify({}),
    });
    renderConnection();
  } catch (error) {
    window.alert(error.message);
  }
}

refs.sendButton.addEventListener("click", sendMessage);
refs.newSessionButton.addEventListener("click", createSession);
refs.connectionForm.addEventListener("submit", connectRobot);
refs.disconnectButton.addEventListener("click", disconnectRobot);
refs.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

bootstrap().catch((error) => {
  window.alert(`初始化失败：${error.message}`);
});
