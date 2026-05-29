/* remote.js */
function xhrRequest(url, options = {}) {
  const { method = "GET", headers = {}, body = null, onUploadProgress = null } = options;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.withCredentials = true;
    xhr.open(method, url, true);
    xhr.responseType = "json";
    Object.entries(headers).forEach(([key, value]) => {
      xhr.setRequestHeader(key, value);
    });
    xhr.onload = () => {
      let data = xhr.response;
      if (!data && xhr.responseText) {
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          data = null;
        }
      }
      if (xhr.status >= 200 && xhr.status < 300 && data && data.ok !== false) {
        resolve(data);
        return;
      }
      reject(buildRequestError(data, `请求失败 (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("网络请求失败"));
    if (xhr.upload && onUploadProgress) {
      xhr.upload.onprogress = (event) => {
        onUploadProgress(event.loaded, event.total, event.lengthComputable);
      };
    }
    xhr.send(body);
  });
}

function updateConnectionStatus(connected) {
  connectionState = Boolean(connected);
  statusText.textContent = connected ? "已连接" : "未连接";
  statusDot.classList.toggle("online", connected);
  statusDot.classList.toggle("offline", !connected);
}

function syncSessionIdentity(sessionId) {
  const normalizedSessionId = String(sessionId || "").trim();
  if (!normalizedSessionId) {
    return;
  }
  if (currentSessionId && currentSessionId !== normalizedSessionId) {
    clearChatClientState();
    appendLog("检测到会话已切换，已清空本地聊天缓存");
  }
  currentSessionId = normalizedSessionId;
}

async function refreshConnectionStatus() {
  const data = await request("/api/status");
  syncSessionIdentity(data.session_id);
  updateConnectionStatus(Boolean(data.connected));
  return Boolean(data.connected);
}

function getConnectField(name) {
  return connectForm.elements.namedItem(name);
}

function normalizeConnectionCacheItem(item) {
  if (!item || typeof item !== "object") {
    return null;
  }
  const host = String(item.host || "").trim();
  const port = String(item.port || "").trim() || DEFAULT_CONNECTION_FORM.port;
  const username = String(item.username || "").trim();
  const password = typeof item.password === "string" ? item.password : String(item.password || "");
  const picoHost = String(item.pico_host || "").trim();
  const picoPort = String(item.pico_port || "").trim() || DEFAULT_CONNECTION_FORM.pico_port;
  const picoUsername = String(item.pico_username || "").trim();
  const picoPassword = typeof item.pico_password === "string" ? item.pico_password : String(item.pico_password || "");
  if (!host || !username) {
    return null;
  }
  return {
    id: `${host}|${port}|${username}`,
    host,
    port,
    username,
    password,
    pico_host: picoHost,
    pico_port: picoPort,
    pico_username: picoUsername,
    pico_password: picoPassword,
    savedAt: String(item.savedAt || item.saved_at || ""),
  };
}

function buildSavedConnectionLabel(connection) {
  const picoPart = connection.pico_host
    ? ` · PICO ${connection.pico_host}:${connection.pico_port} · ${connection.pico_username || "-"}`
    : "";
  return `ORIN ${connection.host}:${connection.port} · ${connection.username}${picoPart}`;
}

function renderSavedConnectionSummary() {
  if (!savedConnectionSummary) {
    return;
  }
  const selectedConnection = savedConnectionsCache.find((connection) => connection.id === savedConnectionSelect?.value);
  const fallbackConnection = selectedConnection || savedConnectionsCache[0];
  if (!fallbackConnection) {
    savedConnectionSummary.textContent = "暂无缓存连接";
    return;
  }
  savedConnectionSummary.textContent = `最近使用 · ${buildSavedConnectionLabel(fallbackConnection)}`;
}

function findSavedConnectionIdForForm(connection) {
  if (!connection || typeof connection !== "object") {
    return "";
  }
  const normalizedForm = normalizeConnectionCacheItem(connection);
  if (!normalizedForm) {
    return "";
  }
  const matchedConnection = savedConnectionsCache.find((savedConnection) => (
    savedConnection.host === normalizedForm.host &&
    savedConnection.port === normalizedForm.port &&
    savedConnection.username === normalizedForm.username &&
    (savedConnection.pico_host || "") === (normalizedForm.pico_host || "") &&
    (savedConnection.pico_port || DEFAULT_CONNECTION_FORM.pico_port) === (normalizedForm.pico_port || DEFAULT_CONNECTION_FORM.pico_port) &&
    (savedConnection.pico_username || "") === (normalizedForm.pico_username || "")
  ));
  return matchedConnection?.id || "";
}

function setSavedConnections(connections, { selectedId = "" } = {}) {
  savedConnectionsCache = (Array.isArray(connections) ? connections : [])
    .map((item) => normalizeConnectionCacheItem(item))
    .filter(Boolean);
  renderSavedConnectionSelect(selectedId);
  renderSavedConnectionSummary();
}

function renderSavedConnectionSelect(selectedId = "") {
  if (!savedConnectionSelect) {
    return;
  }
  const currentValue = selectedId || savedConnectionSelect.value || "";
  savedConnectionSelect.replaceChildren();

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = savedConnectionsCache.length ? "选择已缓存连接" : "暂无缓存连接";
  savedConnectionSelect.appendChild(placeholder);

  savedConnectionsCache.forEach((connection, index) => {
    const option = document.createElement("option");
    option.value = connection.id;
    option.textContent = `${index === 0 ? "最近使用 · " : ""}${buildSavedConnectionLabel(connection)}`;
    savedConnectionSelect.appendChild(option);
  });

  if (savedConnectionsCache.some((connection) => connection.id === currentValue)) {
    savedConnectionSelect.value = currentValue;
  } else {
    savedConnectionSelect.value = "";
  }
  renderSavedConnectionSummary();
}

function readConnectionForm() {
  return {
    host: String(getConnectField("host").value || "").trim(),
    port: String(getConnectField("port").value || "").trim() || DEFAULT_CONNECTION_FORM.port,
    username: String(getConnectField("username").value || "").trim(),
    password: String(getConnectField("password").value || ""),
    pico_host: String(getConnectField("pico_host").value || "").trim(),
    pico_port: String(getConnectField("pico_port").value || "").trim() || DEFAULT_CONNECTION_FORM.pico_port,
    pico_username: String(getConnectField("pico_username").value || "").trim(),
    pico_password: String(getConnectField("pico_password").value || ""),
  };
}

function applyConnectionToForm(connection, { preservePassword = false } = {}) {
  if (!connection) {
    return;
  }
  getConnectField("host").value = connection.host;
  getConnectField("port").value = connection.port;
  getConnectField("username").value = connection.username;
  if (!preservePassword || !getConnectField("password").value) {
    getConnectField("password").value = connection.password;
  }
  getConnectField("pico_host").value = connection.pico_host || "";
  getConnectField("pico_port").value = connection.pico_port || DEFAULT_CONNECTION_FORM.pico_port;
  getConnectField("pico_username").value = connection.pico_username || "";
  if (!preservePassword || !getConnectField("pico_password").value) {
    getConnectField("pico_password").value = connection.pico_password || "";
  }
  if (savedConnectionSelect) {
    savedConnectionSelect.value = connection.id;
  }
  renderSavedConnectionSummary();
}

function isDefaultConnectionForm(connection) {
  return (
    connection.host === DEFAULT_CONNECTION_FORM.host &&
    connection.port === DEFAULT_CONNECTION_FORM.port &&
    connection.username === DEFAULT_CONNECTION_FORM.username &&
    connection.pico_host === DEFAULT_CONNECTION_FORM.pico_host &&
    connection.pico_port === DEFAULT_CONNECTION_FORM.pico_port &&
    connection.pico_username === DEFAULT_CONNECTION_FORM.pico_username &&
    !connection.password &&
    !connection.pico_password
  );
}

function hydrateConnectionCache(savedConnections = [], { forceApplyMostRecent = false } = {}) {
  const currentForm = readConnectionForm();
  const selectedId = findSavedConnectionIdForForm(currentForm);
  setSavedConnections(savedConnections, { selectedId });
  if (!savedConnectionsCache.length) {
    const fallbackConnection = normalizeConnectionCacheItem(currentForm);
    if (fallbackConnection && fallbackConnection.host && fallbackConnection.username) {
      setSavedConnections([fallbackConnection], { selectedId: fallbackConnection.id });
      applyConnectionToForm(fallbackConnection, { preservePassword: true });
    }
    return;
  }
  if (selectedId) {
    const matchedConnection = savedConnectionsCache.find((connection) => connection.id === selectedId);
    if (matchedConnection) {
      applyConnectionToForm(matchedConnection);
    }
    return;
  }
  if (!savedConnectionsCache.length) {
    return;
  }
  if (forceApplyMostRecent) {
    applyConnectionToForm(savedConnectionsCache[0]);
    return;
  }
  if (!isDefaultConnectionForm(currentForm) && currentForm.host) {
    return;
  }
  applyConnectionToForm(savedConnectionsCache[0]);
}

async function ensureSavedConnectionsCacheLoaded() {
  if (savedConnectionsCache.length) {
    return savedConnectionsCache;
  }
  const data = await request("/api/connection-cache");
  hydrateConnectionCache(data.saved_connections || []);
  return savedConnectionsCache;
}
/* remote.js */
function startSessionHeartbeat() {
  if (heartbeatTimer) {
    window.clearInterval(heartbeatTimer);
  }
  heartbeatTimer = window.setInterval(() => {
    refreshConnectionStatus().catch(() => {
      // ignore heartbeat failures and let user-facing requests surface issues
    });
  }, 60000);
}
/* remote.js */
passwordToggleButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const field = button.closest(".password-field");
    const input = field ? field.querySelector('input[type="password"], input[type="text"]') : null;
    if (!input) {
      return;
    }
    const isHidden = input.type === "password";
    input.type = isHidden ? "text" : "password";
    button.classList.toggle("is-visible", isHidden);
    button.setAttribute("aria-label", isHidden ? "隐藏密码" : "显示密码");
    button.setAttribute("title", isHidden ? "隐藏密码" : "显示密码");
  });
});
/* remote.js */
connectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  try {
    const data = await request("/api/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const selectedConnection = normalizeConnectionCacheItem(payload);
    hydrateConnectionCache(
      data.saved_connections || [],
      { forceApplyMostRecent: Boolean(selectedConnection) },
    );
    updateConnectionStatus(true);
    appendLog(
      "SSH 连接成功",
      `ORIN ${payload.username}@${payload.host}:${payload.port}${payload.pico_host ? `\nPICO ${payload.pico_username || "-"}@${payload.pico_host}:${payload.pico_port || DEFAULT_CONNECTION_FORM.pico_port}` : ""}`,
    );
    await syncRemoteDirectories({
      connected: true,
      shortcuts: data.remote_shortcuts,
      preferredRoot: data.preferred_root,
    });
  } catch (error) {
    appendLog("SSH 连接失败", error.message);
    alert(error.message);
  }
});

async function handleSavedConnectionSelection() {
  if (!savedConnectionSelect) {
    return;
  }
  const selectedId = String(savedConnectionSelect.value || "").trim();
  renderSavedConnectionSummary();
  if (!selectedId) {
    return;
  }
  if (!savedConnectionsCache.length) {
    try {
      await ensureSavedConnectionsCacheLoaded();
    } catch (error) {
      appendLog("加载连接缓存失败", error.message);
      alert(error.message);
      return;
    }
  }
  const selectedConnection = savedConnectionsCache.find((connection) => connection.id === selectedId);
  renderSavedConnectionSummary();
  if (!selectedConnection) {
    appendLog("未匹配到缓存连接", selectedId);
    return;
  }
  applyConnectionToForm(selectedConnection);
  appendLog("已填充缓存连接", buildSavedConnectionLabel(selectedConnection));
}

savedConnectionSelect.addEventListener("change", () => {
  handleSavedConnectionSelection().catch((error) => {
    appendLog("应用缓存连接失败", error.message);
    alert(error.message);
  });
});
savedConnectionSelect.addEventListener("input", () => {
  handleSavedConnectionSelection().catch((error) => {
    appendLog("应用缓存连接失败", error.message);
    alert(error.message);
  });
});

clearConnectionCacheBtn.addEventListener("click", async () => {
  try {
    const data = await request("/api/connection-cache/clear", { method: "POST" });
    setSavedConnections(data.saved_connections || []);
    appendLog("已清空连接缓存");
  } catch (error) {
    appendLog("清空连接缓存失败", error.message);
    alert(error.message);
  }
});

if (remoteCacheSelectShell && savedConnectionSelect) {
  remoteCacheSelectShell.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      savedConnectionSelect.focus();
      if (typeof savedConnectionSelect.showPicker === "function") {
        savedConnectionSelect.showPicker();
      }
    }
  });
}

document.getElementById("disconnectBtn").addEventListener("click", async () => {
  const wasConnected = connectionState;
  updateConnectionStatus(false);
  try {
    await request("/api/disconnect", { method: "POST" });
    clearChatClientState();
    await syncRemoteDirectories({ connected: false });
    appendLog("连接已断开");
  } catch (error) {
    updateConnectionStatus(wasConnected);
    appendLog("断开连接失败", error.message);
    alert(error.message);
  }
});
