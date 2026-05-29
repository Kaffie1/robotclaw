/* deploy.js */
function setPackageDeployHint(message, isError = false) {
  if (!packageDeployStageHint) {
    return;
  }
  packageDeployStageHint.textContent = message;
  packageDeployStageHint.classList.toggle("is-error", Boolean(isError));
  packageDeployStageHint.classList.toggle("is-attention", !isError && packageDeployStageState.stage === "continue");
}

function setPackageMachineAttention(active) {
  if (!packageMachineType) {
    return;
  }
  packageMachineType.classList.toggle("is-attention", Boolean(active));
}

function renderPackageMachineOptions(options = [], selectedValue = "", requireExplicitSelection = false) {
  if (!packageMachineType) {
    return;
  }
  packageMachineType.replaceChildren();
  if (!options.length) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "请先上传 firmware 并识别机型";
    packageMachineType.appendChild(placeholder);
    packageMachineType.value = "";
    packageMachineType.disabled = true;
    return;
  }
  if (requireExplicitSelection && !selectedValue) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "请选择机型";
    placeholder.selected = true;
    packageMachineType.appendChild(placeholder);
  }
  options.forEach((option, index) => {
    const item = document.createElement("option");
    item.value = String(option.value || "").trim();
    item.textContent = String(option.label || option.value || "").trim();
    if (!item.value) {
      return;
    }
    if ((selectedValue && item.value === selectedValue) || (!selectedValue && !requireExplicitSelection && index === 0)) {
      item.selected = true;
    }
    packageMachineType.appendChild(item);
  });
  packageMachineType.disabled = false;
}

function resetPackageDeployStage({ keepHint = false, keepMachineOptions = false, selectedMachineType = "" } = {}) {
  packageDeployStageState.stage = "upload";
  packageDeployStageState.taskId = "";
  packageDeployStageState.fileName = "";
  packageDeployStageState.remotePath = "";
  packageDeployStageState.remoteDir = "";
  packageDeployStageState.deviceType = String(packageDeviceType?.value || "ORIN").trim().toUpperCase() || "ORIN";
  if (!keepMachineOptions) {
    packageDeployStageState.machineOptions = [];
    renderPackageMachineOptions([]);
  } else {
    renderPackageMachineOptions(packageDeployStageState.machineOptions, selectedMachineType);
  }
  setPackageMachineAttention(false);
  if (packageDeploySubmitBtn) {
    packageDeploySubmitBtn.textContent = "创建整包部署任务";
  }
  if (!keepHint) {
    setPackageDeployHint("请先上传 firmware，上传完成后将自动识别可选机型。");
  }
}

function resetPackageDeployRuntimeState({ keepHint = false, keepMachineOptions = false, selectedMachineType = "" } = {}) {
  clearDeployTaskTracking("package");
  deployProgressSnapshots.package = null;
  lastFinishedDeployTasks.package = null;
  resetUploadProgress(uploadProgressViews.packageDeploy, "等待上传");
  renderDeployFlow(deployFlowViews.package, deriveDeployFlow(null, null, "package"));
  resetPackageDeployStage({
    keepHint,
    keepMachineOptions,
    selectedMachineType,
  });
}

function activatePackageDeployContinueStage({ taskId = "", fileName = "", remotePath = "", remoteDir = "", deviceType = "ORIN", machineOptions = [], selectedMachineType = "" } = {}) {
  packageDeployStageState.stage = "continue";
  packageDeployStageState.taskId = String(taskId || "").trim();
  packageDeployStageState.fileName = String(fileName || "").trim();
  packageDeployStageState.remotePath = String(remotePath || "").trim();
  packageDeployStageState.remoteDir = String(remoteDir || "").trim();
  packageDeployStageState.deviceType = String(deviceType || "ORIN").trim().toUpperCase() || "ORIN";
  packageDeployStageState.machineOptions = Array.isArray(machineOptions) ? machineOptions : [];
  const normalizedSelectedMachineType = String(selectedMachineType || "").trim();
  renderPackageMachineOptions(packageDeployStageState.machineOptions, normalizedSelectedMachineType);
  setPackageMachineAttention(false);
  if (packageDeploySubmitBtn) {
    packageDeploySubmitBtn.textContent = "继续部署";
  }
  if (normalizedSelectedMachineType) {
    setPackageDeployHint(`已读取远端 ROBOT_TYPE=${normalizedSelectedMachineType}，已默认选中该机型；如有需要仍可手动切换，确认后点击“继续部署”。`);
  } else {
    setPackageDeployHint("未读取到 ROBOT_TYPE，已默认选中第一个机型，请确认后点击“继续部署”。");
  }
  window.setTimeout(() => {
    if (!packageMachineType) {
      return;
    }
    packageMachineType.focus();
    if (typeof packageMachineType.showPicker === "function") {
      try {
        packageMachineType.showPicker();
      } catch {
        // ignore browsers that require stricter user activation timing
      }
    }
  }, 0);
}

function markPackageDeployFailed(message = "") {
  resetPackageDeployStage({ keepHint: true });
  setPackageMachineAttention(false);
  if (message) {
    setPackageDeployHint(`${message}，请重新上传 firmware 后再试。`, true);
  } else {
    setPackageDeployHint("部署失败，请重新上传 firmware 后再试。", true);
  }
}

function markModuleDeployFailed(message = "") {
  clearDeployTaskTracking("module");
  resetUploadProgress(uploadProgressViews.moduleDeploy, "等待上传");
  renderDeployFlow(deployFlowViews.module, deriveDeployFlow(null, null, "module"));
  if (moduleDeployFileInput) {
    moduleDeployFileInput.value = "";
  }
  setModuleDeployFileMeta(null);
  if (moduleDeployForm) {
    moduleDeployForm.reset();
  }
  const moduleSubmitBtn = moduleDeployForm?.querySelector('button[type="submit"]');
  if (moduleSubmitBtn instanceof HTMLButtonElement) {
    moduleSubmitBtn.disabled = false;
  }
  appendLog("模块部署失败", message || "请重新上传模块 deb 文件后再试。");
}
/* deploy.js */
function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function setPackageDeployFileMeta(file = null) {
  if (!packageDeployDropzone || !packageDeployFileMeta) {
    return;
  }
  if (!file) {
    packageDeployDropzone.classList.remove("has-file");
    packageDeployFileMeta.textContent = "当前未选择文件";
    return;
  }
  packageDeployDropzone.classList.add("has-file");
  packageDeployFileMeta.textContent = `${file.name} · ${formatBytes(file.size)}`;
}

function setPackageDeployFile(file = null) {
  if (!packageDeployFileInput) {
    return;
  }
  if (!file) {
    packageDeployFileInput.value = "";
    setPackageDeployFileMeta(null);
    return;
  }

  const transfer = new DataTransfer();
  transfer.items.add(file);
  packageDeployFileInput.files = transfer.files;
  setPackageDeployFileMeta(file);
}

function setModuleDeployFileMeta(file = null) {
  if (!moduleDeployDropzone || !moduleDeployFileMeta) {
    return;
  }
  if (!file) {
    moduleDeployDropzone.classList.remove("has-file");
    moduleDeployFileMeta.textContent = "当前未选择文件";
    return;
  }
  moduleDeployDropzone.classList.add("has-file");
  moduleDeployFileMeta.textContent = `${file.name} · ${formatBytes(file.size)}`;
}

