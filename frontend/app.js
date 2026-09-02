const state = {
  sessions: [],
  activeSessionId: "",
  chatBusy: false,
  speech: {
    asr_enabled: false,
    auto_send: true,
  },
  settings: {},
  settingsDefaults: {},
  pendingImages: [],
};

const SETTINGS_STORAGE_KEY = "robotclaw.llm_settings";
const ATTACHMENT_SUMMARY_PATTERN = /\s*\[\d+\s*张图片\]\s*/g;

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
  voiceButton: document.getElementById("voiceButton"),
  composerStatus: document.getElementById("composerStatus"),
  attachImageButton: document.getElementById("attachImageButton"),
  imageInput: document.getElementById("imageInput"),
  imagePreview: document.getElementById("imagePreview"),
  imageLightbox: document.getElementById("imageLightbox"),
  imageLightboxImg: document.getElementById("imageLightboxImg"),
  imageLightboxClose: document.getElementById("imageLightboxClose"),
  settingsButton: document.getElementById("settingsButton"),
  settingsModal: document.getElementById("settingsModal"),
  settingsForm: document.getElementById("settingsForm"),
  settingsCloseButton: document.getElementById("settingsCloseButton"),
  settingsCancelButton: document.getElementById("settingsCancelButton"),
  settingsSaveButton: document.getElementById("settingsSaveButton"),
  settingsStatus: document.getElementById("settingsStatus"),
  openaiApiKeyInput: document.getElementById("openaiApiKeyInput"),
  apiKeyToggleButton: document.getElementById("apiKeyToggleButton"),
  openaiBaseUrlInput: document.getElementById("openaiBaseUrlInput"),
  openaiChatModelInput: document.getElementById("openaiChatModelInput"),
  llmTemperatureInput: document.getElementById("llmTemperatureInput"),
  topKInput: document.getElementById("topKInput"),
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

function loadLocalSettings() {
  try {
    const raw = window.sessionStorage.getItem(SETTINGS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return normalizeSettings(parsed);
  } catch {
    return {};
  }
}

function saveLocalSettings(settings) {
  window.sessionStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(normalizeSettings(settings)));
}

function normalizeSettings(settings) {
  return {
    OPENAI_API_KEY: String(settings?.OPENAI_API_KEY || "").trim(),
    OPENAI_BASE_URL: String(settings?.OPENAI_BASE_URL || "").trim(),
    OPENAI_CHAT_MODEL: String(settings?.OPENAI_CHAT_MODEL || "").trim(),
    ROBOTCLAW_LLM_TEMPERATURE: String(settings?.ROBOTCLAW_LLM_TEMPERATURE || "").trim(),
    TOP_K: String(settings?.TOP_K || "").trim(),
  };
}

function currentRequestSettings() {
  return normalizeSettings(state.settings);
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
    fragment.querySelector(".session-preview").textContent = displayMessageContent(session.preview) || "暂无消息";
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
    renderMessageBubble(bubble, message);
    time.textContent = formatMessageFooter(message);
    refs.chatScroll.appendChild(fragment);
  }

  refs.chatScroll.scrollTop = refs.chatScroll.scrollHeight;
}

function renderMessageBubble(bubble, message) {
  bubble.textContent = "";
  const text = displayMessageContent(message.content);
  if (text) {
    const textNode = document.createElement("div");
    textNode.className = "message-text";
    textNode.textContent = text;
    bubble.appendChild(textNode);
  }

  const images = Array.isArray(message.images) ? message.images : [];
  if (images.length > 0) {
    const grid = document.createElement("div");
    grid.className = "message-images";
    for (const image of images) {
      const mediaType = String(image.media_type || image.source?.media_type || "image/png");
      const data = String(image.data || image.source?.data || "");
      if (!data) continue;
      const preview = document.createElement("img");
      preview.className = "message-image";
      preview.alt = image.name || "attached image";
      preview.src = `data:${mediaType};base64,${data}`;
      preview.addEventListener("click", () => openImageLightbox(preview.src, preview.alt));
      grid.appendChild(preview);
    }
    if (grid.children.length > 0) {
      bubble.appendChild(grid);
    }
  }
}

function displayMessageContent(content) {
  return String(content || "").replace(ATTACHMENT_SUMMARY_PATTERN, " ").trim();
}

function formatMessageFooter(message) {
  const parts = [];
  if (message.created_at) {
    parts.push(message.created_at);
  }
  const metrics = message.metadata?.metrics;
  if (message.role === "assistant" && metrics) {
    const totalTokens = Number(metrics.total_tokens);
    const elapsedSeconds = Number(metrics.elapsed_seconds);
    if (Number.isFinite(totalTokens) && totalTokens > 0) {
      parts.push(`${totalTokens} tokens`);
    }
    if (Number.isFinite(elapsedSeconds) && elapsedSeconds >= 0) {
      parts.push(`${formatDuration(elapsedSeconds)}`);
    }
  }
  return parts.join(" · ");
}

