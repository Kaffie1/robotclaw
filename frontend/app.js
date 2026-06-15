const state = {
  sessions: [],
  activeSessionId: "",
  interactionModes: [],
  defaultInteractionMode: "agent",
  chatBusy: false,
  connection: {
    connected: false,
    name: "",
    host: "",
    port: 22,
  },
  speech: {
    asr_enabled: false,
    auto_send: true,
  },
};

let pendingMessageId = 0;
let mediaRecorder = null;
let recordingStream = null;
let recordingChunks = [];
let isRecording = false;
let isVoiceBusy = false;

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
  connectPassword: document.getElementById("connectPassword"),
  passwordToggle: document.getElementById("passwordToggle"),
  connectionForm: document.getElementById("connectionForm"),
  disconnectButton: document.getElementById("disconnectButton"),
  voiceButton: document.getElementById("voiceButton"),
  composerStatus: document.getElementById("composerStatus"),
  interactionModeSelect: document.getElementById("interactionModeSelect"),
  interactionModeHint: document.getElementById("interactionModeHint"),
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

function nowTimeLabel() {
  const now = new Date();
  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
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
      if (state.chatBusy) return;
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
    if (message.error) {
      container.classList.add("error");
    }
    if (message.pending) {
      container.classList.add("pending");
    }
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

function renderInteractionMode() {
  const session = activeSession();
  const select = refs.interactionModeSelect;
  const hint = refs.interactionModeHint;
  const modes = state.interactionModes || [];
  const currentMode = session?.interaction_mode || state.defaultInteractionMode || "agent";

  select.innerHTML = "";
  for (const mode of modes) {
    const option = document.createElement("option");
    option.value = mode.id;
    option.textContent = mode.label;
    option.selected = mode.id === currentMode;
    select.appendChild(option);
  }

  const activeMode = modes.find((item) => item.id === currentMode);
  hint.textContent = activeMode?.description || "选择当前会话的交互模式。";
  select.disabled = modes.length <= 0 || state.chatBusy;
}

function renderComposerState() {
  const supported = Boolean(navigator.mediaDevices?.getUserMedia) && typeof window.MediaRecorder !== "undefined";
  const hasText = Boolean(refs.messageInput.value.trim());
  refs.messageInput.disabled = state.chatBusy;
  refs.sendButton.disabled = state.chatBusy || !hasText;
  refs.newSessionButton.disabled = state.chatBusy;
  refs.voiceButton.disabled = state.chatBusy || !supported || isVoiceBusy;
}

function renderAll() {
  renderSessions();
  renderMessages();
  renderConnection();
  renderInteractionMode();
  renderComposerState();
  renderVoiceState();
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

function ensureSessionForSending() {
  const session = activeSession();
  if (session) return session;

  const draftSessionId = `draft-${Date.now()}`;
  const draftSession = {
    id: draftSessionId,
    title: "新会话",
    preview: "暂无消息",
    messages: [],
    interaction_mode: state.defaultInteractionMode || "agent",
  };
  state.sessions.unshift(draftSession);
  state.activeSessionId = draftSessionId;
  return draftSession;
}

function appendOptimisticMessages(sessionId, content) {
  const session = state.sessions.find((item) => item.id === sessionId);
  if (!session) return null;

  const pendingId = `pending-${++pendingMessageId}`;
  const createdAt = nowTimeLabel();
  session.messages = [
    ...(session.messages || []),
    {
      id: `${pendingId}-user`,
      role: "user",
      content,
      created_at: createdAt,
      pending: true,
    },
    {
      id: `${pendingId}-assistant`,
      role: "assistant",
      content: "思考中",
      created_at: createdAt,
      pending: true,
    },
  ];
  session.preview = content;
  if (session.title === "新会话" || !session.title) {
    session.title = content.slice(0, 12) || "新会话";
  }
  return pendingId;
}

function finalizePendingMessagesWithError(sessionId, pendingId, errorMessage) {
  const session = state.sessions.find((item) => item.id === sessionId);
  if (!session || !pendingId) return;

  session.messages = (session.messages || []).map((message) => {
    const id = String(message.id || "");
    if (id === `${pendingId}-user`) {
      return {
        ...message,
        pending: false,
      };
    }
    if (id === `${pendingId}-assistant`) {
      return {
        ...message,
        pending: false,
        error: true,
        content: `请求失败：${errorMessage}`,
      };
    }
    return message;
  });
  session.preview = session.messages.at(-1)?.content || session.preview || "暂无消息";
}

async function bootstrap() {
  const data = await request("/api/bootstrap");
  state.sessions = data.sessions || [];
  state.activeSessionId = data.active_session_id || state.sessions[0]?.id || "";
  state.interactionModes = data.interaction_modes || [];
  state.defaultInteractionMode = data.default_interaction_mode || state.sessions[0]?.interaction_mode || state.defaultInteractionMode;
  state.connection = data.connection || state.connection;
  state.speech = data.speech || state.speech;
  renderAll();
}

function renderVoiceState() {
  const supported = Boolean(navigator.mediaDevices?.getUserMedia) && typeof window.MediaRecorder !== "undefined";
  refs.voiceButton.disabled = state.chatBusy || !supported || isVoiceBusy;
  refs.voiceButton.classList.toggle("listening", isRecording);
  refs.voiceButton.setAttribute("aria-pressed", String(isRecording));
  refs.voiceButton.title = state.chatBusy
    ? "正在等待当前回复，请稍后再发送新消息"
    : !supported
    ? "当前浏览器不支持录音"
    : !state.speech.asr_enabled
      ? "ASR 未配置"
      : isRecording
        ? "停止录音并发送"
        : isVoiceBusy
          ? "语音处理中"
          : "开始语音输入";
}

function setComposerStatus(text = "", tone = "") {
  const content = String(text || "").trim();
  refs.composerStatus.hidden = !content;
  refs.composerStatus.textContent = content;
  refs.composerStatus.classList.toggle("error", tone === "error");
}

async function sendMessage() {
  if (state.chatBusy) return;
  const content = refs.messageInput.value.trim();
  if (!content) return;
  refs.messageInput.value = "";
  await sendChatPayload({
    previewContent: content,
    requestPath: "/api/chat/send",
    requestBody: {
      content,
    },
  });
}

async function sendChatPayload({ previewContent, requestPath, requestBody }) {
  if (state.chatBusy) {
    setComposerStatus("正在等待当前回复，请稍后再发送新消息");
    return null;
  }
  state.chatBusy = true;
  const session = ensureSessionForSending();
  const pendingId = appendOptimisticMessages(session.id, previewContent);
  setComposerStatus("");
  renderAll();
  try {
    if (String(session.id).startsWith("draft-")) {
      const created = await request("/api/sessions", {
        method: "POST",
        body: JSON.stringify({
          interaction_mode: session.interaction_mode || state.defaultInteractionMode || "agent",
        }),
      });
      state.activeSessionId = created.active_session_id;
      state.sessions = state.sessions.filter((item) => item.id !== session.id);
      upsertSession(created.session);
      promoteSession(state.activeSessionId);
      appendOptimisticMessages(state.activeSessionId, previewContent);
      renderAll();
    }

    const data = await request(requestPath, {
      method: "POST",
      body: JSON.stringify({
        session_id: state.activeSessionId,
        ...requestBody,
      }),
    });
    state.activeSessionId = data.active_session_id;
    upsertSession(data.session);
    promoteSession(state.activeSessionId);
    renderAll();
    return data;
  } catch (error) {
    const current = activeSession();
    if (current) {
      finalizePendingMessagesWithError(current.id, pendingId, error.message || "请求失败");
    }
    renderAll();
    throw error;
  } finally {
    state.chatBusy = false;
    renderVoiceState();
    renderComposerState();
  }
}

async function createSession() {
  if (state.chatBusy) return;
  refs.newSessionButton.disabled = true;
  try {
    const data = await request("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        interaction_mode: refs.interactionModeSelect.value || state.defaultInteractionMode || "agent",
      }),
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

async function updateInteractionMode() {
  if (state.chatBusy) return;
  const session = activeSession();
  const interactionMode = refs.interactionModeSelect.value || state.defaultInteractionMode || "agent";
  if (!session || String(session.id || "").startsWith("draft-")) {
    state.defaultInteractionMode = interactionMode;
    if (session) {
      session.interaction_mode = interactionMode;
    }
    renderInteractionMode();
    return;
  }
  refs.interactionModeSelect.disabled = true;
  try {
    const data = await request("/api/session/mode", {
      method: "POST",
      body: JSON.stringify({
        session_id: session.id,
        interaction_mode: interactionMode,
      }),
    });
    state.activeSessionId = data.active_session_id;
    upsertSession(data.session);
    promoteSession(state.activeSessionId);
    renderAll();
  } catch (error) {
    window.alert(error.message || "模式更新失败");
    renderAll();
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
        username: String(form.get("username") || "").trim(),
        password: String(form.get("password") || ""),
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

function togglePasswordVisibility() {
  const isVisible = refs.connectPassword.type === "text";
  refs.connectPassword.type = isVisible ? "password" : "text";
  refs.passwordToggle.setAttribute("aria-pressed", String(!isVisible));
  refs.passwordToggle.title = isVisible ? "显示密码" : "隐藏密码";
  refs.passwordToggle.setAttribute("aria-label", isVisible ? "显示密码" : "隐藏密码");
}

async function toggleVoiceRecording() {
  if (state.chatBusy) return;
  if (isVoiceBusy) return;
  if (isRecording) {
    stopVoiceRecording();
    return;
  }
  try {
    if (!state.speech.asr_enabled) {
      throw new Error("ASR 尚未配置");
    }
    await startVoiceRecording();
  } catch (error) {
    setComposerStatus(error.message || "无法启动录音", "error");
    renderVoiceState();
  }
}

async function startVoiceRecording() {
  if (!navigator.mediaDevices?.getUserMedia || typeof window.MediaRecorder === "undefined") {
    throw new Error("当前浏览器不支持录音");
  }
  recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  recordingChunks = [];
  mediaRecorder = new MediaRecorder(recordingStream);
  mediaRecorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size > 0) {
      recordingChunks.push(event.data);
    }
  });
  mediaRecorder.addEventListener("stop", handleRecordingStop, { once: true });
  mediaRecorder.start();
  isRecording = true;
  setComposerStatus("录音中，再点一次麦克风发送");
  renderVoiceState();
}

function stopVoiceRecording() {
  if (!mediaRecorder || !isRecording) return;
  isRecording = false;
  isVoiceBusy = true;
  setComposerStatus("正在上传语音...");
  renderVoiceState();
  mediaRecorder.stop();
}

async function handleRecordingStop() {
  const recorder = mediaRecorder;
  const stream = recordingStream;
  mediaRecorder = null;
  recordingStream = null;
  if (stream) {
    for (const track of stream.getTracks()) {
      track.stop();
    }
  }

  try {
    const mimeType = recorder?.mimeType || "audio/webm";
    const blob = new Blob(recordingChunks, { type: mimeType });
    recordingChunks = [];
    if (!blob.size) {
      throw new Error("没有录到音频");
    }
    setComposerStatus("正在转写语音...");
    const transcription = await transcribeVoiceBlob(blob, mimeType);
    const content = String(transcription.text || "").trim();
    if (!content) {
      throw new Error("语音转写结果为空");
    }
    refs.messageInput.value = content;
    if (state.speech.auto_send) {
      setComposerStatus("语音已转成文字，正在发送...");
      await sendChatPayload({
        previewContent: content,
        requestPath: "/api/chat/send",
        requestBody: {
          content,
        },
      });
      refs.messageInput.value = "";
      setComposerStatus("语音已发送");
    } else {
      setComposerStatus("语音已转成文字，点击发送即可提问");
    }
    refs.messageInput.focus();
    refs.messageInput.setSelectionRange(refs.messageInput.value.length, refs.messageInput.value.length);
    window.setTimeout(() => {
      if (!isRecording && !isVoiceBusy) {
        setComposerStatus("");
      }
    }, 1600);
  } catch (error) {
    setComposerStatus(error.message || "语音发送失败", "error");
    const message = error.message || "语音发送失败";
    window.alert(message);
  } finally {
    recordingChunks = [];
    isVoiceBusy = false;
    renderVoiceState();
  }
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const base64 = result.includes(",") ? result.split(",", 2)[1] : result;
      resolve(base64);
    };
    reader.onerror = () => reject(new Error("音频编码失败"));
    reader.readAsDataURL(blob);
  });
}