function setModuleDeployFile(file = null) {
  if (!moduleDeployFileInput) {
    return;
  }
  if (!file) {
    moduleDeployFileInput.value = "";
    setModuleDeployFileMeta(null);
    return;
  }

  const transfer = new DataTransfer();
  transfer.items.add(file);
  moduleDeployFileInput.files = transfer.files;
  setModuleDeployFileMeta(file);
}

function createUploadProgressView(id) {
  const root = document.getElementById(id);
  if (!root) {
    return null;
  }
  return {
    root,
    bar: root.querySelector(".upload-progress-bar"),
    percent: root.querySelector(".upload-progress-percent"),
    text: root.querySelector(".upload-progress-text"),
    meta: root.querySelector(".upload-progress-meta"),
  };
}

function createDeployFlowView(id) {
  const root = document.getElementById(id);
  if (!root) {
    return null;
  }
  const steps = {};
  root.querySelectorAll("[data-flow-step]").forEach((item) => {
    steps[item.dataset.flowStep] = item;
  });
  return {
    root,
    status: root.querySelector(".deploy-flow-status"),
    steps,
  };
}

uploadProgressViews = {
  packageDeploy: createUploadProgressView("packageDeployUploadProgress"),
  moduleDeploy: createUploadProgressView("moduleDeployUploadProgress"),
};
deployFlowViews = {
  package: createDeployFlowView("packageDeployFlow"),
  module: createDeployFlowView("moduleDeployFlow"),
};

function deployActionLabel(deployMode = "package") {
  return "安装";
}

function deployFileNoun(deployMode = "package") {
  if (deployMode === "package") {
    return "firmware 文件";
  }
  if (deployMode === "module") {
    return "模块 deb 文件";
  }
  return "部署文件";
}

function setDeployFlowStepState(step, state = "pending") {
  if (!step) {
    return;
  }
  step.classList.toggle("is-active", state === "active");
  step.classList.toggle("is-done", state === "done");
  step.classList.toggle("is-error", state === "error");
}

function renderDeployFlow(view, { summary = "等待开始", stepStates = {} } = {}) {
  if (!view || !view.root) {
    return;
  }
  if (view.status) {
    view.status.textContent = summary;
  }
  ["uploading", "installing", "succeeded", "failed"].forEach((stepKey) => {
    setDeployFlowStepState(view.steps[stepKey], stepStates[stepKey] || "pending");
  });
}

function isDeployTask(task, deployMode) {
  return task && task.type === "deployment" && task.metadata && task.metadata.deploy_mode === deployMode;
}

function clearDeployTaskTracking(deployMode) {
  if (deployMode === "package" || deployMode === "module") {
    currentDeployTaskIds[deployMode] = "";
  }
}

function findCurrentDeployTask(tasks = [], deployMode) {
  if (currentDeployTaskIds[deployMode]) {
    const currentTask = tasks.find((task) => task.id === currentDeployTaskIds[deployMode]);
    if (currentTask) {
      return currentTask;
    }
    clearDeployTaskTracking(deployMode);
  }
  if (deployMode === "package" && packageDeployRequestInFlight) {
    return null;
  }
  const latestTask = tasks.find((task) => isDeployTask(task, deployMode) && !isTaskFinished(task));
  if (latestTask) {
    currentDeployTaskIds[deployMode] = latestTask.id;
    return latestTask;
  }
  return null;
}

function deriveDeployFlow(task = null, progress = null, deployMode = "package") {
  const actionLabel = deployActionLabel(deployMode);
  const stepStates = {
    uploading: "pending",
    installing: "pending",
    succeeded: "pending",
    failed: "pending",
  };
  let summary = "等待开始";

  const taskStatus = String(task && task.status ? task.status : "");
  const taskError = String(task && task.error ? task.error : "");
  const taskResult = task && task.result && typeof task.result === "object" ? task.result : {};
  const uploadDone = Boolean(progress && progress.done);
  const progressPhase = String(progress && progress.phase ? progress.phase : "").trim().toLowerCase();
  const progressMessage = String(progress && progress.message ? progress.message : "");
  const progressError = String(progress && progress.error ? progress.error : "");
  const installLikeProgressPhases = new Set(["installing", "probing_machine_type", "probing_options", "waiting_confirmation"]);
  const installStarted =
    taskStatus === "succeeded" ||
    taskStatus === "waiting_confirmation" ||
    Boolean(taskResult.install_result) ||
    taskError.includes("安装") ||
    taskError.includes("健康检查") ||
    taskError.includes("启动") ||
    installLikeProgressPhases.has(progressPhase) ||
    progressMessage.includes("识别机型") ||
    progressMessage.includes("探测整包可选参数") ||
    progressMessage.includes("安装") ||
    progressMessage.includes("等待确认") ||
    progressError.includes("识别") ||
    progressError.includes("安装");

  if (progress && progress.phase === "failed") {
    if (installStarted) {
      stepStates.uploading = "done";
      stepStates.installing = "error";
      stepStates.failed = "error";
      summary = `${actionLabel}失败`;
    } else {
      stepStates.uploading = "error";
      stepStates.failed = "error";
      summary = "上传失败";
    }
    return { summary, stepStates };
  }

  if (taskStatus === "succeeded" || taskStatus === "warning") {
    stepStates.uploading = "done";
    stepStates.installing = "done";
    stepStates.succeeded = "done";
    summary = taskStatus === "warning" ? `${actionLabel}成功（有告警）` : `${actionLabel}成功`;
    return { summary, stepStates };
  }

  if (taskStatus === "failed") {
    if (uploadDone || installStarted) {
      stepStates.uploading = "done";
      stepStates.installing = "error";
      stepStates.failed = "error";
      summary = `${actionLabel}失败`;
    } else {
      stepStates.uploading = "error";
      stepStates.failed = "error";
      summary = "上传失败";
    }
    return { summary, stepStates };
  }

  if (taskStatus === "waiting_confirmation") {
    stepStates.uploading = "done";
    stepStates.installing = "active";
    summary = "等待确认";
    return { summary, stepStates };
  }

  if (taskStatus === "running") {
    if (uploadDone || installStarted) {
      stepStates.uploading = "done";
      stepStates.installing = "active";
      summary = `${actionLabel}中`;
    } else {
      stepStates.uploading = "active";
      summary = "上传中";
    }
    return { summary, stepStates };
  }

  if (taskStatus === "pending") {
    if (uploadDone || installStarted) {
      stepStates.uploading = "done";
      stepStates.installing = "active";
      summary = `${actionLabel}中`;
    } else {
      stepStates.uploading = "active";
      summary = "上传中";
    }
    return { summary, stepStates };
  }

  if (progress) {
    if (installLikeProgressPhases.has(progressPhase)) {
      stepStates.uploading = "done";
      stepStates.installing = "active";
      if (progressPhase === "probing_machine_type" || progressPhase === "probing_options") {
        summary = "识别机型中";
      } else if (progressPhase === "waiting_confirmation") {
        summary = "等待确认";
      } else {
        summary = `${actionLabel}中`;
      }
    } else if (progress.done) {
      stepStates.uploading = "done";
      summary = "上传完成";
    } else {
      stepStates.uploading = "active";
      if (progressPhase === "downloading_from_server") {
        summary = "下载中";
      } else if (progressPhase === "preparing" || progressPhase === "checking_remote" || progressPhase === "cleaning_remote") {
        summary = "准备中";
      } else {
        summary = "上传中";
      }
    }
  }
  return { summary, stepStates };
}