function formatDuration(seconds) {
  if (seconds < 60) {
    return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return `${minutes}m ${remaining}s`;
}

function renderComposerState() {
  const hasText = Boolean(refs.messageInput.value.trim());
  const hasImages = state.pendingImages.length > 0;
  refs.messageInput.disabled = state.chatBusy;
  refs.sendButton.disabled = state.chatBusy || (!hasText && !hasImages);
  refs.newSessionButton.disabled = state.chatBusy;
  refs.voiceButton.disabled = state.chatBusy || isVoiceBusy;
  refs.attachImageButton.disabled = state.chatBusy;
  renderPendingImages();
}

function renderPendingImages() {
  refs.imagePreview.innerHTML = "";
  refs.imagePreview.hidden = state.pendingImages.length <= 0;
  for (const [index, image] of state.pendingImages.entries()) {
    const item = document.createElement("div");
    item.className = "composer-image-item";

    const preview = document.createElement("img");
    preview.className = "composer-image-thumb";
    preview.alt = image.name || "待发送图片";
    preview.src = `data:${image.media_type || "image/png"};base64,${image.data}`;
    preview.addEventListener("click", () => openImageLightbox(preview.src, preview.alt));
    item.appendChild(preview);

    const removeButton = document.createElement("button");
    removeButton.className = "composer-image-remove";
    removeButton.type = "button";
    removeButton.title = "删除图片";
    removeButton.setAttribute("aria-label", "删除图片");
    removeButton.textContent = "×";
    removeButton.addEventListener("click", () => removePendingImage(index));
    item.appendChild(removeButton);

    refs.imagePreview.appendChild(item);
  }
}

function removePendingImage(index) {
  state.pendingImages.splice(index, 1);
  setComposerStatus(state.pendingImages.length > 0 ? `已添加 ${state.pendingImages.length} 张图片` : "");
  renderComposerState();
}

function openImageLightbox(src, alt = "图片预览") {
  refs.imageLightboxImg.src = src;
  refs.imageLightboxImg.alt = alt;
  refs.imageLightbox.hidden = false;
  document.body.classList.add("lightbox-open");
}

function closeImageLightbox() {
  refs.imageLightbox.hidden = true;
  refs.imageLightboxImg.removeAttribute("src");
  document.body.classList.remove("lightbox-open");
}

function openSettingsModal() {
  refs.settingsModal.hidden = false;
  setSettingsStatus("正在加载设置...");
  request("/api/settings")
    .then((data) => {
      state.settings = {
        ...(data.settings || {}),
        ...loadLocalSettings(),
      };
      state.settingsDefaults = data.defaults || {};
      populateSettingsForm();
      setSettingsStatus("");
      refs.openaiApiKeyInput.focus();
    })
    .catch((error) => {
      populateSettingsForm();
      setSettingsStatus(error.message || "设置加载失败", "error");
    });
}

function closeSettingsModal() {
  refs.settingsModal.hidden = true;
  setSettingsStatus("");
}

function populateSettingsForm() {
  const settings = state.settings || {};
  const defaults = state.settingsDefaults || {};
  refs.openaiApiKeyInput.value = settings.OPENAI_API_KEY || "";
  setApiKeyVisible(false);
  refs.openaiBaseUrlInput.value = settings.OPENAI_BASE_URL || "";
  refs.openaiChatModelInput.value = settings.OPENAI_CHAT_MODEL || "";
  refs.llmTemperatureInput.value = settings.ROBOTCLAW_LLM_TEMPERATURE || "";
  refs.topKInput.value = settings.TOP_K || "";
  refs.openaiBaseUrlInput.placeholder = defaults.OPENAI_BASE_URL || "代码默认值";
  refs.openaiChatModelInput.placeholder = defaults.OPENAI_CHAT_MODEL || "代码默认值";
  refs.llmTemperatureInput.placeholder = defaults.ROBOTCLAW_LLM_TEMPERATURE || "0";
  refs.topKInput.placeholder = defaults.TOP_K || "4";
}

function setApiKeyVisible(visible) {
  refs.openaiApiKeyInput.type = visible ? "text" : "password";
  refs.apiKeyToggleButton.textContent = visible ? "隐藏" : "显示";
  refs.apiKeyToggleButton.setAttribute("aria-pressed", String(visible));
  refs.apiKeyToggleButton.setAttribute("aria-label", visible ? "隐藏 API_KEY" : "显示 API_KEY");
}

function toggleApiKeyVisibility() {
  setApiKeyVisible(refs.openaiApiKeyInput.type === "password");
}

function setSettingsStatus(text = "", tone = "") {
  const content = String(text || "").trim();
  refs.settingsStatus.hidden = !content;
  refs.settingsStatus.textContent = content;
  refs.settingsStatus.classList.toggle("error", tone === "error");
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = normalizeSettings({
    OPENAI_API_KEY: refs.openaiApiKeyInput.value.trim(),
    OPENAI_BASE_URL: refs.openaiBaseUrlInput.value.trim(),
    OPENAI_CHAT_MODEL: refs.openaiChatModelInput.value.trim(),
    ROBOTCLAW_LLM_TEMPERATURE: refs.llmTemperatureInput.value.trim(),
    TOP_K: refs.topKInput.value.trim(),
  });
  refs.settingsSaveButton.disabled = true;
  setSettingsStatus("正在保存...");
  try {
    if (!payload.OPENAI_API_KEY) {
      throw new Error("API_KEY 不能为空");
    }
    if (payload.TOP_K && Number.parseInt(payload.TOP_K, 10) <= 0) {
      throw new Error("TOP_K 必须大于 0");
    }
    if (payload.ROBOTCLAW_LLM_TEMPERATURE && Number.isNaN(Number.parseFloat(payload.ROBOTCLAW_LLM_TEMPERATURE))) {
      throw new Error("TEMPERATURE 必须是数字");
    }
    saveLocalSettings(payload);
    state.settings = payload;
    setSettingsStatus("已保存");
    window.setTimeout(closeSettingsModal, 500);
    renderAll();
  } catch (error) {
    setSettingsStatus(error.message || "保存失败", "error");
  } finally {
    refs.settingsSaveButton.disabled = false;
  }
}

function renderAll() {
  renderSessions();
  renderMessages();
  renderComposerState();
  renderVoiceState();
}

function upsertSession(session) {
  preserveLocalImagePreviews(session);
  const index = state.sessions.findIndex((item) => item.id === session.id);
  if (index >= 0) {
    state.sessions.splice(index, 1, session);
  } else {
    state.sessions.unshift(session);
  }
}

function preserveLocalImagePreviews(incomingSession) {
  const existing = state.sessions.find((item) => item.id === incomingSession.id);
  if (!existing?.messages?.length || !incomingSession?.messages?.length) return;
  const localImageMessages = existing.messages.filter((message) => Array.isArray(message.images) && message.images.length > 0);
  if (localImageMessages.length <= 0) return;

  for (const localMessage of localImageMessages) {
    const target = incomingSession.messages.find(
      (message) =>
        message.role === localMessage.role &&
        !Array.isArray(message.images) &&
        String(message.content || "").trim() === String(localMessage.content || "").trim(),
    );
    if (target) {
      target.images = localMessage.images;
    }
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
  };
  state.sessions.unshift(draftSession);
  state.activeSessionId = draftSessionId;
  return draftSession;
}

function appendOptimisticMessages(sessionId, content, images = []) {
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
      images,
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
  state.speech = data.speech || state.speech;
  state.settings = loadLocalSettings();
  renderAll();
}

function renderVoiceState() {
  const supported = Boolean(navigator.mediaDevices?.getUserMedia) && typeof window.MediaRecorder !== "undefined";
  refs.voiceButton.disabled = state.chatBusy || isVoiceBusy;
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
  const images = state.pendingImages;
  if (!content && images.length <= 0) return;
  const previewContent = images.length > 0 ? `${content || "图片"} [${images.length} 张图片]` : content;
  refs.messageInput.value = "";
  state.pendingImages = [];
  setComposerStatus("");
  renderComposerState();
  await sendChatPayload({
    previewContent,
    requestPath: "/api/chat/send",
    requestBody: {
      content,
      images,
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
  let pendingId = appendOptimisticMessages(session.id, previewContent, requestBody.images || []);
  setComposerStatus("");
  renderAll();
  try {
    if (String(session.id).startsWith("draft-")) {
      const created = await request("/api/sessions", {
        method: "POST",
        body: JSON.stringify({}),
      });
      state.activeSessionId = created.active_session_id;
      state.sessions = state.sessions.filter((item) => item.id !== session.id);
      upsertSession(created.session);
      promoteSession(state.activeSessionId);
      pendingId = appendOptimisticMessages(state.activeSessionId, previewContent, requestBody.images || []);
      renderAll();
    }

    const data = await request(requestPath, {
      method: "POST",
      body: JSON.stringify({
        session_id: state.activeSessionId,
        llm_settings: currentRequestSettings(),
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
  await ensureAudioInputAvailable();
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (error) {
    throw new Error(describeMicrophoneError(error));
  }
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

async function ensureAudioInputAvailable() {
  if (typeof navigator.mediaDevices.enumerateDevices !== "function") {
    return;
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const hasAudioInput = devices.some((device) => device.kind === "audioinput");
    if (devices.length > 0 && !hasAudioInput) {
      throw new Error("没有检测到可用麦克风");
    }
  } catch (error) {
    if (error instanceof Error && error.message === "没有检测到可用麦克风") {
      throw error;
    }
  }
}

function describeMicrophoneError(error) {
  const name = String(error?.name || "");
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "没有检测到可用麦克风";
  }
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "浏览器没有麦克风权限";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "麦克风正在被占用，或系统暂时无法访问";
  }
  if (name === "SecurityError") {
    return "当前页面不允许访问麦克风，请使用 localhost/127.0.0.1 或 HTTPS 打开";
  }
  if (name === "OverconstrainedError") {
    return "没有找到符合要求的麦克风设备";
  }
  return error?.message || "无法启动录音";
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
      llm_settings: currentRequestSettings(),
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

async function handleImageSelection(event) {
  const files = Array.from(event.target.files || []);
  refs.imageInput.value = "";
  await addImageFiles(files);
}

async function addImageFiles(files) {
  if (files.length <= 0) return;
  try {
    const availableSlots = Math.max(0, 4 - state.pendingImages.length);
    if (availableSlots <= 0) {
      setComposerStatus("最多只能添加 4 张图片", "error");
      return;
    }
    const selectedFiles = files.slice(0, availableSlots);
    const images = [];
    for (const file of selectedFiles) {
      images.push(await fileToImageAttachment(file));
    }
    state.pendingImages = [...state.pendingImages, ...images];
    setComposerStatus(`已添加 ${state.pendingImages.length} 张图片`);
    renderComposerState();
  } catch (error) {
    setComposerStatus(error.message || "图片添加失败", "error");
  }
}

function fileToImageAttachment(file) {
  const allowedTypes = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]);
  if (!allowedTypes.has(file.type)) {
    return Promise.reject(new Error(`不支持的图片类型：${file.type || file.name}`));
  }
  if (file.size > 5 * 1024 * 1024) {
    return Promise.reject(new Error("单张图片不能超过 5MB"));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const data = result.includes(",") ? result.split(",", 2)[1] : result;
      resolve({
        name: file.name,
        media_type: file.type,
        data,
      });
    };
    reader.onerror = () => reject(new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

async function handleComposerPaste(event) {
  const files = imageFilesFromClipboard(event.clipboardData);
  if (files.length <= 0) return;
  event.preventDefault();
  await addImageFiles(files);
}

function handleComposerDragOver(event) {
  if (imageFilesFromDataTransfer(event.dataTransfer).length <= 0) return;
  event.preventDefault();
}

async function handleComposerDrop(event) {
  const files = imageFilesFromDataTransfer(event.dataTransfer);
  if (files.length <= 0) return;
  event.preventDefault();
  await addImageFiles(files);
}

function imageFilesFromClipboard(clipboardData) {
  if (!clipboardData?.items) return [];
  return Array.from(clipboardData.items)
    .filter((item) => item.kind === "file" && String(item.type || "").startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter(Boolean);
}

function imageFilesFromDataTransfer(dataTransfer) {
  if (!dataTransfer?.files) return [];
  return Array.from(dataTransfer.files).filter((file) => String(file.type || "").startsWith("image/"));
}

refs.sendButton.addEventListener("click", sendMessage);
refs.newSessionButton.addEventListener("click", createSession);
refs.voiceButton.addEventListener("click", toggleVoiceRecording);
refs.attachImageButton.addEventListener("click", () => refs.imageInput.click());
refs.imageInput.addEventListener("change", handleImageSelection);
refs.settingsButton.addEventListener("click", openSettingsModal);
refs.settingsForm.addEventListener("submit", saveSettings);
refs.settingsCloseButton.addEventListener("click", closeSettingsModal);
refs.settingsCancelButton.addEventListener("click", closeSettingsModal);
refs.apiKeyToggleButton.addEventListener("click", toggleApiKeyVisibility);
refs.imageLightboxClose.addEventListener("click", closeImageLightbox);
refs.imageLightbox.addEventListener("click", (event) => {
  if (event.target === refs.imageLightbox) {
    closeImageLightbox();
  }
});
refs.settingsModal.addEventListener("click", (event) => {
  if (event.target === refs.settingsModal) {
    closeSettingsModal();
  }
});
refs.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
refs.messageInput.addEventListener("input", renderComposerState);
refs.messageInput.addEventListener("paste", handleComposerPaste);
refs.messageInput.addEventListener("dragover", handleComposerDragOver);
refs.messageInput.addEventListener("drop", handleComposerDrop);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !refs.settingsModal.hidden) {
    closeSettingsModal();
    return;
  }
  if (event.key === "Escape" && !refs.imageLightbox.hidden) {
    closeImageLightbox();
  }
});

bootstrap().catch((error) => {
  window.alert(`初始化失败：${error.message}`);
});