async function transcribeVoiceBlob(blob, mimeType) {
  const audioBase64 = await blobToBase64(blob);
  return request("/api/speech/transcribe", {
    method: "POST",
    body: JSON.stringify({
      audio_base64: audioBase64,
      mime_type: mimeType,
      filename: defaultVoiceFilename(mimeType),
    }),
  });
}

function defaultVoiceFilename(mimeType) {
  const normalized = String(mimeType || "").toLowerCase();
  if (normalized.includes("ogg")) return "voice.ogg";
  if (normalized.includes("mp4")) return "voice.m4a";
  if (normalized.includes("mpeg") || normalized.includes("mp3")) return "voice.mp3";
  if (normalized.includes("wav")) return "voice.wav";
  return "voice.webm";
}

refs.sendButton.addEventListener("click", sendMessage);
refs.newSessionButton.addEventListener("click", createSession);
refs.connectionForm.addEventListener("submit", connectRobot);
refs.disconnectButton.addEventListener("click", disconnectRobot);
refs.passwordToggle.addEventListener("click", togglePasswordVisibility);
refs.voiceButton.addEventListener("click", toggleVoiceRecording);
refs.interactionModeSelect.addEventListener("change", updateInteractionMode);
refs.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
refs.messageInput.addEventListener("input", renderComposerState);

bootstrap().catch((error) => {
  window.alert(`初始化失败：${error.message}`);
});