function syncDeployFlow(deployMode, { tasks = null, task = null, progress } = {}) {
  if (progress !== undefined) {
    deployProgressSnapshots[deployMode] = progress;
  }

  let resolvedTask = task;
  if (!resolvedTask && Array.isArray(tasks)) {
    resolvedTask = findCurrentDeployTask(tasks, deployMode);
  }
  if (!resolvedTask && (deployMode === "package" || deployMode === "module")) {
    resolvedTask = lastFinishedDeployTasks[deployMode];
  }
  if (resolvedTask && isDeployTask(resolvedTask, deployMode)) {
    if (resolvedTask.progress && typeof resolvedTask.progress === "object") {
      deployProgressSnapshots[deployMode] = resolvedTask.progress;
    }
    if (isTaskFinished(resolvedTask)) {
      lastFinishedDeployTasks[deployMode] = resolvedTask;
    } else {
      currentDeployTaskIds[deployMode] = resolvedTask.id;
    }
  }

  const resolvedStatus = String(resolvedTask && resolvedTask.status ? resolvedTask.status : "").trim().toLowerCase();
  if (resolvedTask && isDeployTask(resolvedTask, deployMode) && isTaskFinished(resolvedTask)) {
    clearDeployTaskTracking(deployMode);
  }

  if (deployMode === "package" && resolvedTask && resolvedStatus === "failed") {
    markPackageDeployFailed(String(resolvedTask.error || "部署失败，请查看后台日志"));
  } else if (deployMode === "module" && resolvedTask && resolvedStatus === "failed") {
    markModuleDeployFailed(String(resolvedTask.error || "部署失败，请查看后台日志"));
  }

  const derivedFlow = deriveDeployFlow(resolvedTask, deployProgressSnapshots[deployMode], deployMode);
  console.log("[syncDeployFlow]", {
    deployMode,
    resolvedTaskId: resolvedTask?.id || "",
    resolvedStatus,
    currentDeployTaskId: currentDeployTaskIds[deployMode],
    progress: deployProgressSnapshots[deployMode] || null,
    derivedFlow,
  });
  if (deployMode === "package" && deployProgressSnapshots.package) {
    renderProgressSnapshot(uploadProgressViews.packageDeploy, deployProgressSnapshots.package);
  } else if (deployMode === "module" && deployProgressSnapshots.module) {
    renderProgressSnapshot(uploadProgressViews.moduleDeploy, deployProgressSnapshots.module);
  }
  renderDeployFlow(deployFlowViews[deployMode], derivedFlow);
}

function renderUploadProgress(view, { percent = 0, text = "等待开始", meta = "", state = "active" }) {
  if (!view || !view.root) {
    return;
  }
  const safePercent = Math.max(0, Math.min(100, Number(percent || 0)));
  view.root.hidden = false;
  view.root.classList.toggle("is-success", state === "success");
  view.root.classList.toggle("is-error", state === "error");
  view.bar.style.width = `${safePercent}%`;
  view.percent.textContent = `${Math.round(safePercent)}%`;
  view.text.textContent = text;
  view.meta.textContent = meta;
}

function resetUploadProgress(view, title) {
  if (!view) {
    return;
  }
  renderUploadProgress(view, { percent: 0, text: title, meta: "等待开始", state: "active" });
}

Object.values(uploadProgressViews)
  .filter(Boolean)
  .forEach((view) => {
    resetUploadProgress(view, "等待上传");
  });
renderDeployFlow(deployFlowViews.package, deriveDeployFlow(null, null, "package"));
renderDeployFlow(deployFlowViews.module, deriveDeployFlow(null, null, "module"));
setPackageDeployFileMeta(packageDeployFileInput && packageDeployFileInput.files ? packageDeployFileInput.files[0] : null);
resetPackageDeployStage({ keepHint: true });
setModuleDeployFileMeta(moduleDeployFileInput && moduleDeployFileInput.files ? moduleDeployFileInput.files[0] : null);

if (packageDeployDropzone && packageDeployFileInput) {
  packageDeployDropzone.addEventListener("click", () => {
    packageDeployFileInput.click();
  });

  packageDeployDropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      packageDeployFileInput.click();
    }
  });

  packageDeployFileInput.addEventListener("change", () => {
    setPackageDeployFileMeta(packageDeployFileInput.files && packageDeployFileInput.files[0] ? packageDeployFileInput.files[0] : null);
    resetPackageDeployRuntimeState();
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    packageDeployDropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      packageDeployDropzone.classList.add("is-dragover");
    });
  });

  ["dragleave", "dragend"].forEach((eventName) => {
    packageDeployDropzone.addEventListener(eventName, () => {
      packageDeployDropzone.classList.remove("is-dragover");
    });
  });

  packageDeployDropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    packageDeployDropzone.classList.remove("is-dragover");
    const droppedFiles = event.dataTransfer && event.dataTransfer.files ? Array.from(event.dataTransfer.files) : [];
    const selectedFile = droppedFiles.find((file) => file && file.name);
    if (!selectedFile) {
      return;
    }
    setPackageDeployFile(selectedFile);
    resetPackageDeployRuntimeState();
    appendLog("已拖入整包部署文件", selectedFile.name);
  });
}

packageDeviceType?.addEventListener("change", () => {
  resetPackageDeployRuntimeState();
});

const packageServerFilePathInput = packageDeployForm?.elements?.namedItem("server_file_path");
if (packageServerFilePathInput instanceof HTMLInputElement) {
  packageServerFilePathInput.addEventListener("input", () => {
    resetPackageDeployRuntimeState();
  });
}

if (moduleDeployDropzone && moduleDeployFileInput) {
  moduleDeployDropzone.addEventListener("click", () => {
    moduleDeployFileInput.click();
  });

  moduleDeployDropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      moduleDeployFileInput.click();
    }
  });

  moduleDeployFileInput.addEventListener("change", () => {
    setModuleDeployFileMeta(moduleDeployFileInput.files && moduleDeployFileInput.files[0] ? moduleDeployFileInput.files[0] : null);
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    moduleDeployDropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      moduleDeployDropzone.classList.add("is-dragover");
    });
  });

  ["dragleave", "dragend"].forEach((eventName) => {
    moduleDeployDropzone.addEventListener(eventName, () => {
      moduleDeployDropzone.classList.remove("is-dragover");
    });
  });

  moduleDeployDropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    moduleDeployDropzone.classList.remove("is-dragover");
    const droppedFiles = event.dataTransfer && event.dataTransfer.files ? Array.from(event.dataTransfer.files) : [];
    const selectedFile = droppedFiles.find((file) => file && file.name);
    if (!selectedFile) {
      return;
    }
    setModuleDeployFile(selectedFile);
    appendLog("已拖入模块部署文件", selectedFile.name);
  });
}

function buildUploadToken(prefix) {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return `${prefix}-${window.crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function buildShortcutLabel(shortcut) {
  const suffix = shortcut.display_path && shortcut.display_path !== shortcut.path ? ` · ${shortcut.display_path}` : "";
  const existsText = shortcut.exists === false ? "（未找到）" : "";
  return `${shortcut.label}${suffix}${existsText}`;
}

function buildDirectoryOptions() {
  const options = [];
  const seen = new Set();

  function pushOption(path, label) {
    if (!path || seen.has(path)) {
      return;
    }
    seen.add(path);
    options.push({ path, label });
  }

  remoteShortcutsCache.filter((shortcut) => shortcut.exists !== false).forEach((shortcut) => {
    pushOption(shortcut.path, buildShortcutLabel(shortcut));
  });
  rememberedRemoteDirs.forEach((label, path) => {
    pushOption(path, label);
  });
  pushOption(DEFAULT_PROJECT_ROOT, `项目默认目录 · ${DEFAULT_PROJECT_ROOT}`);
  pushOption("/tmp", "临时目录 /tmp");
  pushOption("/", "根目录 /");
  return options;
}

function renderRemoteDirectorySelects() {
  const options = buildDirectoryOptions();
  remoteDirSelects.forEach((select) => {
    const currentValue = select.value || select.dataset.defaultValue || preferredRootCache || "/tmp";
    select.replaceChildren();
    options.forEach((option) => {
      const item = document.createElement("option");
      item.value = option.path;
      item.textContent = option.label;
      select.appendChild(item);
    });
    if (!options.some((option) => option.path === currentValue)) {
      const customOption = document.createElement("option");
      customOption.value = currentValue;
      customOption.textContent = `当前目录 · ${currentValue}`;
      select.appendChild(customOption);
    }
    select.value = currentValue;
  });
}

function rememberRemoteDirectory(path, label = path) {
  if (!path) {
    return;
  }
  rememberedRemoteDirs.set(path, label);
  renderRemoteDirectorySelects();
}

function rememberLoadedDirectoryOptions(rootPath, entries = []) {
  rememberRemoteDirectory(rootPath, `当前目录 · ${rootPath}`);
  entries
    .filter((entry) => entry && entry.is_dir)
    .forEach((entry) => {
      rememberRemoteDirectory(entry.path, `子目录 · ${entry.path}`);
    });
}

function selectRemoteDirectory(path, label = `浏览目录 · ${path}`) {
  rememberRemoteDirectory(path, label);
  remoteDirSelects.forEach((select) => {
    select.value = path;
  });
}

async function syncRemoteDirectories({ connected, shortcuts = null, preferredRoot = null, autoload = false } = {}) {
  if (!connected) {
    remoteShortcutsCache = [];
    preferredRootCache = "/tmp";
    rememberedRemoteDirs.clear();
    renderRemoteDirectorySelects();
    return;
  }

  let nextShortcuts = shortcuts;
  let nextPreferredRoot = preferredRoot;
  if (!nextShortcuts) {
    const data = await request("/api/remote-shortcuts");
    nextShortcuts = data.shortcuts || [];
    nextPreferredRoot = data.preferred_root || "/tmp";
  }

  remoteShortcutsCache = nextShortcuts;
  preferredRootCache = nextPreferredRoot || "/tmp";
  renderRemoteDirectorySelects();

  if (autoload && preferredRootCache) {
    try {
      await loadRemoteDirectoryOptions(preferredRootCache);
    } catch (error) {
      appendLog("默认部署目录加载失败", error.message);
    }
  }
}

function uploadPhaseLabel(phase) {
  const map = {
    pending: "等待开始",
    queued: "部署任务已创建，等待上传",
    preparing: "正在准备上传",
    checking_remote: "正在检查远端同名包",
    cleaning_remote: "正在清理远端旧包",
    downloading_from_server: "正在从文件服务器下载",
    backing_up: "正在备份远端文件",
    uploading_to_robot: "正在上传到机器人",
    installing: "上传完成，正在执行安装",
    probing_machine_type: "安装包已上传，正在识别机型",
    probing_options: "安装包已上传，正在识别机型",
    waiting_confirmation: "等待确认",
    completed: "上传流程已完成",
    failed: "上传失败",
  };
  return map[phase] || "处理中";
}

function syncDeployFlowForUploadView(view, progress) {
  if (view === uploadProgressViews.packageDeploy) {
    syncDeployFlow("package", { progress });
  } else if (view === uploadProgressViews.moduleDeploy) {
    syncDeployFlow("module", { progress });
  }
}

function applyServerProgress(view, progress) {
  if (!progress) {
    return false;
  }
  syncDeployFlowForUploadView(view, progress);
  return renderProgressSnapshot(view, progress);
}

function renderProgressSnapshot(view, progress) {
  if (!progress) {
    return false;
  }
  const percent = progress.phase === "completed" ? 100 : Number(progress.percent || 0);
  const detailParts = [];
  if (progress.total_bytes) {
    detailParts.push(`${formatBytes(progress.transferred_bytes)} / ${formatBytes(progress.total_bytes)}`);
  }
  if (progress.file_name) {
    detailParts.push(progress.file_name);
  }
  renderUploadProgress(view, {
    percent,
    text: progress.message || uploadPhaseLabel(progress.phase),
    meta: detailParts.join(" · "),
    state: progress.phase === "failed" ? "error" : progress.done ? "success" : "active",
  });
  return Boolean(progress.done);
}

function startUploadProgressPolling(token, view) {
  let stopped = false;

  async function poll() {
    while (!stopped) {
      try {
        const data = await request(`/api/upload-progress/${encodeURIComponent(token)}`);
        if (applyServerProgress(view, data.progress)) {
          break;
        }
      } catch {
        // ignore transient polling issues
      }
      await new Promise((resolve) => window.setTimeout(resolve, 450));
    }
  }

  poll();
  return () => {
    stopped = true;
  };
}

async function finalizeUploadProgress(view, uploadToken, successText, stopPolling) {
  stopPolling();
  try {
    const progressData = await request(`/api/upload-progress/${encodeURIComponent(uploadToken)}`);
    if (applyServerProgress(view, progressData.progress)) {
      return;
    }
  } catch {
    // fall through to client-side success state
  }
  renderUploadProgress(view, {
    percent: 100,
    text: successText || "上传流程已完成",
    meta: "",
    state: "success",
  });
}

async function submitUploadWithProgress(
  url,
  formData,
  view,
  tokenPrefix,
  {
    skipBrowserUpload = false,
    reuseRemoteText = "已复用文件服务器包，准备进入部署工作流",
    browserCompleteText = "浏览器上传已完成，等待后台继续处理",
    remoteReuseProgressText = "已复用远端安装包，正在进入安装流程",
  } = {},
) {
  const uploadToken = buildUploadToken(tokenPrefix);
  formData.set("upload_token", uploadToken);
  resetUploadProgress(view, skipBrowserUpload ? reuseRemoteText : "等待上传");
  syncDeployFlowForUploadView(view, {
    phase: skipBrowserUpload ? "preparing" : "queued",
    done: false,
    message: skipBrowserUpload ? reuseRemoteText : "浏览器正在上传到控制台",
  });
  const stopPolling = startUploadProgressPolling(uploadToken, view);

  try {
    const data = await xhrRequest(url, {
      method: "POST",
      body: formData,
      onUploadProgress: (loaded, total, lengthComputable) => {
        if (skipBrowserUpload) {
          return;
        }
        const percent = lengthComputable && total > 0 ? (loaded / total) * 100 : 0;
        const meta = lengthComputable && total > 0 ? `${formatBytes(loaded)} / ${formatBytes(total)}` : formatBytes(loaded);
        syncDeployFlowForUploadView(view, {
          phase: "queued",
          done: false,
          percent,
          transferred_bytes: loaded,
          total_bytes: total,
          message: loaded >= total && total > 0 ? "浏览器上传完成，等待机器人上传" : "浏览器正在上传到控制台",
        });
        renderUploadProgress(view, {
          percent,
          text: loaded >= total && total > 0 ? "浏览器上传完成，等待机器人上传" : "浏览器正在上传到控制台",
          meta,
          state: "active",
        });
      },
    });
    if (data.task) {
      stopPolling();
      renderUploadProgress(view, {
        percent: 100,
        text: skipBrowserUpload ? remoteReuseProgressText : browserCompleteText,
        meta: `${data.task.title} (${data.task.id})`,
        state: "active",
      });
    } else {
      await finalizeUploadProgress(view, uploadToken, data.message || "上传流程已完成", stopPolling);
    }
    return data;
  } catch (error) {
    stopPolling();
    renderUploadProgress(view, {
      percent: 0,
      text: "上传失败",
      meta: error.message,
      state: "error",
    });
    throw error;
  }
}

function isTaskFinished(task) {
  const status = String(task?.status || "").trim().toLowerCase();
  return status === "succeeded" || status === "warning" || status === "failed";
}

function isTaskWaitingConfirmation(task) {
  return String(task?.status || "").trim().toLowerCase() === "waiting_confirmation";
}

async function waitForTaskCheckpoint(taskId, { pollMs = 1500 } = {}) {
  const resolvedTaskId = String(taskId || "").trim();
  if (!resolvedTaskId) {
    throw new Error("任务 ID 为空，无法等待任务状态变化");
  }
  while (true) {
    const data = await request(`/api/tasks/${resolvedTaskId}`);
    const task = data?.task || null;
    if (!task) {
      throw new Error(`未找到任务: ${resolvedTaskId}`);
    }
    selectedTaskId = resolvedTaskId;
    renderTaskDetail(task);
    if (task.type === "deployment") {
      const deployMode = String(task?.metadata?.deploy_mode || "").trim();
      if (deployMode === "package" || deployMode === "module") {
        syncDeployFlow(deployMode, { task });
      }
    }
    if (isTaskFinished(task) || isTaskWaitingConfirmation(task)) {
      await refreshDashboard();
      return task;
    }
    await refreshDashboard();
    await new Promise((resolve) => window.setTimeout(resolve, pollMs));
  }
}

async function waitForTaskCompletion(taskId, { pollMs = 1500 } = {}) {
  const resolvedTaskId = String(taskId || "").trim();
  if (!resolvedTaskId) {
    throw new Error("任务 ID 为空，无法等待任务完成");
  }
  while (true) {
    const data = await request(`/api/tasks/${resolvedTaskId}`);
    const task = data?.task || null;
    if (!task) {
      throw new Error(`未找到任务: ${resolvedTaskId}`);
    }
    console.log("[waitForTaskCompletion.poll]", {
      taskId: resolvedTaskId,
      status: task.status,
      finishedAt: task.finished_at,
      deployMode: task?.metadata?.deploy_mode || "",
    });
    selectedTaskId = resolvedTaskId;
    renderTaskDetail(task);
    if (task.type === "deployment") {
      const deployMode = String(task?.metadata?.deploy_mode || "").trim();
      if (deployMode === "package" || deployMode === "module") {
        syncDeployFlow(deployMode, { task });
      }
    }
    if (isTaskFinished(task)) {
      const deployMode = String(task?.metadata?.deploy_mode || "").trim();
      if (deployMode === "package" || deployMode === "module") {
        lastFinishedDeployTasks[deployMode] = task;
      }
      clearDeployTaskTracking(deployMode);
      await refreshDashboard();
      return task;
    }
    await refreshDashboard();
    await new Promise((resolve) => window.setTimeout(resolve, pollMs));
  }
}

function finalizeUploadProgressFromTask(view, task) {
  const status = String(task?.status || "").trim().toLowerCase();
  if (!view || !status) {
    return;
  }
  if (status === "failed") {
    renderUploadProgress(view, {
      percent: 100,
      text: "任务执行失败",
      meta: String(task?.error || "请查看后台日志"),
      state: "error",
    });
    return;
  }
  if (status === "succeeded" || status === "warning") {
    renderUploadProgress(view, {
      percent: 100,
      text: status === "warning" ? "任务执行完成（有告警）" : "任务执行完成",
      meta: String(task?.id || ""),
      state: "success",
    });
  }
}

function extractFileNameFromServerPath(rawPath) {
  const text = String(rawPath || "").trim().replaceAll("\\", "/");
  if (!text) {
    return "";
  }
  const normalized = text.split("?")[0].split("#")[0];
  const segments = normalized.split("/").filter(Boolean);
  return segments.length ? segments[segments.length - 1] : "";
}

async function resolveDeployConflict(
  formData,
  deployMode,
  progressView,
  {
    fileFieldName = "deb_file",
    serverPathFieldName = "server_file_path",
  } = {},
) {
  const selectedFile = formData.get(fileFieldName);
  const serverFilePath = String(formData.get(serverPathFieldName) || "").trim();
  const selectedFileName =
    selectedFile instanceof File && selectedFile.name ? selectedFile.name : extractFileNameFromServerPath(serverFilePath);
  if (!selectedFileName) {
    throw new Error(`请选择${deployFileNoun(deployMode)}`);
  }

  if (deployMode === "package") {
    formData.delete("replace_existing");
    formData.delete("use_existing_remote");
    return { cancelled: false, skipBrowserUpload: Boolean(serverFilePath) };
  }

  const params = new URLSearchParams({
    file_name: selectedFileName,
    machine_type: String(formData.get("machine_type") || "").trim(),
  });
  if (deployMode === "package") {
    params.set("device_type", String(formData.get("device_type") || "ORIN").trim() || "ORIN");
  }
  const target = await request(`/api/deploy-target?${params.toString()}`);
  formData.set("file_name", target.file_name || selectedFileName);

  if (!target.exists) {
    return { cancelled: false, skipBrowserUpload: Boolean(serverFilePath) };
  }

  const replaceExisting = window.confirm(
    `远端已存在同名文件：\n${target.remote_path}\n\n是否替换该文件并继续执行后续部署？`,
  );
  if (replaceExisting) {
    formData.set("replace_existing", "true");
    appendLog("检测到远端同名文件，用户选择替换", target.remote_path);
    return { cancelled: false, skipBrowserUpload: Boolean(serverFilePath) };
  }

  const installExisting = window.confirm(
    `已保留远端现有文件：\n${target.remote_path}\n\n是否直接使用这个远端文件继续执行${deployActionLabel(deployMode)}？`,
  );
  if (!installExisting) {
    renderUploadProgress(progressView, {
      percent: 0,
      text: "已取消部署",
      meta: `保留远端文件：${target.remote_path}`,
      state: "active",
    });
    appendLog("部署已取消", `远端同名文件未替换，且未继续${deployActionLabel(deployMode)}：${target.remote_path}`);
    return { cancelled: true, skipBrowserUpload: true };
  }

  formData.set("use_existing_remote", "true");
  formData.delete(fileFieldName);
  renderUploadProgress(progressView, {
    percent: 100,
    text: `已跳过上传，准备直接${deployActionLabel(deployMode)}远端同名文件`,
    meta: target.remote_path,
    state: "active",
  });
  appendLog(`检测到远端同名文件，用户选择直接${deployActionLabel(deployMode)}`, target.remote_path);
  return { cancelled: false, skipBrowserUpload: true };
}

async function resolveDeployConflictFromError(
  formData,
  progressView,
  error,
  {
    fileFieldName = "deb_file",
    serverPathFieldName = "server_file_path",
    deployMode = "package",
  } = {},
) {
  const conflict = error && error.conflict;
  if (!conflict || !conflict.remote_path) {
    return { handled: false };
  }

  if (deployMode === "package") {
    return { handled: false };
  }

  const replaceExisting = window.confirm(
    `远端已存在同名文件：\n${conflict.remote_path}\n\n是否替换该文件并继续执行后续部署？`,
  );
  if (replaceExisting) {
    formData.set("replace_existing", "true");
    formData.delete("use_existing_remote");
    appendLog("后端检测到远端同名文件，用户选择替换", conflict.remote_path);
    return { handled: true, cancelled: false, skipBrowserUpload: Boolean(formData.get(serverPathFieldName)) };
  }

  const installExisting = window.confirm(
    `已保留远端现有文件：\n${conflict.remote_path}\n\n是否直接使用这个远端文件继续执行${deployActionLabel(deployMode)}？`,
  );
  if (!installExisting) {
    renderUploadProgress(progressView, {
      percent: 0,
      text: "已取消部署",
      meta: `保留远端文件：${conflict.remote_path}`,
      state: "active",
    });
    appendLog("部署已取消", `远端同名文件未替换，且未继续${deployActionLabel(deployMode)}：${conflict.remote_path}`);
    return { handled: true, cancelled: true, skipBrowserUpload: true };
  }

  formData.set("use_existing_remote", "true");
  formData.delete("replace_existing");
  formData.delete(fileFieldName);
  renderUploadProgress(progressView, {
    percent: 100,
    text: `已跳过上传，准备直接${deployActionLabel(deployMode)}远端同名文件`,
    meta: conflict.remote_path,
    state: "active",
  });
  appendLog(`后端检测到远端同名文件，用户选择直接${deployActionLabel(deployMode)}`, conflict.remote_path);
  return { handled: true, cancelled: false, skipBrowserUpload: true };
}

function createActionButton(text, className, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = text;
  button.addEventListener("click", handler);
  return button;
}

function createStatusPill(status) {
  const pill = document.createElement("span");
  const labelMap = {
    pending: "等待中",
    running: "执行中",
    warning: "成功（有告警）",
    succeeded: "成功",
    failed: "失败",
  };
  pill.className = `status-pill status-${status}`;
  pill.textContent = labelMap[status] || status;
  return pill;
}

function createEmptyState(text) {
  const empty = document.createElement("div");
  empty.className = "record-empty";
  empty.textContent = text;
  return empty;
}

function resolveRemoteDirectoryTarget(selectedPath) {
  if (selectedPath && selectedPath !== "/tmp" && selectedPath !== "/") {
    return selectedPath;
  }
  return (
    remoteShortcutsCache.find((shortcut) => shortcut.path === DEFAULT_PROJECT_ROOT && shortcut.exists !== false)?.path ||
    (preferredRootCache && preferredRootCache !== "/" ? preferredRootCache : DEFAULT_PROJECT_ROOT)
  );
}

async function loadRemoteDirectoryOptions(path) {
  appendLog("加载部署目录", path);
  const data = await request(`/api/list-dir?path=${encodeURIComponent(path)}`);
  const resolvedPath = data.resolved_path || path;
  rememberLoadedDirectoryOptions(resolvedPath, data.entries || []);
  selectRemoteDirectory(resolvedPath, `当前目录 · ${resolvedPath}`);
  const childDirectoryCount = (data.entries || []).filter((entry) => entry && entry.is_dir).length;
  appendLog("部署目录下拉已更新", `${resolvedPath}（已加入 ${childDirectoryCount} 个一级子目录）`);
  return data;
}

async function loadRemoteDirectoryFromSelect(selectId) {
  const select = document.getElementById(selectId);
  if (!select) {
    return;
  }
  const selectedPath = select.value.trim();
  if (!selectedPath) {
    throw new Error("请先选择远程目录");
  }
  const targetPath = resolveRemoteDirectoryTarget(selectedPath);
  const data = await loadRemoteDirectoryOptions(targetPath);
  const resolvedTargetPath = data.resolved_path || targetPath;
  selectRemoteDirectory(resolvedTargetPath, `当前目录 · ${resolvedTargetPath}`);
  appendLog("已加载部署目录", resolvedTargetPath);
}

function renderTasks(tasks) {
  taskList.replaceChildren();
  if (!tasks.length) {
    taskList.appendChild(createEmptyState("还没有后台任务。创建部署任务后会显示在这里。"));
    taskDetailOutput.textContent = "暂无任务详情。";
    selectedTaskId = "";
    return;
  }

  if (selectedTaskId && !tasks.some((task) => task.id === selectedTaskId)) {
    selectedTaskId = "";
  }
  if (!selectedTaskId) {
    const runningTask = tasks.find((task) => task.status === "running");
    selectedTaskId = (runningTask || tasks[0]).id;
  }

  tasks.forEach((task) => {
    const item = document.createElement("div");
    item.className = `record-item ${task.id === selectedTaskId ? "selected" : ""}`;

    const header = document.createElement("div");
    header.className = "record-header";

    const title = document.createElement("strong");
    title.textContent = task.title;

    header.append(title, createStatusPill(task.status));

    const meta = document.createElement("div");
    meta.className = "record-meta";
    meta.textContent = `${task.type} · 创建于 ${task.created_at}${task.finished_at ? ` · 完成于 ${task.finished_at}` : ""}`;

    const actions = document.createElement("div");
    actions.className = "record-actions";
    actions.appendChild(
      createActionButton(task.id === selectedTaskId ? "已选中" : "查看详情", task.id === selectedTaskId ? "secondary" : "ghost", async () => {
        selectedTaskId = task.id;
        await refreshTaskDetail();
        renderTasks(tasks);
      }),
    );

    item.append(header, meta, actions);
    taskList.appendChild(item);
  });
}

function formatObject(value) {
  if (!value || (typeof value === "object" && !Object.keys(value).length)) {
    return "无";
  }
  return JSON.stringify(value, null, 2);
}

function taskStatusLabel(status) {
  const labelMap = {
    pending: "等待中",
    running: "执行中",
    warning: "成功（有告警）",
    succeeded: "成功",
    failed: "失败",
  };
  return labelMap[status] || status;
}

function setTaskDetailCopyState({ enabled, text = "复制日志" } = {}) {
  if (!copyTaskDetailBtn) {
    return;
  }
  copyTaskDetailBtn.disabled = !enabled;
  copyTaskDetailBtn.textContent = text;
}

function buildTaskDetailText(task) {
  if (!task) {
    return "暂无任务详情。";
  }
  const lines = [
    `任务: ${task.title}`,
    `ID: ${task.id}`,
    `状态: ${taskStatusLabel(task.status)}`,
    `创建时间: ${task.created_at || "-"}`,
    `开始时间: ${task.started_at || "-"}`,
    `完成时间: ${task.finished_at || "-"}`,
    "",
    "结果:",
    formatObject(task.result),
  ];

  if (task.error) {
    lines.push("", `错误: ${task.error}`);
  }

  lines.push("", "后台日志:");
  if (task.logs.length) {
    lines.push(...task.logs);
  } else {
    lines.push("暂无日志");
  }
  return lines.join("\n");
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const successful = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!successful) {
    throw new Error("复制失败，请手动选择日志内容复制");
  }
}

async function copyRosExample(button, outputNode, successMessage) {
  const text = String(outputNode?.textContent || "").trim();
  if (!text) {
    throw new Error("当前没有可复制的示例内容");
  }
  const originalText = button?.textContent || "复制示例";
  await copyText(text);
  if (button) {
    button.textContent = "已复制";
    window.setTimeout(() => {
      button.textContent = originalText;
    }, 1600);
  }
  appendLog(successMessage);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderTaskDetailLine(line) {
  const text = String(line ?? "");
  let className = "task-log-line";
  if (text.startsWith("[stdout] ")) {
    className += " is-stdout";
  } else if (text.startsWith("[stderr] ")) {
    className += " is-stderr";
  } else if (text.startsWith("错误:")) {
    className += " is-error";
  } else if (text.endsWith("标准输出:") || text.endsWith("错误输出:")) {
    className += " is-stream-title";
  } else if (text.startsWith("后台日志:") || text.startsWith("结果:")) {
    className += " is-section";
  } else if (/^(任务|ID|状态|创建时间|开始时间|完成时间):/.test(text)) {
    className += " is-meta";
  }
  return `<div class="${className}">${escapeHtml(text)}</div>`;
}

function renderTaskDetail(task) {
  if (!task) {
    currentTaskDetailText = "";
    setTaskDetailCopyState({ enabled: false });
    taskDetailOutput.textContent = "暂无任务详情。";
    return;
  }
  const text = buildTaskDetailText(task);
  const lines = text.split("\n");
  currentTaskDetailText = text;
  setTaskDetailCopyState({ enabled: true });
  taskDetailOutput.innerHTML = lines.map(renderTaskDetailLine).join("");
}

async function refreshTaskDetail() {
  if (!selectedTaskId) {
    currentTaskDetailText = "";
    setTaskDetailCopyState({ enabled: false });
    taskDetailOutput.textContent = "暂无任务详情。";
    return;
  }
  const data = await request(`/api/tasks/${selectedTaskId}`);
  renderTaskDetail(data.task);
}

async function refreshDashboard() {
  try {
    const taskData = await request("/api/tasks");
    console.log("[refreshDashboard.tasks]", (taskData.tasks || []).map((task) => ({
      id: task.id,
      status: task.status,
      mode: task?.metadata?.deploy_mode || "",
      finishedAt: task.finished_at,
    })));
    renderTasks(taskData.tasks);
    syncDeployFlow("package", { tasks: taskData.tasks });
    syncDeployFlow("module", { tasks: taskData.tasks });
    await refreshTaskDetail();
    dashboardErrorShown = false;
  } catch (error) {
    if (!dashboardErrorShown) {
      appendLog("刷新后台状态失败", error.message);
      dashboardErrorShown = true;
    }
  }
}

function startDashboardPolling() {
  if (dashboardTimer) {
    window.clearInterval(dashboardTimer);
  }
  dashboardTimer = window.setInterval(() => {
    refreshDashboard();
  }, 4000);
}
/* deploy.js */
if (copyTaskDetailBtn) {
  copyTaskDetailBtn.addEventListener("click", async () => {
    if (!currentTaskDetailText) {
      return;
    }
    try {
      await copyText(currentTaskDetailText);
      setTaskDetailCopyState({ enabled: true, text: "已复制" });
      appendLog("已复制后台任务日志");
      window.setTimeout(() => {
        setTaskDetailCopyState({ enabled: true, text: "复制日志" });
      }, 1600);
    } catch (error) {
      appendLog("复制后台任务日志失败", error.message);
      alert(error.message);
    }
  });
}
/* deploy.js */
async function submitDeployForm(event, { deployMode, progressView, tokenPrefix }) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  if (deployMode === "package") {
    const deviceType = String(formData.get("device_type") || "ORIN").trim().toUpperCase() || "ORIN";
    formData.set("device_type", deviceType);
  }
  const conflictResolution = await resolveDeployConflict(formData, deployMode, progressView);
  if (conflictResolution.cancelled) {
    return;
  }
  currentDeployTaskIds.package = "";
  syncDeployFlow("package", {
    task: {
      id: "",
      type: "deployment",
      status: conflictResolution.skipBrowserUpload ? "pending" : "running",
      metadata: { deploy_mode: "package" },
      result: {},
      error: "",
    },
    progress: conflictResolution.skipBrowserUpload ? { phase: "completed", done: true } : { phase: "preparing", done: false },
  });
  let data;
  try {
    data = await submitUploadWithProgress("/api/deploy", formData, progressView, tokenPrefix, {
      skipBrowserUpload: conflictResolution.skipBrowserUpload,
    });
  } catch (error) {
    const retryResolution = await resolveDeployConflictFromError(formData, progressView, error);
    if (!retryResolution.handled) {
      markPackageDeployFailed(error.message || "上传或识别机型失败");
      throw error;
    }
    if (retryResolution.cancelled) {
      markPackageDeployFailed(error.message || "上传或识别机型失败");
      return;
    }
    data = await submitUploadWithProgress("/api/deploy", formData, progressView, tokenPrefix, {
      skipBrowserUpload: retryResolution.skipBrowserUpload,
    });
  }
  selectedTaskId = data.task.id;
  currentDeployTaskIds.package = data.task.id;
  syncDeployFlow("package", { task: data.task });
  appendLog("部署任务已创建", `${data.task.title} (${data.task.id})`);
  await refreshDashboard();
}

async function createPackageDeployTask(formData, { progressView, tokenPrefix = "package-deploy" } = {}) {
  const conflictResolution = await resolveDeployConflict(formData, "package", progressView);
  if (conflictResolution.cancelled) {
    return null;
  }
  const skipBrowserUpload = conflictResolution.skipBrowserUpload;
  currentDeployTaskIds.package = "";
  syncDeployFlow("package", {
    task: {
      id: "",
      type: "deployment",
      status: skipBrowserUpload ? "pending" : "running",
      metadata: { deploy_mode: "package" },
      result: {},
      error: "",
    },
    progress: skipBrowserUpload ? { phase: "completed", done: true } : { phase: "preparing", done: false },
  });
  let data;
  packageDeployRequestInFlight = true;
  try {
    data = await submitUploadWithProgress("/api/deploy", formData, progressView, tokenPrefix, {
      skipBrowserUpload,
    });
  } catch (error) {
    const retryResolution = await resolveDeployConflictFromError(formData, progressView, error, { deployMode: "package" });
    if (!retryResolution.handled) {
      throw error;
    }
    if (retryResolution.cancelled) {
      return null;
    }
    data = await submitUploadWithProgress("/api/deploy", formData, progressView, tokenPrefix, {
      skipBrowserUpload: retryResolution.skipBrowserUpload,
    });
  } finally {
    packageDeployRequestInFlight = false;
  }
  selectedTaskId = data.task.id;
  currentDeployTaskIds.package = data.task.id;
  syncDeployFlow("package", { task: data.task });
  appendLog("整包部署任务已创建", `${data.task.title} (${data.task.id})`);
  await refreshDashboard();
  return data.task;
}

async function createModuleDeployTask(formData) {
  currentDeployTaskIds.module = "";
  syncDeployFlow("module", {
    task: {
      id: "",
      type: "deployment",
      status: "running",
      metadata: {
        deploy_mode: "module",
      },
      result: {},
      error: "",
    },
    progress: { phase: "preparing", done: false },
  });

  const data = await submitUploadWithProgress("/api/deploy-module", formData, uploadProgressViews.moduleDeploy, "module-deploy", {
    skipBrowserUpload: Boolean(formData.get("server_file_path")),
  });
  selectedTaskId = data.task.id;
  currentDeployTaskIds.module = data.task.id;
  syncDeployFlow("module", { task: data.task });
  appendLog("模块部署任务已创建", `${data.task.title} (${data.task.id})`);
  await refreshDashboard();
  return data.task;
}

async function submitPackageDeployStart(event) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const deviceType = String(formData.get("device_type") || "ORIN").trim().toUpperCase() || "ORIN";
  formData.set("device_type", deviceType);
  formData.set("machine_type", "");
  const firstTask = await createPackageDeployTask(formData, {
    progressView: uploadProgressViews.packageDeploy,
    tokenPrefix: "package-deploy",
  });
  if (!firstTask) {
    return;
  }
  const checkpointTask = await waitForTaskCheckpoint(firstTask.id);
  if (String(checkpointTask.status || "").trim().toLowerCase() === "failed") {
    finalizeUploadProgressFromTask(uploadProgressViews.packageDeploy, checkpointTask);
    markPackageDeployFailed(checkpointTask.error || "整包部署任务执行失败");
    throw new Error(checkpointTask.error || "整包部署任务执行失败");
  }
  if (!isTaskWaitingConfirmation(checkpointTask)) {
    finalizeUploadProgressFromTask(uploadProgressViews.packageDeploy, checkpointTask);
    resetPackageDeployStage({ keepHint: true });
    setPackageDeployHint("整包部署任务已执行完成。");
    return;
  }
  const machineOptions = Array.isArray(checkpointTask?.pending_confirmation?.input?.options)
    ? checkpointTask.pending_confirmation.input.options
    : [];
  const selectedMachineType = "";
  activatePackageDeployContinueStage({
    taskId: checkpointTask.id,
    fileName: checkpointTask?.metadata?.file_name || String(formData.get("file_name") || "").trim(),
    remotePath: checkpointTask?.metadata?.remote_path || "",
    remoteDir: checkpointTask?.metadata?.remote_dir || "",
    deviceType,
    machineOptions,
    selectedMachineType,
  });
  appendLog(
    "整包上传完成，等待 workflow 机型确认",
    `${checkpointTask?.metadata?.remote_path || ""}\n机型: ${machineOptions.map((item) => item.label || item.value).join(", ")}`,
  );
  setPackageDeployHint("请先选择机型并点击“继续部署”。");
}

async function submitPackageContinueDeployForm(formNode) {
  const formData = new FormData(formNode);
  const deviceType = String(formData.get("device_type") || packageDeployStageState.deviceType || "ORIN").trim().toUpperCase() || "ORIN";
  const machineType = String(formData.get("machine_type") || "").trim();
  if (!machineType) {
    throw new Error("请选择机型");
  }
  if (!packageDeployStageState.taskId) {
    throw new Error("当前没有等待确认的部署任务，请重新上传 firmware");
  }
  setPackageMachineAttention(false);
  setPackageDeployHint(`已确认机型 ${machineType}，正在继续部署。`);
  const continueResponse = await request(`/api/tasks/${packageDeployStageState.taskId}/continue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: machineType }),
  });
  const continuedTask = continueResponse?.task || null;
  if (!continuedTask) {
    throw new Error("继续部署失败：未获取到任务信息");
  }
  if (continuedTask.status && String(continuedTask.status).trim().toLowerCase() !== "waiting_confirmation") {
    packageDeployStageState.stage = "upload";
  }
  syncDeployFlow("package", { task: continuedTask });
  const firstResult = await waitForTaskCompletion(continuedTask.id);
  if (String(firstResult.status || "").trim().toLowerCase() === "failed") {
    finalizeUploadProgressFromTask(uploadProgressViews.packageDeploy, firstResult);
    markPackageDeployFailed(firstResult.error || "首个整包部署任务执行失败");
    throw new Error(firstResult.error || "首个整包部署任务执行失败");
  }
  finalizeUploadProgressFromTask(uploadProgressViews.packageDeploy, firstResult);

  resetPackageDeployStage({ keepHint: true, keepMachineOptions: true, selectedMachineType: machineType });
  setPackageDeployHint("已创建整包部署任务。如需部署其他 firmware，请重新选择文件。");
  await refreshDashboard();
}

async function submitPackageContinueDeploy(event) {
  event.preventDefault();
  await submitPackageContinueDeployForm(event.currentTarget);
}

packageDeployForm.addEventListener("submit", async (event) => {
  try {
    if (packageDeployStageState.stage === "continue") {
      await submitPackageContinueDeploy(event);
      return;
    }
    await submitPackageDeployStart(event);
  } catch (error) {
    const isContinueStage = packageDeployStageState.stage === "continue";
    appendLog(isContinueStage ? "继续整包安装失败" : "上传并识别机型失败", error.message);
    if (isContinueStage) {
      markPackageDeployFailed(error.message || "安装失败，请查看后台日志");
    } else {
      setPackageDeployHint(error.message, true);
    }
    alert(error.message);
  }
});

async function submitModuleDeployForm(event) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const moduleName = String(formData.get("module_name") || "").trim();
  if (!moduleName) {
    throw new Error("请选择要部署的模块");
  }
  const selectedFile = formData.get("deb_file");
  const serverFilePath = String(formData.get("server_file_path") || "").trim();
  if (!(selectedFile instanceof File) || !selectedFile.name) {
    if (!extractFileNameFromServerPath(serverFilePath)) {
      throw new Error("请选择要部署的模块 deb 文件或填写文件服务器包路径");
    }
  }
  if (!serverFilePath && (!(selectedFile instanceof File) || !selectedFile.name)) {
    throw new Error("请选择要部署的模块 deb 文件");
  }

  const task = await createModuleDeployTask(formData);
  const result = await waitForTaskCompletion(task.id);
  finalizeUploadProgressFromTask(uploadProgressViews.moduleDeploy, result);
  if (String(result.status || "").trim().toLowerCase() === "failed") {
    throw new Error(result.error || "模块部署任务执行失败");
  }
  appendLog("模块部署完成", `${moduleName} 已完成`);
}

if (moduleDeployForm) {
  moduleDeployForm.addEventListener("submit", async (event) => {
    try {
      await submitModuleDeployForm(event);
    } catch (error) {
      appendLog("创建模块部署任务失败", error.message);
      alert(error.message);
    }
  });
}

remoteDirLoadButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const targetSelectId = button.dataset.targetSelect;
    try {
      await loadRemoteDirectoryFromSelect(targetSelectId);
    } catch (error) {
      appendLog("02 区域目录加载失败", error.message);
      alert(error.message);
    }
  });
});
