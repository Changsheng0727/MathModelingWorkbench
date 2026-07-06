const state = {
  currentProject: null,
  projects: [],
  projectQuery: "",
  projectFilter: validProjectFilter(readPreference("mmw-project-filter", "all")),
  selectedProjectIds: new Set(),
  templates: [],
  llmSettings: null,
  autoJobs: null,
  deliveryBatchJobs: null,
  capacitySettings: null,
  capacityAutotune: null,
  growthMetrics: null,
  trustMetrics: null,
  trustExports: null,
  repairCampaigns: null,
  repairBriefing: null,
  deliveryReadiness: null,
  deliveryPackage: null,
  experience: null,
  uploadProgressStop: null,
  projectRestoreTried: false,
};

const els = {
  form: document.querySelector("#upload-form"),
  file: document.querySelector("#file-input"),
  fileLabel: document.querySelector("#file-label"),
  folder: document.querySelector("#folder-input"),
  folderLabel: document.querySelector("#folder-label"),
  autoRunAfterUpload: document.querySelector("#auto-run-after-upload"),
  status: document.querySelector("#upload-status"),
  uploadProgress: document.querySelector("#upload-analysis-progress"),
  refresh: document.querySelector("#refresh-projects"),
  projectSearch: document.querySelector("#project-search"),
  projectFilters: document.querySelector("#project-filters"),
  projectCount: document.querySelector("#project-count"),
  selectAnalyzedProjects: document.querySelector("#select-analyzed-projects"),
  clearProjectSelection: document.querySelector("#clear-project-selection"),
  batchStartProjects: document.querySelector("#batch-start-projects"),
  projectBatchDetails: document.querySelector("#project-batch-details"),
  batchProjectStatus: document.querySelector("#batch-project-status"),
  projectList: document.querySelector("#project-list"),
  health: document.querySelector("#health"),
  themeToggle: document.querySelector("#theme-toggle"),
  themeToggleLabel: document.querySelector("#theme-toggle-label"),
  llmSettingsForm: document.querySelector("#llm-settings-form"),
  apiKeyInput: document.querySelector("#api-key-input"),
  baseUrlInput: document.querySelector("#base-url-input"),
  modelInput: document.querySelector("#model-input"),
  workflowStrategyInput: document.querySelector("#workflow-strategy-input"),
  workflowStrategyHint: document.querySelector("#workflow-strategy-hint"),
  testLlmSettings: document.querySelector("#test-llm-settings"),
  clearLlmSettings: document.querySelector("#clear-llm-settings"),
  llmSettingsStatus: document.querySelector("#llm-settings-status"),
  title: document.querySelector("#project-title"),
  openProjectRoot: document.querySelector("#open-project-root"),
  environment: document.querySelector("#environment-status"),
  empty: document.querySelector("#empty-state"),
  analysisView: document.querySelector("#analysis-view"),
  recommended: document.querySelector("#recommended-problem"),
  problemSelectionStatus: document.querySelector("#problem-selection-status"),
  documentCount: document.querySelector("#document-count"),
  dataCount: document.querySelector("#data-count"),
  projectStatus: document.querySelector("#project-status"),
  experienceGuide: document.querySelector("#experience-guide"),
  guideTitle: document.querySelector("#guide-title"),
  guideDetail: document.querySelector("#guide-detail"),
  guideActions: document.querySelector("#guide-actions"),
  guideSteps: document.querySelector("#guide-steps"),
  statusCards: document.querySelector("#status-cards"),
  projectReadiness: document.querySelector("#project-readiness"),
  growthCenter: document.querySelector("#growth-center"),
  refreshGrowthMetrics: document.querySelector("#refresh-growth-metrics"),
  growthCenterStatus: document.querySelector("#growth-center-status"),
  trustCenter: document.querySelector("#trust-center"),
  refreshTrustCenter: document.querySelector("#refresh-trust-center"),
  trustCenterStatus: document.querySelector("#trust-center-status"),
  refreshAutoJobs: document.querySelector("#refresh-auto-jobs"),
  autoJobCenter: document.querySelector("#auto-job-center"),
  repairCenter: document.querySelector("#repair-center"),
  refreshRepairCenter: document.querySelector("#refresh-repair-center"),
  repairCenterStatus: document.querySelector("#repair-center-status"),
  deliveryCenter: document.querySelector("#delivery-center"),
  refreshDeliveryReadiness: document.querySelector("#refresh-delivery-readiness"),
  deliveryReadinessStatus: document.querySelector("#delivery-readiness-status"),
  problemCards: document.querySelector("#problem-cards"),
  workflow: document.querySelector("#workflow"),
  inventory: document.querySelector("#inventory"),
  paperOptionsForm: document.querySelector("#paper-options-form"),
  templateSelect: document.querySelector("#template-select"),
  targetBodyPages: document.querySelector("#target-body-pages"),
  paperOptionsStatus: document.querySelector("#paper-options-status"),
  templateUploadForm: document.querySelector("#template-upload-form"),
  templateNameInput: document.querySelector("#template-name-input"),
  templateFileInput: document.querySelector("#template-file-input"),
  templateFileLabel: document.querySelector("#template-file-label"),
  templateStatus: document.querySelector("#template-status"),
  templateHint: document.querySelector("#template-hint"),
  deleteTemplate: document.querySelector("#delete-template"),
  modelAssistantForm: document.querySelector("#model-assistant-form"),
  assistProblemSelect: document.querySelector("#assist-problem-select"),
  assistModelInput: document.querySelector("#assist-model-input"),
  assistGoalInput: document.querySelector("#assist-goal-input"),
  modelAssistantStatus: document.querySelector("#model-assistant-status"),
  modelAssistantProgress: document.querySelector("#model-assistant-progress"),
  artifacts: document.querySelector("#artifacts"),
  runModeling: document.querySelector("#run-modeling"),
  modelingStatus: document.querySelector("#modeling-status"),
  runSpecialized: document.querySelector("#run-specialized"),
  specializedStatus: document.querySelector("#specialized-status"),
  runAutoWorkflow: document.querySelector("#run-auto-workflow"),
  resumeAutoWorkflow: document.querySelector("#resume-auto-workflow"),
  cancelAutoWorkflow: document.querySelector("#cancel-auto-workflow"),
  autoWorkflowStatus: document.querySelector("#auto-workflow-status"),
  autoWorkflowProgress: document.querySelector("#auto-workflow-progress"),
  refreshDiagnostics: document.querySelector("#refresh-diagnostics"),
  diagnosticsStatus: document.querySelector("#diagnostics-status"),
  generateSkillReport: document.querySelector("#generate-skill-report"),
  skillReportStatus: document.querySelector("#skill-report-status"),
  generateCodeGraph: document.querySelector("#generate-code-graph"),
  codeGraphStatus: document.querySelector("#code-graph-status"),
  fillPaper: document.querySelector("#fill-paper"),
  paperFillStatus: document.querySelector("#paper-fill-status"),
  compile: document.querySelector("#compile-latex"),
  compileStatus: document.querySelector("#compile-status"),
  reviewPaper: document.querySelector("#review-paper"),
  paperReviewStatus: document.querySelector("#paper-review-status"),
  runLlmAnalysis: document.querySelector("#run-llm-analysis"),
  llmAnalysisStatus: document.querySelector("#llm-analysis-status"),
  toastRegion: document.querySelector("#toast-region"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function encodeRelativePath(value) {
  return String(value ?? "")
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
}

function readPreference(key, fallback = "") {
  try {
    return window.localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function writePreference(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Some embedded browser policies disable localStorage; the UI still works without it.
  }
}

function resolveThemePreference() {
  const requested = new URLSearchParams(window.location.search).get("theme");
  if (requested === "light" || requested === "dark") {
    writePreference("modelark-theme", requested);
    return requested;
  }
  const stored = readPreference("modelark-theme", "");
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme, { persist = false } = {}) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  if (persist) {
    writePreference("modelark-theme", nextTheme);
  }
  const isDark = nextTheme === "dark";
  if (els.themeToggle) {
    els.themeToggle.setAttribute("aria-checked", isDark ? "true" : "false");
    els.themeToggle.setAttribute("aria-label", isDark ? "切换到浅色模式" : "切换到深色模式");
  }
  if (els.themeToggleLabel) {
    els.themeToggleLabel.textContent = isDark ? "深色" : "浅色";
  }
}

function initThemeToggle() {
  applyTheme(resolveThemePreference());
  els.themeToggle?.addEventListener("click", () => {
    const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    applyTheme(current === "dark" ? "light" : "dark", { persist: true });
  });
}

function normalizeSearch(value) {
  return String(value ?? "").trim().toLowerCase();
}

function showToast(message, tone = "info") {
  if (!els.toastRegion || !message) {
    return;
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${tone}`;
  toast.setAttribute("role", tone === "error" ? "alert" : "status");
  toast.textContent = message;
  els.toastRegion.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("is-leaving");
    window.setTimeout(() => toast.remove(), 180);
  }, 2800);
}

function responseErrorMessage(response, payload, text, requestPath = "") {
  const rawDetail = payload?.detail || payload?.message || text || response.statusText || `HTTP ${response.status}`;
  const detail = String(rawDetail || "").trim();
  const lowerDetail = detail.toLowerCase();
  const isLocalApiRequest = String(requestPath || "").startsWith("/api/");
  const looksLikeLlmProvider404 = (
    lowerDetail.includes("llm api") ||
    lowerDetail.includes("chat/completions") ||
    lowerDetail.includes("base url") ||
    detail.includes("服务商返回 NOT FOUND") ||
    detail.includes("接口地址") ||
    detail.includes("模型")
  );
  if (isLocalApiRequest && response.status === 404 && (!detail || /not found/i.test(detail)) && !looksLikeLlmProvider404) {
    return "后端接口不存在（HTTP 404）。请关闭旧客户端或旧后台服务后重新打开最新版客户端；如果仍然出现，请重新安装最新安装包。";
  }
  return detail || `HTTP ${response.status}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    const detail = responseErrorMessage(response, payload, text, path);
    throw new Error(detail);
  }
  return payload ?? {};
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function activateModuleTab(target, { focus = false } = {}) {
  const tabs = Array.from(document.querySelectorAll("[data-module-tab]"));
  const panels = Array.from(document.querySelectorAll("[data-module-panel]"));
  if (!tabs.length) {
    return;
  }
  const activeTab = tabs.find((item) => item.dataset.moduleTab === target) || tabs[0];
  const parentDetails = activeTab.closest("details");
  if (parentDetails) {
    parentDetails.open = true;
  }
  tabs.forEach((item) => {
    const active = item === activeTab;
    item.classList.toggle("is-active", active);
    item.setAttribute("aria-selected", active ? "true" : "false");
    item.tabIndex = active ? 0 : -1;
  });
  panels.forEach((panel) => {
    const active = panel.dataset.modulePanel === activeTab.dataset.moduleTab;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });
  writePreference("mmw-active-module", activeTab.dataset.moduleTab);
  if (focus) {
    activeTab.focus();
  }
}

async function checkHealth() {
  try {
    await api("/api/health");
    els.health.textContent = "已连接";
    els.health.dataset.status = "connected";
    const env = await api("/api/environments");
    renderEnvironments(env);
    await loadLlmSettings();
    await loadTemplates();
  } catch {
    els.health.textContent = "未连接";
    els.health.dataset.status = "disconnected";
  }
}

function renderEnvironments(env) {
  const local = env.local_python?.available ? `Python ${env.local_python.version}` : "Python 不可用";
  const pandoc = env.pandoc?.available ? "Pandoc 可用" : "Pandoc 缺失";
  const xelatex = env.xelatex?.available ? "XeLaTeX 可用" : "XeLaTeX 缺失";
  const depStatus = dependencyInstallLabel(env.dependency_install);
  els.environment.textContent = `${local} · ${pandoc} · ${xelatex}${depStatus ? ` · ${depStatus}` : ""}`;
}

function dependencyInstallLabel(status = {}) {
  const value = status.status || "";
  const labels = {
    checking: "依赖检查中",
    installing: "依赖下载中",
    ready: "依赖已就绪",
    partial: "依赖需重启/复核",
    manual_required: "需手动安装依赖",
    unreadable: "依赖状态不可读",
  };
  return labels[value] || "";
}

async function loadLlmSettings() {
  const settings = await api("/api/settings/llm");
  renderLlmSettings(settings);
  renderExperienceGuide(state.experience || {});
}

async function loadTemplates() {
  const payload = await api("/api/templates");
  state.templates = payload.templates || [];
  const selected = state.currentProject?.metadata?.paper_options?.template_id || "builtin-default";
  renderTemplateSelect(selected);
}

function renderTemplateSelect(selectedId = "builtin-default") {
  if (!els.templateSelect) {
    return;
  }
  els.templateSelect.innerHTML = state.templates
    .map((template) => {
      const selected = template.id === selectedId ? " selected" : "";
      const suffix = template.is_builtin
        ? "（内置）"
        : template.mode === "rules"
          ? "（格式说明）"
          : "（LaTeX 模板）";
      return `<option value="${escapeHtml(template.id)}"${selected}>${escapeHtml(template.name + suffix)}</option>`;
    })
    .join("");
  renderTemplateHint(selectedId);
}

function renderTemplateHint(templateId = "builtin-default") {
  if (!els.templateHint) {
    return;
  }
  const template = state.templates.find((item) => item.id === templateId);
  if (!template || template.is_builtin) {
    els.templateHint.textContent = "当前使用内置 LaTeX 模板；若上传 Word/PDF 格式说明，系统会提取规则并保留审查提示。";
    return;
  }
  if (template.mode === "rules") {
    const chars = template.extracted_chars ?? 0;
    const summary = template.rule_summary ? ` 摘要：${template.rule_summary.slice(0, 180)}` : "";
    els.templateHint.textContent = `当前选择格式说明文档，已提取 ${chars} 个字符；生成论文时仍使用内置 LaTeX 模板。${summary}`;
    return;
  }
  const placeholders = template.placeholders?.length ? template.placeholders.join("、") : "未记录";
  els.templateHint.textContent = `当前选择自定义 LaTeX 模板，占位符：${placeholders}`;
}

function renderLlmSettings(settings) {
  state.llmSettings = settings;
  els.apiKeyInput.value = "";
  els.baseUrlInput.value = settings.base_url || "https://api.chshapi.org/v1";
  els.modelInput.value = settings.model || "gpt-5.5";
  if (els.workflowStrategyInput) {
    const options = settings.workflow_strategy_options?.length
      ? settings.workflow_strategy_options
      : [
          { id: "balanced", label: "均衡", summary: "速度和成功率兼顾" },
          { id: "stable", label: "稳妥", summary: "更多校验和自动修复" },
          { id: "turbo", label: "极速", summary: "并行读取附件和子问题" },
        ];
    els.workflowStrategyInput.innerHTML = options
      .map((item) => {
        const selected = item.id === (settings.workflow_strategy || "balanced") ? " selected" : "";
        return `<option value="${escapeHtml(item.id)}"${selected}>${escapeHtml(item.label)}：${escapeHtml(item.summary)}</option>`;
      })
      .join("");
  }
  if (els.workflowStrategyHint) {
    const label = settings.workflow_strategy_label || "均衡";
    const summary = settings.workflow_strategy_summary || "速度和成功率兼顾。";
    els.workflowStrategyHint.textContent = `当前策略：${label}。${summary}`;
  }
  if (settings.configured) {
    const source = settings.source === "env" ? "环境变量" : "本地设置";
    const strategy = settings.workflow_strategy_label ? ` · ${settings.workflow_strategy_label}` : "";
    els.llmSettingsStatus.textContent = `已配置：${settings.masked_api_key} · ${source}${strategy}`;
  } else {
    els.llmSettingsStatus.textContent = "尚未配置 API 密钥。";
  }
}

async function loadProjects({ restore = false } = {}) {
  if (els.projectCount) {
    els.projectCount.textContent = "正在刷新项目状态…";
  }
  try {
    state.projects = await api("/api/projects");
    pruneSelectedProjects();
    renderProjectList();
    renderExperienceGuide(state.experience || {});
    if (restore) {
      await restoreInitialProject();
    }
  } catch (error) {
    renderProjectListLoadError(error);
    throw error;
  }
}

function renderProjectListLoadError(error) {
  const existingCount = (state.projects || []).length;
  if (els.projectCount) {
    els.projectCount.textContent = existingCount ? `刷新失败，仍显示 ${existingCount} 个旧项目` : "项目列表加载失败";
  }
  if (els.projectList && !existingCount) {
    els.projectList.innerHTML = `<p class="status">项目列表暂时无法读取：${escapeHtml(error.message)}。请检查本地后端是否已启动，或重新打开客户端。</p>`;
  }
}

async function restoreInitialProject() {
  if (state.projectRestoreTried || state.currentProject) {
    return;
  }
  state.projectRestoreTried = true;
  const projects = state.projects || [];
  const savedId = readPreference("mmw-last-project-id", "");
  const candidate = projects.find((project) => project.id === savedId) || projects.find((project) => project.default_open) || projects[0];
  if (candidate?.id) {
    try {
      await openProject(candidate.id, { silent: true });
    } catch (error) {
      writePreference("mmw-last-project-id", "");
      showToast(`自动恢复上次项目失败：${error.message}`, "warning");
    }
  }
}

async function loadAutoJobs() {
  if (!els.autoJobCenter) {
    return;
  }
  try {
    const payload = await api("/api/auto/jobs");
    state.autoJobs = payload.auto_jobs || {};
    state.deliveryBatchJobs = payload.delivery_batch_jobs || {};
    state.capacitySettings = payload.capacity_settings || state.autoJobs.capacity_settings || state.deliveryBatchJobs.capacity_settings || null;
    state.capacityAutotune = payload.capacity_autotune || state.capacityAutotune || null;
    renderAutoJobCenter(state.autoJobs, state.deliveryBatchJobs);
  } catch (error) {
    els.autoJobCenter.innerHTML = `<p class="status">后台任务中心暂不可用：${escapeHtml(error.message)}</p>`;
  }
}

async function loadGrowthMetrics() {
  if (!els.growthCenter) {
    return;
  }
  try {
    const payload = await api("/api/product/growth");
    state.growthMetrics = payload.growth || {};
    renderGrowthCenter(state.growthMetrics);
    if (payload.trust && els.trustCenter) {
      state.trustMetrics = payload.trust;
      renderTrustCenter(state.trustMetrics);
    }
  } catch (error) {
    els.growthCenter.innerHTML = `<p class="status">解题进度中心暂不可用：${escapeHtml(error.message)}</p>`;
  }
}

async function loadExperienceCenter() {
  if (!els.experienceGuide) {
    return;
  }
  try {
    const payload = await api("/api/product/experience");
    state.experience = payload.experience || {};
    renderExperienceGuide(state.experience);
  } catch (error) {
    renderExperienceGuide({
      status: "warning",
      label: "本地向导",
      summary: `体验向导暂不可用：${error.message}`,
      signals: {},
      actions: [{ id: "refresh_all", label: "刷新状态", detail: "重新读取本地项目状态。", tone: "neutral" }],
    });
  }
}

async function loadTrustCenter() {
  if (!els.trustCenter) {
    return;
  }
  try {
    const payload = await api("/api/product/trust");
    state.trustMetrics = payload.trust || {};
    state.trustExports = payload.trust_exports || null;
    state.repairCampaigns = payload.repair_campaigns || null;
    renderTrustCenter(state.trustMetrics, state.trustExports);
  } catch (error) {
    els.trustCenter.innerHTML = `<p class="status">信任中心暂不可用：${escapeHtml(error.message)}</p>`;
  }
}

function renderProjectList() {
  const projects = state.projects || [];
  const query = normalizeSearch(state.projectQuery);
  const filter = state.projectFilter || "all";
  const filtered = projects.filter((project) => {
    const matchesQuery = !query || projectSearchText(project).includes(query);
    return matchesQuery && projectFilterMatches(project, filter);
  });
  renderProjectFilters(projects);
  const selectedCount = state.selectedProjectIds.size;
  const batchVisible = Boolean(els.projectBatchDetails?.open);
  els.projectList?.classList.toggle("is-batch-visible", batchVisible);

  if (els.projectCount) {
    const filterText = projectFilterLabel(filter);
    els.projectCount.textContent = projects.length
      ? query || filter !== "all"
        ? `${filterText}：${filtered.length} / ${projects.length} 个项目${selectedCount ? ` · 已选 ${selectedCount}` : ""}`
        : `${projects.length} 个项目${selectedCount ? ` · 已选 ${selectedCount}` : ""}`
      : "暂无项目";
  }

  if (!projects.length) {
    els.projectList.innerHTML = '<p class="status">暂无项目</p>';
    updateProjectBatchControls();
    return;
  }
  if (!filtered.length) {
    els.projectList.innerHTML = '<p class="status">没有匹配的项目，试试切换筛选或搜索词。</p>';
    updateProjectBatchControls(filtered);
    return;
  }

  els.projectList.innerHTML = filtered
    .map(
      (project) => {
        const active = state.currentProject?.metadata?.id === project.id ? " is-active" : "";
        const autoBadge = project.auto_workflow_status ? `<span class="project-badge">${escapeHtml(project.auto_workflow_status)}</span>` : "";
        const analysisBadge = project.analysis_available ? '<span class="project-badge project-badge-ok">已分析</span>' : '<span class="project-badge project-badge-muted">未分析</span>';
        const readinessBadge = renderProjectReadinessBadge(project);
        const metadataErrorBadge = project.metadata_error
          ? `<span class="project-badge project-badge-error" title="${escapeHtml(project.metadata_error)}">元数据异常</span>`
          : "";
        const openBadge = project.can_open === false ? '<span class="project-badge project-badge-error">不可打开</span>' : "";
        const rootRepairBadge = project.root_was_repaired
          ? `<span class="project-badge project-badge-muted" title="${escapeHtml(project.root_repair_notice || "项目路径已自动校正")}">路径已校正</span>`
          : "";
        const nextStep = renderProjectNextStep(project);
        const quickAction = renderProjectQuickAction(project);
        const deliveryBadge = renderProjectDeliveryBadge(project);
        const artifactBadge = renderProjectArtifactBadge(project);
        const diagnosis = project.last_failure_diagnosis || {};
        const diagnosisBadge = diagnosis.category
          ? `<span class="project-badge project-badge-error" title="${escapeHtml(diagnosis.suggested_action || diagnosis.repair_focus || diagnosis.evidence || "")}">${escapeHtml(diagnosis.label || diagnosis.category)}</span>`
          : "";
        const status = project.status || "-";
        const updatedAt = project.project_updated_at || project.updated_at || project.created_at;
        const checked = state.selectedProjectIds.has(project.id) ? " checked" : "";
        const disabled = project.analysis_available ? "" : " disabled";
        const openDisabled = project.can_open === false ? " disabled" : "";
        return `
        <article class="project-row${active}${batchVisible ? " is-batch-visible" : ""}">
          <label class="project-select">
            <input class="project-select-input" type="checkbox" data-project-id="${escapeHtml(project.id)}"${checked}${disabled} />
            <span class="sr-only">选择${escapeHtml(project.name || project.id)}</span>
          </label>
          <button class="project-button project-open${active}" type="button" data-project-id="${escapeHtml(project.id)}"${openDisabled}>
            <span class="project-name">${escapeHtml(project.name)}</span>
            <span class="project-meta">更新 ${escapeHtml(formatProjectTime(updatedAt))} · ${escapeHtml(status)}</span>
            <span class="project-badges">${analysisBadge}${readinessBadge}${metadataErrorBadge}${openBadge}${rootRepairBadge}${autoBadge}${deliveryBadge}${artifactBadge}${diagnosisBadge}</span>
            ${nextStep}
          </button>
          ${quickAction}
        </article>
      `;
      },
    )
    .join("");
  updateProjectBatchControls(filtered);
  els.projectList.querySelectorAll(".project-open").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await openProject(button.dataset.projectId);
      } catch (error) {
        showToast(`打开项目失败：${error.message}`, "error");
      }
    });
  });
}

function renderProjectFilters(projects = []) {
  if (!els.projectFilters) {
    return;
  }
  const counts = projects.reduce(
    (acc, project) => {
      acc.all += 1;
      const bucket = project.readiness_bucket || "normal";
      if (bucket in acc) {
        acc[bucket] += 1;
      }
      return acc;
    },
    { all: 0, needs_action: 0, running: 0, deliverable: 0 },
  );
  els.projectFilters.querySelectorAll("[data-project-filter]").forEach((button) => {
    const filter = button.dataset.projectFilter || "all";
    const active = filter === (state.projectFilter || "all");
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.textContent = `${projectFilterLabel(filter)} ${counts[filter] ?? 0}`;
  });
}

function projectFilterMatches(project = {}, filter = "all") {
  const validFilter = validProjectFilter(filter);
  if (validFilter === "all") {
    return true;
  }
  return (project.readiness_bucket || "normal") === validFilter;
}

function projectFilterLabel(filter = "all") {
  const labels = {
    all: "全部",
    needs_action: "需处理",
    running: "运行中",
    deliverable: "可交付",
  };
  return labels[filter] || labels.all;
}

function validProjectFilter(filter = "all") {
  return ["all", "needs_action", "running", "deliverable"].includes(filter) ? filter : "all";
}

function renderProjectDeliveryBadge(project = {}) {
  const status = project.delivery_readiness_status || "";
  if (!status) {
    return "";
  }
  const label = project.delivery_readiness_label || statusLabel(status);
  const score = Number(project.delivery_readiness_score);
  const scoreText = Number.isFinite(score) ? ` ${score}分` : "";
  const tone = statusTone(status);
  const className = tone === "success" ? " project-badge-ok" : tone === "failed" ? " project-badge-error" : tone === "pending" ? " project-badge-muted" : "";
  const title = project.delivery_readiness_summary || label;
  return `<span class="project-badge${className}" title="${escapeHtml(title)}">${escapeHtml(label)}${escapeHtml(scoreText)}</span>`;
}

function renderProjectArtifactBadge(project = {}) {
  const summary = project.artifact_summary || {};
  const total = Number(summary.total || 0);
  if (total <= 1) {
    return "";
  }
  const available = Number(summary.available || 0);
  const missing = Number(summary.missing || 0);
  const unsafe = Number(summary.unsafe || 0);
  const className = missing || unsafe ? " project-badge-error" : " project-badge-ok";
  const label = missing ? `文件缺失 ${missing}` : unsafe ? `路径异常 ${unsafe}` : `文件 ${available}/${total}`;
  const title = missing || unsafe
    ? `可打开 ${available}/${total} 个文件，${missing} 个缺失${unsafe ? `，${unsafe} 个路径异常` : ""}`
    : `生成文件均可打开：${available}/${total}`;
  return `<span class="project-badge${className}" title="${escapeHtml(title)}">${escapeHtml(label)}</span>`;
}

function renderProjectReadinessBadge(project = {}) {
  const label = project.readiness_label || "";
  if (!label) {
    return "";
  }
  const score = Number(project.readiness_score);
  const scoreText = Number.isFinite(score) ? ` ${score}分` : "";
  const tone = statusTone(project.readiness_status);
  const className = tone === "success" ? " project-badge-ok" : tone === "failed" ? " project-badge-error" : tone === "pending" ? " project-badge-muted" : "";
  return `<span class="project-badge${className}" title="${escapeHtml(project.readiness_summary || label)}">${escapeHtml(label)}${escapeHtml(scoreText)}</span>`;
}

function renderProjectNextStep(project = {}) {
  const action = project.readiness_action || {};
  const label = action.label || "";
  const summary = project.readiness_summary || "";
  if (!label && !summary) {
    return "";
  }
  const text = label ? `下一步：${label}${summary ? ` · ${summary}` : ""}` : summary;
  return `<span class="project-next">${escapeHtml(text)}</span>`;
}

function renderProjectQuickAction(project = {}) {
  const action = project.readiness_action || {};
  const actionId = project.readiness_action_id || action.id || "";
  const label = project.readiness_action_label || action.label || "";
  if (!project.id || !actionId || !label) {
    return "";
  }
  return `<button class="project-quick-action" type="button" data-project-id="${escapeHtml(project.id)}" data-project-action="${escapeHtml(actionId)}">${escapeHtml(label)}</button>`;
}

function pruneSelectedProjects() {
  const validIds = new Set((state.projects || []).map((project) => project.id).filter(Boolean));
  Array.from(state.selectedProjectIds).forEach((projectId) => {
    if (!validIds.has(projectId)) {
      state.selectedProjectIds.delete(projectId);
    }
  });
}

function updateProjectBatchControls(filteredProjects = null) {
  const selectedCount = state.selectedProjectIds.size;
  const visible = Array.isArray(filteredProjects) ? filteredProjects : currentFilteredProjects();
  const analyzedVisibleCount = visible.filter((project) => project.analysis_available).length;
  if (els.batchStartProjects) {
    els.batchStartProjects.disabled = selectedCount === 0;
    els.batchStartProjects.textContent = selectedCount ? `批量入队 ${selectedCount}` : "批量入队";
  }
  if (els.clearProjectSelection) {
    els.clearProjectSelection.disabled = selectedCount === 0;
  }
  if (els.selectAnalyzedProjects) {
    els.selectAnalyzedProjects.disabled = analyzedVisibleCount === 0;
    els.selectAnalyzedProjects.textContent = analyzedVisibleCount ? `选择已分析 ${analyzedVisibleCount}` : "选择已分析";
  }
}

function currentFilteredProjects() {
  const projects = state.projects || [];
  const query = normalizeSearch(state.projectQuery);
  return projects.filter((project) => {
    const matchesQuery = !query || projectSearchText(project).includes(query);
    return matchesQuery && projectFilterMatches(project, state.projectFilter || "all");
  });
}

async function startSelectedProjectsBatch() {
  const projectIds = Array.from(state.selectedProjectIds);
  if (!projectIds.length) {
    els.batchProjectStatus.textContent = "请先选择已分析项目。";
    return;
  }
  els.batchStartProjects.disabled = true;
  els.selectAnalyzedProjects.disabled = true;
  els.clearProjectSelection.disabled = true;
  els.batchProjectStatus.textContent = `正在将 ${projectIds.length} 个项目加入后台任务池。`;
  try {
    const payload = await api("/api/auto/batch/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_ids: projectIds, mode: "auto" }),
    });
    const batch = payload.batch || {};
    const submitted = Array.isArray(batch.submitted) ? batch.submitted : [];
    submitted.forEach((job) => {
      if (job.project_id) {
        state.selectedProjectIds.delete(job.project_id);
      }
    });
    if (payload.auto_jobs) {
      state.autoJobs = payload.auto_jobs;
      renderAutoJobCenter(state.autoJobs, state.deliveryBatchJobs);
    } else {
      await loadAutoJobs();
    }
    await loadProjects();
    await loadGrowthMetrics();
    await loadTrustCenter();
    const skipped = Array.isArray(batch.skipped) ? batch.skipped : [];
    const skippedText = skipped.length
      ? `，跳过 ${skipped.length} 个：${skipped.slice(0, 2).map((item) => item.reason || item.project_id).join("；")}${skipped.length > 2 ? "…" : ""}`
      : "";
    els.batchProjectStatus.textContent = `批量入队完成：${batch.submitted_count || submitted.length} 个进入任务池${skippedText}。`;
    showToast("批量任务已提交后台任务池", "success");
  } catch (error) {
    els.batchProjectStatus.textContent = `批量入队失败：${error.message}`;
    showToast(`批量入队失败：${error.message}`, "error");
  } finally {
    updateProjectBatchControls();
  }
}

function projectSearchText(project = {}) {
  return normalizeSearch([
    project.id,
    project.name,
    project.original_name,
    project.created_at,
    project.project_updated_at,
    project.root_repair_notice,
    project.root_was_repaired ? "路径已校正" : "",
    project.status,
    project.auto_workflow_status,
    project.performance_health_label,
    project.performance_health_summary,
    project.repair_center_label,
    project.repair_center_summary,
    project.repair_center_action,
    project.delivery_readiness_label,
    project.delivery_readiness_summary,
    project.delivery_readiness_action,
    project.artifact_summary?.missing ? `文件缺失 ${project.artifact_summary.missing}` : "",
    project.artifact_summary?.unsafe ? `路径异常 ${project.artifact_summary.unsafe}` : "",
    project.artifact_summary?.available ? `可打开文件 ${project.artifact_summary.available}` : "",
    project.readiness_label,
    project.readiness_summary,
    project.readiness_action?.label,
    project.readiness_action_id,
    project.readiness_action_label,
    project.readiness_bucket_label || projectFilterLabel(project.readiness_bucket),
    project.metadata_error,
    project.metadata_error ? "元数据异常" : "",
    project.delivery_package_summary,
    project.delivery_package_sha256,
    project.last_failure_diagnosis?.label,
    project.last_failure_diagnosis?.category,
    project.last_failure_diagnosis?.repair_focus,
    project.last_failure_diagnosis?.suggested_action,
    project.analysis_available ? "已分析" : "未分析",
  ].filter(Boolean).join(" "));
}

function formatProjectTime(value) {
  if (!value) {
    return "-";
  }
  return String(value).replace("T", " ").slice(0, 16);
}

function formatBytes(value) {
  const units = ["B", "KB", "MB", "GB"];
  let size = Number(value) || 0;
  for (const unit of units) {
    if (size < 1024 || unit === units[units.length - 1]) {
      return unit === "B" ? `${Math.round(size)} B` : `${size.toFixed(1)} ${unit}`;
    }
    size /= 1024;
  }
  return `${size.toFixed(1)} GB`;
}

async function openProject(projectId, { silent = false } = {}) {
  const detail = await api(`/api/projects/${projectId}`);
  renderProject(detail);
  if (detail.metadata?.id) {
    writePreference("mmw-last-project-id", detail.metadata.id);
  }
  if (!silent) {
    if (detail.metadata?.metadata_error) {
      showToast("项目元数据读取失败，已打开可恢复视图。", "warning");
    } else if (detail.metadata?.artifact_load_errors?.length) {
      showToast(`部分生成文件读取失败：${detail.metadata.artifact_load_errors.length} 项。`, "warning");
    } else {
      showToast("已打开项目", "success");
    }
  }
}

async function openProjectRoot(projectId = "") {
  const targetProjectId = projectId || state.currentProject?.metadata?.id || "";
  if (!targetProjectId) {
    showToast("请先打开一个项目。", "warning");
    return;
  }
  const control = projectId ? null : els.openProjectRoot;
  const originalText = control?.textContent || "";
  if (control) {
    control.disabled = true;
    control.textContent = "打开中";
  }
  try {
    await api(`/api/projects/${encodeURIComponent(targetProjectId)}/open-root`, { method: "POST" });
    if (control) {
      control.textContent = "已打开";
      window.setTimeout(() => {
        control.textContent = originalText;
      }, 1200);
    }
    showToast("已打开项目文件夹", "success");
  } catch (error) {
    if (control) {
      control.textContent = originalText;
    }
    showToast(`打开项目文件夹失败：${error.message}`, "error");
  } finally {
    if (control) {
      window.setTimeout(() => {
        control.disabled = false;
      }, 250);
    }
  }
}

function renderProject(detail) {
  state.currentProject = detail;
  state.repairBriefing = detail.repair || null;
  state.deliveryReadiness = detail.delivery || null;
  state.deliveryPackage = detail.package || null;
  syncProjectSelection();
  const { metadata, analysis } = detail;
  els.title.textContent = metadata.name || metadata.original_name || "项目";
  if (els.openProjectRoot) {
    els.openProjectRoot.classList.remove("hidden");
    els.openProjectRoot.disabled = false;
  }
  const lastDiagnosis = metadata.last_failure_diagnosis || {};
  const diagnosisText = lastDiagnosis.category ? ` · 诊断：${lastDiagnosis.label || lastDiagnosis.category}` : "";
  const artifactErrorCount = Array.isArray(metadata.artifact_load_errors) ? metadata.artifact_load_errors.length : 0;
  const artifactErrorText = artifactErrorCount ? ` · 文件异常 ${artifactErrorCount}项` : "";
  els.projectStatus.textContent = metadata.auto_workflow_status
    ? `${metadata.status || "-"} · 自动流程：${metadata.auto_workflow_status}${diagnosisText}${artifactErrorText}`
    : `${metadata.status || "-"}${diagnosisText}${artifactErrorText}`;
  els.projectStatus.title = renderArtifactLoadErrorTitle(metadata.artifact_load_errors);
  renderExperienceGuide(state.experience || {});
  if (!analysis) {
    renderEmptyState(metadata);
    els.empty.classList.remove("hidden");
    els.analysisView.classList.add("hidden");
    renderProgressPanel(els.uploadProgress, metadata.analysis_progress, 7);
    return;
  }
  els.empty.classList.add("hidden");
  els.analysisView.classList.remove("hidden");
  const rec = displayProblem(metadata, analysis);
  const selectedSource = selectedProblemSource(metadata);
  els.recommended.textContent = `${selectedSource} ${rec.id || "-"} 题：${rec.title || ""}`;
  els.documentCount.textContent = analysis.contest_summary?.document_count ?? "-";
  els.dataCount.textContent = analysis.contest_summary?.data_count ?? "-";
  const systemRec = analysis.system_recommended_problem || analysis.recommended_problem || {};
  const selectedId = selectedProblemId(metadata);
  renderProblems(analysis.problems || [], selectedId, systemRec.id);
  renderWorkflow(analysis.workflow || [], rec);
  renderInventory(analysis.inventory || []);
  renderStatusCards(metadata, analysis);
  renderProjectReadiness(detail.readiness || {});
  renderPaperOptions(metadata);
  renderModelAssistantOptions(analysis, rec);
  renderRepairCenter(metadata, analysis.project?.id || metadata.id, detail.repair || {});
  renderDeliveryCenter(metadata, analysis.project?.id || metadata.id, detail.delivery || {});
  renderArtifacts(metadata, analysis.project?.id || metadata.id);
  renderAutoWorkflowProgress(metadata.auto_workflow_progress);
  updateAutoWorkflowButtons(metadata.auto_workflow_status, metadata.auto_workflow_progress || {});
  renderModelAssistantProgress(metadata.model_assistant_progress);
  renderProgressPanel(els.uploadProgress, metadata.analysis_progress, 7);
}

function renderArtifactLoadErrorTitle(errors = []) {
  if (!Array.isArray(errors) || !errors.length) {
    return "";
  }
  return errors
    .slice(0, 4)
    .map((item) => `${item.label || "生成文件"}：${item.path || ""} ${item.error || ""}`.trim())
    .join("\n");
}

function renderEmptyState(metadata = {}) {
  if (!els.empty) {
    return;
  }
  if (metadata.metadata_error) {
    els.empty.innerHTML = `
      <h3>项目元数据读取失败。</h3>
      <p>项目文件夹仍在本地，可以先打开文件夹检查 metadata.json，或重新上传赛题材料。</p>
      <p class="status">${escapeHtml(metadata.metadata_error)}</p>
    `;
    return;
  }
  if (metadata.analysis_error) {
    els.empty.innerHTML = `
      <h3>赛题分析文件读取失败。</h3>
      <p>可以重新运行赛题分析，或打开项目文件夹检查 artifacts/analysis.json。</p>
      <p class="status">${escapeHtml(metadata.analysis_error)}</p>
    `;
    return;
  }
  els.empty.innerHTML = `
    <h3>上传一个赛题包后，这里会显示自动分析结果。</h3>
    <p>系统会识别赛题、附件、格式规范，生成推荐选题、任务工作流和 LaTeX 论文骨架。</p>
  `;
}

function selectedProblemSource(metadata) {
  const source = metadata.final_problem?.source;
  if (source === "user") {
    return "用户选择";
  }
  if (source) {
    return "流程选择";
  }
  return "系统推荐";
}

function selectedProblemId(metadata) {
  const finalProblem = metadata.final_problem || {};
  return finalProblem.id || finalProblem.final_problem_id || "";
}

function displayProblem(metadata, analysis) {
  const finalProblem = metadata.final_problem || {};
  const recommended = analysis.recommended_problem || {};
  const finalId = finalProblem.id || finalProblem.final_problem_id;
  if (finalId && finalId !== "Unknown") {
    const matched = (analysis.problems || []).find((problem) => problem.id === finalId) || {};
    return {
      ...matched,
      ...recommended,
      ...finalProblem,
      id: finalId,
      title: finalProblem.title || finalProblem.final_problem_title || matched.title || recommended.title || "",
    };
  }
  return recommended;
}

function diagnosisSummary(diagnosis = {}) {
  if (!diagnosis || typeof diagnosis !== "object" || !diagnosis.category) {
    return "";
  }
  const label = diagnosis.label || diagnosis.category;
  const focus = diagnosis.repair_focus || diagnosis.suggested_action || "可在自动流程进度中查看修复重点";
  return `${label}：${focus}`;
}

function performanceHealthMetrics(metadata = {}) {
  const scores = metadata.performance_health_scores || {};
  const metrics = metadata.performance_health_metrics || {};
  const items = [];
  const overall = metadata.performance_health_score ?? scores.overall;
  const speed = scores.speed ?? metrics.speed;
  const reliability = scores.reliability ?? metrics.reliability;
  if (Number.isFinite(Number(speed))) {
    items.push(["速度", `${Number(speed)}`]);
  }
  if (Number.isFinite(Number(reliability))) {
    items.push(["可靠", `${Number(reliability)}`]);
  }
  if (Number(metrics.attachment_workers) > 0) {
    items.push(["线程", `${Number(metrics.attachment_workers)}`]);
  }
  if (Number(metrics.planned_task_count) > 0) {
    items.push(["任务", `${Number(metrics.planned_task_count)}`]);
  }
  return {
    badge: Number.isFinite(Number(overall)) ? `${Number(overall)} 分` : "",
    items: items.slice(0, 4),
  };
}

function renderStatusCardMetrics(items = []) {
  if (!items.length) {
    return "";
  }
  return `
    <div class="status-card-metrics">
      ${items
        .map(
          ([label, value]) => `
            <span class="status-card-metric">
              <b>${escapeHtml(label)}</b>
              <strong>${escapeHtml(value)}</strong>
            </span>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderStatusCards(metadata, analysis) {
  if (!els.statusCards) {
    return;
  }
  const lastDiagnosis = metadata.last_failure_diagnosis || {};
  const diagnosisDetail = diagnosisSummary(lastDiagnosis);
  const cards = [
    {
      title: "赛题解析",
      value: analysis ? "已完成" : "等待",
      detail: `${analysis?.problems?.length || 0} 个候选题，${analysis?.inventory?.length || 0} 个材料文件`,
      status: analysis ? "success" : "pending",
    },
    {
      title: "自动解题",
      value: statusLabel(metadata.auto_workflow_status),
      detail: diagnosisDetail || "生成代码、运行结果、回填论文",
      status: statusTone(metadata.auto_workflow_status),
    },
    {
      title: "自动修复",
      value: metadata.repair_center_label || statusLabel(metadata.repair_center_status),
      detail: metadata.repair_center_summary || "失败后读取日志并继续生成",
      status: statusTone(metadata.repair_center_status),
    },
    {
      title: "交付就绪",
      value: metadata.delivery_readiness_label || statusLabel(metadata.delivery_readiness_status),
      detail: metadata.delivery_readiness_summary || "论文、结果和支撑材料",
      status: statusTone(metadata.delivery_readiness_status),
      badge: Number.isFinite(Number(metadata.delivery_readiness_score)) ? `${Number(metadata.delivery_readiness_score)} 分` : "",
    },
  ];
  els.statusCards.innerHTML = cards
    .map(
      (card) => `
        <article class="status-card" data-status="${card.status}">
          <span class="status-dot"></span>
          <div>
            <div class="status-card-head">
              <h3>${escapeHtml(card.title)}</h3>
              ${card.badge ? `<span class="status-card-badge">${escapeHtml(card.badge)}</span>` : ""}
            </div>
            <strong>${escapeHtml(card.value)}</strong>
            <p>${escapeHtml(card.detail)}</p>
            ${renderStatusCardMetrics(card.metrics || [])}
          </div>
        </article>
      `,
    )
    .join("");
}

function renderProjectReadiness(readiness = {}) {
  if (!els.projectReadiness) {
    return;
  }
  if (!readiness || !Array.isArray(readiness.checks)) {
    els.projectReadiness.innerHTML = '<p class="status">暂无准备度信息。</p>';
    return;
  }
  const status = statusTone(readiness.status);
  const score = Number.isFinite(Number(readiness.score)) ? Number(readiness.score) : 0;
  const checks = readiness.checks.slice(0, 7);
  const action = readiness.primary_action || {};
  const actionButton = action.id
    ? `<button class="primary compact" type="button" data-readiness-action="${escapeHtml(action.id)}">${escapeHtml(action.label || "继续")}</button>`
    : "";
  els.projectReadiness.dataset.status = status;
  els.projectReadiness.innerHTML = `
    <section class="readiness-hero" data-status="${escapeHtml(status)}">
      <div class="readiness-score" aria-label="当前准备度 ${escapeHtml(score)} 分">
        <strong>${escapeHtml(score)}</strong>
        <span>分</span>
      </div>
      <div class="readiness-copy">
        <span>准备度</span>
        <h3>${escapeHtml(readiness.label || "当前项目状态")}</h3>
        <p>${escapeHtml(readiness.summary || "")}</p>
      </div>
      ${actionButton}
    </section>
    <div class="readiness-checks">
      ${checks.map(renderReadinessCheck).join("")}
    </div>
  `;
}

function renderReadinessCheck(item = {}) {
  const status = statusTone(item.status);
  const required = item.required ? '<span class="readiness-required">必需</span>' : "";
  return `
    <article class="readiness-check" data-status="${escapeHtml(status)}">
      <span class="readiness-dot" aria-hidden="true"></span>
      <div>
        <strong>${escapeHtml(item.label || "-")}${required}</strong>
        <p>${escapeHtml(item.detail || statusLabel(item.status))}</p>
      </div>
    </article>
  `;
}

function renderRepairCenter(metadata = {}, projectId = "", repair = {}) {
  if (!els.repairCenter) {
    return;
  }
  const payload = repair && typeof repair === "object" ? repair : {};
  const status = payload.status || metadata.repair_center_status || "";
  const label = payload.label || metadata.repair_center_label || statusLabel(status);
  const summary = payload.summary || metadata.repair_center_summary || "尚未生成修复简报。";
  const diagnosis = payload.latest_failure_diagnosis || metadata.last_failure_diagnosis || {};
  const primaryAction = repairPrimaryAction(metadata, payload);
  const actionButton = renderRepairActionButton(primaryAction, projectId, metadata);
  const evidence = Array.isArray(payload.evidence) && payload.evidence.length
    ? payload.evidence
    : repairEvidenceFromMetadata(metadata, diagnosis);
  const evidenceHtml = evidence.length
    ? evidence.slice(0, 8).map(renderRepairEvidenceRow).join("")
    : '<p class="status">暂无阻断证据。</p>';
  const reportLinks = renderRepairReportLinks(metadata, projectId);
  const generatedAt = payload.generated_at ? `<span>更新 ${escapeHtml(formatProjectTime(payload.generated_at))}</span>` : "";
  const resumeText = metadata.repair_center_can_resume
    ? "可继续生成"
    : status
      ? "当前无需续跑"
      : "需先刷新诊断";

  els.repairCenter.innerHTML = `
    <div class="repair-head" data-status="${escapeHtml(statusTone(status))}">
      <span class="repair-status-dot"></span>
      <div>
        <strong>${escapeHtml(label || "未开始")}</strong>
        <p>${escapeHtml(summary)}</p>
      </div>
      ${actionButton}
    </div>
    <div class="repair-meta">
      <span>${escapeHtml(resumeText)}</span>
      ${primaryAction?.label ? `<span>${escapeHtml(primaryAction.label)}</span>` : ""}
      ${generatedAt}
    </div>
    <div class="repair-evidence">
      ${evidenceHtml}
    </div>
    ${reportLinks}
  `;
}

function repairPrimaryAction(metadata = {}, payload = {}) {
  const action = payload.primary_action && typeof payload.primary_action === "object" ? payload.primary_action : {};
  if (action.id) {
    return action;
  }
  const actions = Array.isArray(payload.actions) ? payload.actions : [];
  if (actions[0]?.id) {
    return actions[0];
  }
  const id = metadata.repair_center_action || "";
  const labels = {
    resume_auto_workflow: "继续生成并自动修复",
    inspect_failure_evidence: "查看失败证据",
    refresh_diagnostics: "刷新诊断与并行计划",
    start_auto_workflow: "启动一键自动流程",
    fix_completeness_gate: "补齐完整性门禁",
    continue_review: "继续编译和审查",
  };
  return id ? { id, label: labels[id] || id, priority: "medium" } : {};
}

function renderRepairActionButton(action = {}, projectId = "", metadata = {}) {
  const command = repairActionCommand(action.id);
  if (!command || !projectId) {
    return "";
  }
  const artifacts = metadata.artifacts || {};
  if (command === "open_report" && !artifacts.repair_briefing && !artifacts.repair_briefing_json && !artifacts.computed_solver_repair) {
    return "";
  }
  return `<button class="repair-action" type="button" data-repair-action="${escapeHtml(command)}">${escapeHtml(action.label || "处理")}</button>`;
}

function repairActionCommand(actionId = "") {
  if (actionId === "resume_auto_workflow" || actionId === "fix_completeness_gate") {
    return "resume";
  }
  if (actionId === "start_auto_workflow") {
    return "start";
  }
  if (actionId === "refresh_diagnostics") {
    return "diagnostics";
  }
  if (actionId === "inspect_failure_evidence" || actionId === "continue_review") {
    return "open_report";
  }
  return "";
}

function repairEvidenceFromMetadata(metadata = {}, diagnosis = {}) {
  const rows = [];
  if (diagnosis?.category) {
    rows.push({
      label: diagnosis.label || diagnosis.category,
      detail: diagnosis.repair_focus || diagnosis.suggested_action || diagnosis.evidence || "",
      source: "last_failure_diagnosis",
    });
  }
  [
    ["自动流程", metadata.auto_workflow_status],
    ["代码求解", metadata.computed_solution_status],
    ["性能健康", metadata.performance_health_label || metadata.performance_health_status],
    ["论文回填", metadata.paper_fill_status],
    ["LaTeX", metadata.compile_status],
  ].forEach(([label, detail]) => {
    if (detail) {
      rows.push({ label, detail, source: "metadata/status" });
    }
  });
  return rows;
}

function renderRepairEvidenceRow(item = {}) {
  return `
    <div class="repair-evidence-row">
      <b>${escapeHtml(item.label || item.source || "证据")}</b>
      <span>${escapeHtml(item.detail || "-")}</span>
    </div>
  `;
}

function renderRepairReportLinks(metadata = {}, projectId = "") {
  const artifacts = metadata.artifacts || {};
  const links = [
    ["repair_briefing", "修复简报"],
    ["repair_briefing_json", "修复 JSON"],
    ["performance_health", "性能健康"],
    ["computed_solver_repair", "自动修复记录"],
    ["computed_solver_log", "代码日志"],
  ]
    .filter(([key]) => projectId && artifacts[key])
    .map(([key, label]) => {
      const path = artifacts[key];
      if (!artifactIsAvailable(metadata, key)) {
        const reason = escapeHtml(artifactMissingReason(metadata, key));
        return `<span class="report-link-missing" title="${reason}">${escapeHtml(label)} · 未生成</span>`;
      }
      return `<a href="/api/projects/${encodeURIComponent(projectId)}/download/${encodeRelativePath(path)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
    });
  return links.length ? `<div class="repair-links">${links.join("")}</div>` : "";
}

function renderDeliveryCenter(metadata = {}, projectId = "", delivery = {}) {
  if (!els.deliveryCenter) {
    return;
  }
  const payload = delivery && typeof delivery === "object" ? delivery : {};
  const status = payload.status || metadata.delivery_readiness_status || "";
  const label = payload.label || metadata.delivery_readiness_label || statusLabel(status);
  const score = payload.score ?? metadata.delivery_readiness_score;
  const summary = payload.summary || metadata.delivery_readiness_summary || "尚未生成交付就绪报告。";
  const checks = Array.isArray(payload.checks) ? payload.checks : deliveryChecksFromMetadata(metadata);
  const primaryAction = deliveryPrimaryAction(metadata, payload, checks);
  const actionButton = renderDeliveryActionButton(primaryAction, projectId);
  const checkHtml = checks.length
    ? checks.slice(0, 10).map(renderDeliveryCheckRow).join("")
    : '<p class="status">暂无交付检查项。</p>';
  const missing = Array.isArray(payload.required_missing) ? payload.required_missing : checks.filter((item) => item.required && item.status === "fail");
  const missingText = missing.length ? `${missing.length} 个必需项缺失` : payload.can_submit || metadata.delivery_readiness_can_submit ? "可提交" : "等待检查";
  const reportLinks = renderDeliveryReportLinks(metadata, projectId);
  const generatedAt = payload.generated_at ? `<span>更新 ${escapeHtml(formatProjectTime(payload.generated_at))}</span>` : "";

  els.deliveryCenter.innerHTML = `
    <div class="delivery-head" data-status="${escapeHtml(statusTone(status))}">
      <span class="delivery-score">${Number.isFinite(Number(score)) ? escapeHtml(Number(score)) : "--"}</span>
      <div>
        <strong>${escapeHtml(label || "未检查")}</strong>
        <p>${escapeHtml(summary)}</p>
      </div>
      ${actionButton}
    </div>
    <div class="delivery-meta">
      <span>${escapeHtml(missingText)}</span>
      ${primaryAction?.label ? `<span>${escapeHtml(primaryAction.label)}</span>` : ""}
      ${generatedAt}
    </div>
    <div class="delivery-checks">
      ${checkHtml}
    </div>
    ${reportLinks}
  `;
}

function deliveryChecksFromMetadata(metadata = {}) {
  return [
    { label: "代码结果", status: metadata.computed_solution_status === "success" ? "pass" : "fail", detail: statusLabel(metadata.computed_solution_status), required: true },
    { label: "论文回填", status: metadata.paper_fill_status === "success" ? "pass" : "warning", detail: statusLabel(metadata.paper_fill_status), required: false },
    { label: "LaTeX 编译", status: metadata.compile_status === "success" ? "pass" : "fail", detail: statusLabel(metadata.compile_status), required: true },
    { label: "论文审查", status: metadata.paper_review_status === "success" ? "pass" : "warning", detail: statusLabel(metadata.paper_review_status), required: false },
  ];
}

function deliveryPrimaryAction(metadata = {}, payload = {}, checks = []) {
  const action = payload.primary_action && typeof payload.primary_action === "object" ? payload.primary_action : {};
  if (action.id) {
    return action;
  }
  const actions = Array.isArray(payload.actions) ? payload.actions : [];
  if (actions[0]?.id) {
    return actions[0];
  }
  const id = metadata.delivery_readiness_action || "";
  const labels = {
    resume_auto_workflow: "继续生成并自动修复",
    analyze_project: "重建赛题分析",
    run_auto_workflow: "启动一键自动流程",
    compile_latex: "编译 PDF/Word",
    review_paper: "审查论文",
    refresh_diagnostics: "刷新诊断/性能",
    refresh_repair: "刷新修复中心",
    build_delivery_package: "生成正式交付包",
    download_support_zip: "下载支撑材料包",
  };
  if (id) {
    return { id, label: labels[id] || id, priority: "medium" };
  }
  const failed = checks.find((item) => item.status === "fail" || item.status === "warning");
  return failed?.action ? { id: failed.action, label: labels[failed.action] || failed.action, priority: failed.required ? "high" : "medium" } : {};
}

function renderDeliveryActionButton(action = {}, projectId = "") {
  const command = deliveryActionCommand(action.id);
  if (!command || !projectId) {
    return "";
  }
  return `<button class="delivery-action" type="button" data-delivery-action="${escapeHtml(command)}">${escapeHtml(action.label || "处理")}</button>`;
}

function deliveryActionCommand(actionId = "") {
  const commands = {
    resume_auto_workflow: "resume",
    analyze_project: "analyze",
    run_auto_workflow: "start",
    compile_latex: "compile",
    review_paper: "review",
    refresh_diagnostics: "diagnostics",
    refresh_repair: "repair",
    build_delivery_package: "package",
    download_support_zip: "support_zip",
  };
  return commands[actionId] || "";
}

function renderDeliveryCheckRow(item = {}) {
  return `
    <div class="delivery-check-row" data-status="${escapeHtml(statusTone(item.status))}">
      <span></span>
      <div>
        <b>${escapeHtml(item.label || item.id || "检查项")}</b>
        <small>${escapeHtml(item.required ? "必需" : "建议")} · ${escapeHtml(statusLabel(item.status))}</small>
        <p>${escapeHtml(item.detail || "-")}</p>
      </div>
    </div>
  `;
}

function renderDeliveryReportLinks(metadata = {}, projectId = "") {
  const artifacts = metadata.artifacts || {};
  const links = [
    ["delivery_readiness", "交付报告"],
    ["delivery_readiness_json", "交付 JSON"],
    ["delivery_package", "正式交付包"],
    ["delivery_package_manifest", "交付包清单"],
    ["delivery_package_manifest_json", "交付包 JSON"],
    ["paper_pdf", "论文 PDF"],
    ["paper_docx", "论文 Word"],
    ["paper_review", "审查报告"],
    ["support_zip", "支撑材料包"],
  ]
    .filter(([key]) => projectId && (key === "support_zip" || artifacts[key]))
    .map(([key, label]) => {
      const path = key === "support_zip" ? "support.zip" : artifacts[key];
      if (!artifactIsAvailable(metadata, key)) {
        const reason = escapeHtml(artifactMissingReason(metadata, key));
        return `<span class="report-link-missing" title="${reason}">${escapeHtml(label)} · 未生成</span>`;
      }
      return `<a href="/api/projects/${encodeURIComponent(projectId)}/download/${encodeRelativePath(path)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
    });
  return links.length ? `<div class="delivery-links">${links.join("")}</div>` : "";
}

function artifactIsAvailable(metadata = {}, key = "") {
  const status = metadata.artifact_status?.[key];
  return !status || (status.exists !== false && status.is_file !== false);
}

function artifactMissingReason(metadata = {}, key = "") {
  return metadata.artifact_status?.[key]?.missing_reason || "文件尚未生成或已被移动";
}

function renderExperienceGuide(experience = {}) {
  if (!els.experienceGuide) {
    return;
  }
  const project = state.currentProject || {};
  const metadata = project.metadata || {};
  const analysis = project.analysis || null;
  const step = currentGuideStep(metadata, analysis, experience);
  els.experienceGuide.dataset.status = step.status || "pending";
  if (els.guideTitle) {
    els.guideTitle.textContent = step.title;
  }
  if (els.guideDetail) {
    els.guideDetail.textContent = step.detail;
  }
  if (els.guideActions) {
    els.guideActions.innerHTML = step.actions
      .map((action) => `<button class="${escapeHtml(action.primary ? "primary compact" : "ghost compact")}" type="button" data-guide-action="${escapeHtml(action.id)}">${escapeHtml(action.label)}</button>`)
      .join("");
  }
  if (els.guideSteps) {
    els.guideSteps.innerHTML = ["上传赛题", "确认选题", "自动求解", "导出交付"]
      .map((label, index) => {
        const number = index + 1;
        const status = number < step.index ? "done" : number === step.index ? "current" : "todo";
        return `<li data-status="${escapeHtml(status)}"><span>${number}</span><b>${escapeHtml(label)}</b></li>`;
      })
      .join("");
  }
}

function currentGuideStep(metadata = {}, analysis = null, experience = {}) {
  const projectId = metadata.id || state.currentProject?.metadata?.id || "";
  const finalProblem = metadata.final_problem || {};
  const autoStatus = metadata.auto_workflow_status || "";
  const deliveryStatus = metadata.delivery_readiness_status || "";
  const hasArtifacts = Boolean(metadata.artifacts && Object.keys(metadata.artifacts).length);
  const configured = state.llmSettings?.configured;

  if (!state.projects.length && !analysis) {
    return guideStep(1, "上传赛题材料", "选择赛题压缩包或文件夹。上传后，系统会自动识别题目、附件和推荐选题。", [
      { id: "focus_upload", label: "选择赛题", primary: true },
    ]);
  }
  if (!analysis) {
    const summary = experience.summary || "先打开一个项目，或继续上传新的赛题材料。";
    return guideStep(1, "打开或上传项目", summary, [
      { id: "focus_projects", label: "查看项目", primary: true },
      { id: "focus_upload", label: "上传新赛题" },
    ]);
  }
  if (!finalProblem.id && !finalProblem.final_problem_id) {
    return guideStep(2, "确认要做哪一题", "先看推荐题和各题评分，确认后再启动自动求解，避免论文和代码跑偏。", [
      { id: "open_problems", label: "去确认选题", primary: true },
    ]);
  }
  if (!configured) {
    return guideStep(3, "配置大模型接口", "自动求解需要先保存并测试大模型接口。通过后再运行一键流程。", [
      { id: "focus_llm", label: "填写接口", primary: true },
      { id: "test_llm", label: "测试连接" },
    ], "warning");
  }
  if (["failed", "completed_with_warnings", "cancelled", "requires_api_key"].includes(autoStatus)) {
    const reason = metadata.last_failure_diagnosis?.suggested_action || metadata.auto_workflow_error || "系统会读取错误日志和上下文继续修复。";
    return guideStep(3, "继续生成并自动修复", reason, [
      { id: "resume_auto", label: "继续并修复", primary: true },
      { id: "open_outputs", label: "查看日志" },
    ], "failed");
  }
  if (["running", "queued", "cancel_requested"].includes(autoStatus)) {
    return guideStep(3, "等待自动求解完成", "大模型正在规划、生成代码、运行结果并回填论文。可以在输出页查看流式进度。", [
      { id: "open_outputs", label: "看进度", primary: true },
      { id: "cancel_auto", label: "中断流程" },
    ], "running");
  }
  if (autoStatus !== "success") {
    return guideStep(3, "启动自动求解", "系统会先解完每个子问题并生成图表，再撰写论文、编译和审查。", [
      { id: "start_auto", label: "一键求解", primary: true },
      { id: "open_outputs", label: "查看输出区" },
    ]);
  }
  if (deliveryStatus !== "ready" && deliveryStatus !== "success") {
    return guideStep(4, "检查论文并生成交付包", "自动求解已完成。下一步检查论文、编译 PDF/Word，并生成支撑材料包。", [
      { id: "compile", label: "编译论文", primary: !hasArtifacts },
      { id: "review", label: "审查论文" },
      { id: "refresh_delivery", label: "刷新交付" },
    ], "success");
  }
  return guideStep(4, "交付文件已就绪", "论文、结果和支撑材料已经进入交付阶段。可以打开项目文件夹或在生成文件里下载。", [
    { id: "open_project_root", label: "打开文件夹", primary: true },
    { id: "open_outputs", label: "查看生成文件" },
  ], "success");
}

function guideStep(index, title, detail, actions = [], status = "pending") {
  return { index, title, detail, actions, status };
}

function renderGrowthCenter(growth = {}) {
  if (!els.growthCenter) {
    return;
  }
  const metrics = Array.isArray(growth.metrics) ? growth.metrics : [];
  const funnel = Array.isArray(growth.funnel) ? growth.funnel : [];
  const signals = Array.isArray(growth.signals) ? growth.signals : [];
  const action = growth.recommended_action || {};
  const actionCommand = growthActionCommand(action);
  const deliveryBatch = growth.delivery_batch || {};
  const workflow = growth.workflow || {};
  const generatedAt = growth.generated_at ? `<span>更新 ${escapeHtml(formatProjectTime(growth.generated_at))}</span>` : "";
  els.growthCenter.innerHTML = `
    <section class="growth-hero" data-status="${escapeHtml(statusTone(growth.status))}">
      <div>
        <strong>${escapeHtml(growth.label || "解题待命")}</strong>
        <p>${escapeHtml(growth.summary || "上传赛题后会汇总分析、求解、交付和打包进度。")}</p>
      </div>
      ${generatedAt}
    </section>
    <div class="growth-metrics">
      ${metrics.length ? metrics.map(renderGrowthMetric).join("") : '<p class="status">暂无解题指标。</p>'}
    </div>
    <div class="growth-funnel">
      ${funnel.length ? funnel.map(renderGrowthFunnelRow).join("") : ""}
    </div>
    ${renderGrowthDeliveryBatch(deliveryBatch)}
    ${renderGrowthWorkflow(workflow)}
    <div class="growth-footer">
      ${action.label ? `
        <div class="growth-action">
          <div>
            <b>${escapeHtml(action.label)}</b>
            <span>${escapeHtml(action.detail || "")}</span>
          </div>
          ${actionCommand ? `<button class="growth-action-button" type="button" data-growth-action="${escapeHtml(actionCommand)}">${escapeHtml(action.label)}</button>` : ""}
        </div>
      ` : ""}
      ${signals.length ? `<div class="growth-signals">${signals.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
    </div>
  `;
}

function growthActionCommand(action = {}) {
  const command = action.command || "";
  if (command === "batch_delivery_packages" || action.id === "build_packages") {
    return "batch_packages";
  }
  return "";
}

function renderGrowthDeliveryBatch(batch = {}) {
  if (!batch.id) {
    return "";
  }
  const packaged = Number(batch.packaged_count) || 0;
  const skipped = Number(batch.skipped_count) || 0;
  const failed = Number(batch.failed_count) || 0;
  const requested = Number(batch.requested_count) || 0;
  const duration = formatDuration(batch.duration_seconds || 0);
  const size = Number(batch.total_package_bytes) || 0;
  const sizeText = size ? ` · ${formatBytes(size)}` : "";
  const generatedAt = batch.generated_at ? ` · ${formatProjectTime(batch.generated_at)}` : "";
  const tone = failed ? "failed" : packaged ? "success" : "warning";
  return `
    <article class="growth-batch" data-status="${escapeHtml(tone)}">
      <div>
        <b>最近批量交付包</b>
        <span>${escapeHtml(`请求 ${requested} · 生成 ${packaged} · 跳过 ${skipped} · 失败 ${failed}`)}</span>
      </div>
      <p>${escapeHtml(`并发 ${batch.max_workers || 0} · 耗时 ${duration}${sizeText}${generatedAt}`)}</p>
    </article>
  `;
}

function renderGrowthWorkflow(workflow = {}) {
  if (!workflow || !workflow.stage) {
    return "";
  }
  const proofPoints = Array.isArray(workflow.proof_points) ? workflow.proof_points : [];
  const risks = Array.isArray(workflow.risks) ? workflow.risks : [];
  const actions = Array.isArray(workflow.actions) ? workflow.actions : [];
  const solutionAssets = Number(workflow.solution_assets) || 0;
  const packages = Number(workflow.package_count) || 0;
  const hoursSaved = Number(workflow.estimated_hours_saved) || 0;
  return `
    <section class="growth-workflow" data-status="${escapeHtml(statusTone(workflow.stage))}">
      <div class="growth-workflow-head">
        <div>
          <b>${escapeHtml(workflow.label || "解题准备度")}</b>
          <p>${escapeHtml(workflow.summary || "")}</p>
        </div>
        <strong>${escapeHtml(workflow.score ?? 0)}/100</strong>
      </div>
      <div class="growth-workflow-metrics">
        <span><b>解题资产</b><strong>${escapeHtml(solutionAssets)}</strong></span>
        <span><b>正式交付包</b><strong>${escapeHtml(packages)}</strong></span>
        <span><b>节省工时</b><strong>${escapeHtml(hoursSaved ? `${hoursSaved.toFixed(1)}h` : "-")}</strong></span>
      </div>
      ${proofPoints.length ? `<div class="growth-workflow-proof">${proofPoints.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      ${risks.length ? `<ul class="growth-workflow-risks">${risks.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
      ${actions.length ? `<div class="growth-workflow-actions">${actions.map((item) => `
        <article>
          <b>${escapeHtml(item.label || item.id || "动作")}</b>
          <p>${escapeHtml(item.detail || "")}</p>
        </article>
      `).join("")}</div>` : ""}
    </section>
  `;
}

function renderGrowthMetric(item = {}) {
  return `
    <article class="growth-metric" data-status="${escapeHtml(statusTone(item.status))}">
      <span></span>
      <div>
        <b>${escapeHtml(item.label || item.id || "指标")}</b>
        <strong>${escapeHtml(item.value ?? "-")}</strong>
        <p>${escapeHtml(item.detail || "")}</p>
      </div>
    </article>
  `;
}

function renderGrowthFunnelRow(row = {}) {
  const conversion = Math.max(0, Math.min(100, Number(row.conversion) || 0));
  return `
    <article class="growth-funnel-row">
      <div>
        <b>${escapeHtml(row.label || row.id || "阶段")}</b>
        <span>${escapeHtml(row.count ?? 0)} · ${conversion}%</span>
      </div>
      <div class="growth-funnel-track"><i style="width: ${conversion}%"></i></div>
      <p>${escapeHtml(row.detail || "")}</p>
    </article>
  `;
}

function renderTrustCenter(trust = {}, trustExports = null) {
  if (!els.trustCenter) {
    return;
  }
  const exportsPayload = trustExports || state.trustExports || {};
  const latestExport = exportsPayload.latest || {};
  const latestCampaign = (state.repairCampaigns || {}).latest || {};
  const metrics = Array.isArray(trust.metrics) ? trust.metrics : [];
  const sla = Array.isArray(trust.sla) ? trust.sla : [];
  const evidence = Array.isArray(trust.evidence) ? trust.evidence : [];
  const incidents = Array.isArray(trust.incidents) ? trust.incidents : [];
  const actions = Array.isArray(trust.actions) ? trust.actions : [];
  const generatedAt = trust.generated_at ? `<span>${escapeHtml(formatProjectTime(trust.generated_at))}</span>` : "";
  els.trustCenter.innerHTML = `
    <section class="trust-hero" data-status="${escapeHtml(statusTone(trust.status))}">
      <div>
        <b>${escapeHtml(trust.label || "信任中心")}</b>
        <p>${escapeHtml(trust.summary || "项目运行后会在这里汇总质量、交付和可审计证据。")}</p>
      </div>
      <strong>${escapeHtml(trust.score ?? 0)}/100</strong>
      ${generatedAt}
    </section>
    ${renderTrustExportPanel(latestExport)}
    ${renderRepairCampaignPanel(latestCampaign)}
    <div class="trust-metrics">
      ${metrics.length ? metrics.map(renderTrustMetric).join("") : '<p class="status">暂无信任指标。</p>'}
    </div>
    <div class="trust-sla">
      ${sla.length ? sla.map(renderTrustSlaRow).join("") : ""}
    </div>
    <div class="trust-grid">
      ${renderTrustList("证据", evidence, "evidence")}
      ${renderTrustList("异常", incidents, "incident")}
    </div>
    ${actions.length ? `<div class="trust-actions">${actions.map(renderTrustAction).join("")}</div>` : ""}
  `;
}

function renderRepairCampaignPanel(latest = {}) {
  const hasLatest = Boolean(latest && latest.id);
  const latestText = hasLatest
    ? `最近 ${formatProjectTime(latest.generated_at)} · ${latest.summary || `${latest.queued || 0} 个已入队，${latest.briefed || 0} 个已重建简报`}`
    : "尚未运行修复行动。";
  return `
    <section class="trust-campaign">
      <div>
        <b>修复行动</b>
        <p>${escapeHtml(latestText)}</p>
      </div>
      <div class="trust-campaign-actions">
        <button class="trust-campaign-button" type="button" data-trust-action="repair_campaign">运行修复行动</button>
      </div>
    </section>
  `;
}

function renderTrustExportPanel(latest = {}) {
  const hasLatest = Boolean(latest && latest.download_url);
  const sizeText = latest.size ? ` · ${latest.size}` : "";
  const hashText = latest.sha256 ? ` · SHA256 ${String(latest.sha256).slice(0, 12)}` : "";
  const latestText = hasLatest
    ? `最近 ${formatProjectTime(latest.generated_at)} · 评分 ${latest.trust_score ?? "-"}${sizeText}${hashText}`
    : "尚未导出审计包。";
  return `
    <section class="trust-export">
      <div>
        <b>审计包</b>
        <p>${escapeHtml(latestText)}</p>
      </div>
      <div class="trust-export-actions">
        <button class="trust-export-button" type="button" data-trust-action="export_audit">导出审计包</button>
        ${hasLatest ? `<a class="trust-export-link" href="${escapeHtml(latest.download_url)}" target="_blank" rel="noreferrer">下载最新包</a>` : ""}
      </div>
    </section>
  `;
}

function renderTrustMetric(item = {}) {
  return `
    <article class="trust-metric" data-status="${escapeHtml(statusTone(item.status))}">
      <b>${escapeHtml(item.label || item.id || "指标")}</b>
      <strong>${escapeHtml(item.value ?? "-")}</strong>
      <p>${escapeHtml(item.detail || "")}</p>
    </article>
  `;
}

function renderTrustSlaRow(row = {}) {
  const value = Number.isFinite(Number(row.value)) ? Math.max(0, Math.min(100, Number(row.value))) : 0;
  const labelValue = Number.isFinite(Number(row.value)) ? `${Math.round(value)}%` : "-";
  return `
    <article class="trust-sla-row" data-status="${escapeHtml(statusTone(row.status))}">
      <div>
        <b>${escapeHtml(row.label || row.id || "SLA")}</b>
        <span>${escapeHtml(labelValue)} / 目标 ${escapeHtml(row.target ?? "-")}%</span>
      </div>
      <div class="trust-sla-track"><i style="width: ${value}%"></i></div>
      <p>${escapeHtml(row.detail || "")}</p>
    </article>
  `;
}

function renderTrustList(title, rows = [], kind = "evidence") {
  return `
    <section class="trust-list trust-list-${escapeHtml(kind)}">
      <b>${escapeHtml(title)}</b>
      ${
        rows.length
          ? rows.map((item) => `
            <article data-status="${escapeHtml(statusTone(item.status))}">
              <strong>${escapeHtml(item.label || item.id || "-")}</strong>
              <p>${escapeHtml(item.detail || "")}</p>
            </article>
          `).join("")
          : `<p class="status">${kind === "incident" ? "暂无活跃异常。" : "暂无证据。"}</p>`
      }
    </section>
  `;
}

function renderTrustAction(action = {}) {
  return `
    <article>
      <b>${escapeHtml(action.label || action.id || "动作")}</b>
      <p>${escapeHtml(action.detail || "")}</p>
    </article>
  `;
}

function renderAutoJobCenter(snapshot = {}, deliverySnapshot = {}) {
  if (!els.autoJobCenter) {
    return;
  }
  const autoJobs = Array.isArray(snapshot.jobs) ? snapshot.jobs.map((job) => ({ ...job, kind: job.kind || "auto_workflow" })) : [];
  const deliveryJobs = Array.isArray(deliverySnapshot.jobs) ? deliverySnapshot.jobs.map((job) => ({ ...job, kind: "delivery_batch" })) : [];
  const jobs = [...deliveryJobs, ...autoJobs].sort((a, b) => String(b.submitted_at || "").localeCompare(String(a.submitted_at || "")));
  const throughput = snapshot.throughput || {};
  const capacitySettings = state.capacitySettings || snapshot.capacity_settings || deliverySnapshot.capacity_settings || {};
  const metrics = [
    ["并发槽", snapshot.capacity ?? 0],
    ["运行", snapshot.running_count ?? 0],
    ["排队", snapshot.queued_count ?? 0],
    ["可用", snapshot.available_slots ?? 0],
    ["历史", snapshot.finished_count ?? 0],
  ];
  const metricHtml = metrics
    .map(
      ([label, value]) => `
        <span class="job-metric">
          <b>${escapeHtml(label)}</b>
          <strong>${escapeHtml(value)}</strong>
        </span>
      `,
    )
    .join("");
  const jobsHtml = jobs.length
    ? jobs.map(renderAutoJobRow).join("")
    : '<p class="status">当前没有后台自动流程任务。</p>';
  els.autoJobCenter.innerHTML = `
    <div class="job-center-summary">
      ${metricHtml}
    </div>
    ${renderThroughputPanel(throughput)}
    ${renderCapacityAutotunePanel(state.capacityAutotune)}
    ${renderCapacitySettingsPanel(capacitySettings, snapshot, deliverySnapshot)}
    <div class="job-list">
      ${jobsHtml}
    </div>
  `;
}

function renderCapacitySettingsPanel(settings = {}, snapshot = {}, deliverySnapshot = {}) {
  const autoWorkers = Number(settings.auto_workflow_workers || snapshot.capacity || 2);
  const deliveryJobWorkers = Number(settings.delivery_batch_job_workers || deliverySnapshot.capacity || 1);
  const packageWorkers = Number(settings.delivery_package_workers || 4);
  const maxAuto = Number(settings.max_auto_workflow_workers || 8);
  const maxDeliveryJobs = Number(settings.max_delivery_batch_job_workers || 4);
  const maxPackage = Number(settings.max_delivery_package_workers || 8);
  const source = settings.source ? ` · ${settings.source}` : "";
  return `
    <form class="capacity-panel" data-capacity-form>
      <div>
        <b>容量设置</b>
        <p>调整运行时并发上限，用于提升求解、打包和结果查看响应速度${escapeHtml(source)}。</p>
      </div>
      <label>
        <span>自动流程槽</span>
        <input class="text-input" name="auto_workflow_workers" type="number" min="1" max="${escapeHtml(maxAuto)}" value="${escapeHtml(autoWorkers)}" />
      </label>
      <label>
        <span>批量任务</span>
        <input class="text-input" name="delivery_batch_job_workers" type="number" min="1" max="${escapeHtml(maxDeliveryJobs)}" value="${escapeHtml(deliveryJobWorkers)}" />
      </label>
      <label>
        <span>打包线程</span>
        <input class="text-input" name="delivery_package_workers" type="number" min="1" max="${escapeHtml(maxPackage)}" value="${escapeHtml(packageWorkers)}" />
      </label>
      <button class="capacity-save" type="submit">应用</button>
    </form>
  `;
}

function renderCapacityAutotunePanel(autotune = {}) {
  const latest = autotune?.latest || (autotune?.status ? autotune : null);
  if (!latest) {
    return "";
  }
  const updates = latest.updates && typeof latest.updates === "object" ? latest.updates : {};
  const signals = latest.signals && typeof latest.signals === "object" ? latest.signals : {};
  const updateText = Object.entries(updates).length
    ? Object.entries(updates)
      .map(([key, value]) => `${capacitySettingLabel(key)} -> ${value}`)
      .join(" | ")
    : "无需调整容量";
  const signalText = [
    ["自动队列", signals.auto_queue],
    ["压力", signals.active_pressure],
    ["交付队列", signals.delivery_queue],
    ["打包积压", signals.package_backlog],
  ]
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([label, value]) => `<span><b>${escapeHtml(label)}</b><strong>${escapeHtml(value)}</strong></span>`)
    .join("");
  return `
    <section class="capacity-autotune" data-status="${escapeHtml(statusTone(latest.status === "applied" ? "success" : "idle"))}">
      <div>
        <b>自动调优审计</b>
        <p>${escapeHtml(latest.summary || "尚未运行容量推荐。")}</p>
      </div>
      <strong>${escapeHtml(updateText)}</strong>
      ${signalText ? `<div class="capacity-autotune-signals">${signalText}</div>` : ""}
    </section>
  `;
}

function capacitySettingLabel(key = "") {
  const labels = {
    auto_workflow_workers: "自动流程槽",
    delivery_batch_job_workers: "批量任务槽",
    delivery_package_workers: "打包线程",
  };
  return labels[key] || String(key || "").replaceAll("_", " ");
}

function renderThroughputPanel(throughput = {}) {
  if (!throughput || typeof throughput !== "object" || !Object.keys(throughput).length) {
    return "";
  }
  const utilization = Number(throughput.utilization || 0);
  const pressure = Number(throughput.active_pressure || 0);
  const metrics = [
    ["推荐槽", `${throughput.recommended_workers ?? throughput.capacity ?? 0}/${throughput.max_configurable_workers ?? 8}`],
    ["利用率", `${Math.round(utilization * 100)}%`],
    ["压力", `${pressure.toFixed(2)}x`],
    ["下个启动", formatDuration(throughput.eta_next_start_seconds)],
    ["队列清空", formatDuration(throughput.eta_queue_clear_seconds)],
    ["成功率", Number.isFinite(Number(throughput.recent_success_rate)) ? `${throughput.recent_success_rate}%` : "-"],
  ];
  const signals = Array.isArray(throughput.signals) ? throughput.signals : [];
  const currentCapacity = Number(throughput.capacity || 0);
  const maxWorkers = Number(throughput.max_configurable_workers || 0);
  const recommendedWorkers = Number(throughput.recommended_workers || currentCapacity || 0);
  const boundedRecommendation = Math.max(
    1,
    Math.min(maxWorkers || recommendedWorkers || 1, Number.isFinite(recommendedWorkers) ? Math.round(recommendedWorkers) : currentCapacity || 1),
  );
  const canAutotune = throughput.runtime_configurable === true;
  const autotuneLabel = boundedRecommendation > currentCapacity ? `应用 ${boundedRecommendation} 个槽位` : "应用推荐";
  return `
    <section class="throughput-panel" data-status="${escapeHtml(statusTone(throughput.status))}">
      <div class="throughput-head">
        <span class="throughput-dot"></span>
        <div>
          <strong>${escapeHtml(throughput.label || "吞吐状态")}</strong>
          <p>${escapeHtml(throughput.summary || "后台任务池处于待命状态。")}</p>
        </div>
      </div>
      <div class="throughput-metrics">
        ${metrics.map(([label, value]) => `
          <span>
            <b>${escapeHtml(label)}</b>
            <strong>${escapeHtml(value)}</strong>
          </span>
        `).join("")}
      </div>
      ${throughput.scaling_action ? `<p class="throughput-action">${escapeHtml(throughput.scaling_action)}</p>` : ""}
      ${signals.length ? `<div class="throughput-signals">${signals.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      ${canAutotune ? `
        <div class="throughput-tools">
          <button class="throughput-apply" type="button" data-capacity-action="autotune" title="应用容量推荐">${escapeHtml(autotuneLabel)}</button>
        </div>
      ` : ""}
    </section>
  `;
}

function renderAutoJobRow(job = {}) {
  if (job.kind === "delivery_batch") {
    return renderDeliveryBatchJobRow(job);
  }
  const currentId = state.currentProject?.metadata?.id || "";
  const projectName = job.project_name || job.project_id || "项目";
  const isCurrent = currentId && job.project_id === currentId;
  const timing = job.status === "queued"
    ? `等待 ${formatDuration(job.wait_seconds)}`
    : job.status === "running"
      ? `运行 ${formatDuration(job.run_seconds)}`
      : `耗时 ${formatDuration(job.run_seconds)}`;
  const mode = job.resume ? "继续生成" : "一键流程";
  const error = job.error ? `<p>${escapeHtml(job.error)}</p>` : "";
  return `
    <article class="job-row${isCurrent ? " is-current" : ""}" data-status="${escapeHtml(statusTone(job.status))}">
      <span class="job-status-dot"></span>
      <div class="job-main">
        <strong>${escapeHtml(projectName)}</strong>
        <small>${escapeHtml(mode)} · ${escapeHtml(statusLabel(job.status))} · ${escapeHtml(timing)}</small>
        ${error}
      </div>
      <button class="job-open" type="button" data-project-id="${escapeHtml(job.project_id || "")}">打开</button>
    </article>
  `;
}

function renderDeliveryBatchJobRow(job = {}) {
  const timing = job.status === "queued"
    ? `等待 ${formatDuration(job.wait_seconds)}`
    : job.status === "running"
      ? `运行 ${formatDuration(job.run_seconds)}`
      : `耗时 ${formatDuration(job.run_seconds)}`;
  const counts = `请求 ${job.requested_count || 0} · 生成 ${job.packaged_count || 0} · 跳过 ${job.skipped_count || 0} · 失败 ${job.failed_count || 0}`;
  const detail = job.summary || counts;
  const error = job.error ? `<p>${escapeHtml(job.error)}</p>` : "";
  return `
    <article class="job-row job-row-delivery" data-status="${escapeHtml(statusTone(job.status))}">
      <span class="job-status-dot"></span>
      <div class="job-main">
        <strong>批量交付包</strong>
        <small>${escapeHtml(statusLabel(job.status))} · ${escapeHtml(timing)} · ${escapeHtml(counts)}</small>
        <p>${escapeHtml(detail)}</p>
        ${error}
      </div>
      <span class="job-open job-open-static">交付</span>
    </article>
  `;
}

function formatDuration(value) {
  const seconds = Math.max(0, Number(value) || 0);
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) {
    return `${minutes}m ${rest}s`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function statusLabel(value) {
  const labels = {
    success: "已完成",
    analyzed: "已分析",
    running: "运行中",
    queued: "排队中",
    failed: "失败",
    completed_with_warnings: "需复核",
    requires_api_key: "待配置",
    script_generated: "已生成",
    between_steps: "阶段切换中",
    cancel_requested: "正在中断",
    cancelled: "已中断",
    interrupted: "可继续",
    idle: "未开始",
    warning: "需注意",
    action_required: "需修复",
    repairable: "可继续",
    optimize: "可优化",
    ready: "可启动",
    clear: "无阻断",
    healthy: "稳定",
    busy: "高负载",
    saturated: "拥堵",
    growth_ready: "解题就绪",
    delivery_ready: "待打包",
    operating: "运行中",
    building: "建设中",
    empty: "等待项目",
    deliverable: "可提交",
    blocked: "不可提交",
    needs_work: "需补齐",
    review: "需复核",
    pass: "通过",
    fail: "失败",
    submission_ready: "提交就绪",
    solution_ready: "求解就绪",
    incubating: "培育中",
    trusted: "可信",
    watch: "观察中",
    at_risk: "存在风险",
    hot: "高意向",
    warm: "跟进中",
    nurture: "培育中",
    packaged: "已打包",
    skipped: "已跳过",
  };
  return labels[value] || value || "未开始";
}

function statusTone(value) {
  if (value === "success" || value === "analyzed" || value === "script_generated" || value === "clear" || value === "healthy" || value === "ready" || value === "growth_ready" || value === "deliverable" || value === "pass" || value === "submission_ready" || value === "trusted") {
    return "success";
  }
  if (value === "running" || value === "queued" || value === "cancel_requested" || value === "operating") {
    return "running";
  }
  if (value === "failed" || value === "interrupted" || value === "action_required" || value === "saturated" || value === "blocked" || value === "fail" || value === "at_risk") {
    return "failed";
  }
  if (value === "warning" || value === "completed_with_warnings" || value === "requires_api_key" || value === "cancelled" || value === "repairable" || value === "optimize" || value === "busy" || value === "delivery_ready" || value === "building" || value === "needs_work" || value === "review" || value === "solution_ready" || value === "incubating" || value === "watch") {
    return "warning";
  }
  return "pending";
}

function renderPaperOptions(metadata) {
  const options = metadata.paper_options || {};
  const templateId = options.template_id || "builtin-default";
  renderTemplateSelect(templateId);
  if (els.targetBodyPages) {
    els.targetBodyPages.value = options.target_body_pages || "";
  }
  if (els.paperOptionsStatus) {
    const pages = options.target_body_pages ? `${options.target_body_pages} 页` : "未设置";
    els.paperOptionsStatus.textContent = `当前正文目标：${pages}`;
  }
}

function renderModelAssistantOptions(analysis, displayRec = null) {
  const rec = displayRec || analysis.recommended_problem || {};
  const tasks = rec.tasks || [];
  const baseLabel = `${rec.id || "推荐题"}：${rec.title || "整体问题"}`;
  const options = [`<option value="${escapeHtml(baseLabel)}">${escapeHtml(baseLabel)}</option>`];
  tasks.forEach((task, index) => {
    const label = `问题 ${index + 1}：${task}`;
    options.push(`<option value="${escapeHtml(label)}">${escapeHtml(label)}</option>`);
  });
  els.assistProblemSelect.innerHTML = options.join("");
}

function syncProjectSelection() {
  const currentId = state.currentProject?.metadata?.id;
  els.projectList.querySelectorAll(".project-button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.projectId === currentId);
  });
}

function renderChipRow(items, className = "") {
  return (items || [])
    .filter(Boolean)
    .slice(0, 6)
    .map((item) => `<span class="chip ${className}">${escapeHtml(item)}</span>`)
    .join("");
}

function renderScoreBreakdown(breakdown = {}) {
  const rows = [
    ["data", "数据", 25],
    ["task", "任务", 25],
    ["model", "模型", 20],
    ["computation", "计算", 20],
    ["paper", "论文", 20],
  ];
  const items = rows
    .filter(([key]) => breakdown[key] !== undefined && breakdown[key] !== null)
    .map(([key, label, max]) => {
      const value = Number(breakdown[key]) || 0;
      const width = Math.max(0, Math.min(100, (value / max) * 100));
      return `
        <div class="score-breakdown-row">
          <span>${escapeHtml(label)}</span>
          <span class="score-track"><i style="width: ${width}%"></i></span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `;
    })
    .join("");
  if (!items) {
    return "";
  }
  const risk = breakdown.risk_penalty !== undefined ? `<span>风险扣分 ${escapeHtml(breakdown.risk_penalty)}</span>` : "";
  return `
    <div class="score-breakdown">
      ${items}
      ${risk ? `<div class="score-risk">${risk}</div>` : ""}
    </div>
  `;
}

function renderProblems(problems, selectedId, systemRecommendedId = "") {
  if (!problems.length) {
    els.problemCards.innerHTML = '<p class="status">尚未生成选题分析。</p>';
    return;
  }
  els.problemCards.innerHTML = problems
    .map((problem) => {
      const selected = problem.id === selectedId ? " selected" : "";
      const isSystemRecommended = problem.id === systemRecommendedId;
      const tasks = (problem.tasks || []).slice(0, 2).map((task) => `<li>${escapeHtml(task)}</li>`).join("");
      const modelTypes = renderChipRow(problem.model_types, "is-muted");
      const methods = renderChipRow(problem.suggested_methods);
      const risks = renderChipRow(problem.risk_items, "is-risk");
      const scoreBreakdown = renderScoreBreakdown(problem.score_breakdown);
      const selectDisabled = problem.id === selectedId ? " disabled" : "";
      const selectLabel = problem.id === selectedId ? "已选择" : "选择此题";
      const quickSignals = [
        problem.ai_fit ? `智能适配 ${problem.ai_fit}` : "",
        problem.feasibility ? `可行性 ${problem.feasibility}` : "",
      ].filter(Boolean);
      const detailBlocks = [
        scoreBreakdown,
        modelTypes ? `<div class="chip-row"><b>模型类型</b>${modelTypes}</div>` : "",
        methods ? `<div class="chip-row"><b>可用方法</b>${methods}</div>` : "",
        risks ? `<div class="chip-row"><b>主要风险</b>${risks}</div>` : "",
      ].filter(Boolean).join("");
      return `
        <article class="problem-card${selected}">
          <div class="problem-head">
            <div class="problem-title">
              <h3>${escapeHtml(problem.id)} 题</h3>
              <p class="problem-subtitle">${escapeHtml(problem.title)}</p>
            </div>
            <div class="problem-badges">
              ${problem.id === selectedId ? '<span class="selection-badge">已选择</span>' : ""}
              ${isSystemRecommended ? '<span class="recommend-badge">系统推荐</span>' : ""}
            </div>
          </div>
          <div class="problem-quick">
            <span class="problem-score">综合得分 ${escapeHtml(problem.fit_score)}</span>
            ${quickSignals.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
          </div>
          ${tasks ? `<ul class="problem-meta">${tasks}</ul>` : ""}
          ${detailBlocks ? `<details class="problem-details"><summary>查看方法、评分和风险</summary>${detailBlocks}</details>` : ""}
          <button class="select-problem-button" type="button" data-problem-id="${escapeHtml(problem.id)}"${selectDisabled}>${selectLabel}</button>
        </article>
      `;
    })
    .join("");
  els.problemCards.querySelectorAll(".select-problem-button").forEach((button) => {
    button.addEventListener("click", () => selectProblem(button.dataset.problemId));
  });
  if (els.problemSelectionStatus) {
    els.problemSelectionStatus.textContent = selectedId
      ? `当前后续自动解题与论文生成将使用 ${selectedId} 题。`
      : "请先选择一个题目，再运行一键自动流程。";
  }
}

async function selectProblem(problemId) {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    if (els.problemSelectionStatus) {
      els.problemSelectionStatus.textContent = "请先打开一个项目。";
    }
    return;
  }
  if (!problemId) {
    if (els.problemSelectionStatus) {
      els.problemSelectionStatus.textContent = "未识别到要选择的题号。";
    }
    return;
  }
  if (els.problemSelectionStatus) {
    els.problemSelectionStatus.textContent = `正在选择 ${problemId} 题。`;
  }
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/problem/selection`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem_id: problemId }),
    });
    renderProject(payload.project);
    if (els.problemSelectionStatus) {
      els.problemSelectionStatus.textContent = `已选择 ${problemId} 题，后续一键流程会以该题为准。`;
    }
    await loadProjects();
  } catch (error) {
    if (els.problemSelectionStatus) {
      els.problemSelectionStatus.textContent = `选择失败：${error.message}`;
    }
  }
}

function renderWorkflow(workflow, displayRec = null) {
  if (!workflow.length) {
    els.workflow.innerHTML = '<p class="status">尚未生成工作流。</p>';
    return;
  }
  els.workflow.innerHTML = workflow
    .map(
      (item, index) => {
        const output =
          index === 0 && displayRec?.id && displayRec.id !== "Unknown"
            ? `确认选择 ${displayRec.id} 题：${displayRec.title || ""}`
            : item.output;
        return `
        <div class="workflow-step">
          <span class="workflow-index">${index + 1}</span>
          <strong>${escapeHtml(item.stage)}</strong>
          <span>${escapeHtml(item.owner)}</span>
          <span>${escapeHtml(output)}</span>
        </div>
      `;
      },
    )
    .join("");
}

function renderInventory(inventory) {
  if (!inventory.length) {
    els.inventory.innerHTML = '<p class="status">没有解析到文件</p>';
    return;
  }
  els.inventory.innerHTML = inventory
    .map((item) => {
      const schema = item.schema ? summarizeSchema(item.schema) : `${Math.round(item.size / 1024)} KB`;
      return `
        <div class="inventory-item">
          <span class="pill">${escapeHtml(item.kind)}</span>
          <span class="file-path">${escapeHtml(item.path)}</span>
          <span class="inventory-size">${escapeHtml(schema)}</span>
        </div>
      `;
    })
    .join("");
}

function summarizeSchema(schema) {
  if (schema.type === "csv") {
    return `${schema.rows ?? "-"} 行 · ${schema.cols ?? "-"} 列`;
  }
  if (schema.type === "excel") {
    const sheets = schema.sheets || [];
    return `${sheets.length} 个工作表`;
  }
  return "已解析";
}

function renderArtifacts(metadata, projectId) {
  const artifacts = metadata.artifacts || {};
  const artifactStatus = metadata.artifact_status || {};
  const artifactSummary = metadata.artifact_summary || {};
  const items = [
    ["analysis_report", "分析报告"],
    ["outline", "论文提纲"],
    ["model_plan", "模型计划"],
    ["latex_skeleton", "LaTeX 骨架"],
    ["modeling_script", "建模脚本"],
    ["modeling_log", "建模日志"],
    ["modeling_manifest", "结果清单"],
    ["baseline_summary", "基线结果摘要"],
    ["specialized_script", "专项脚本"],
    ["specialized_log", "专项日志"],
    ["specialized_manifest", "专项结果清单"],
    ["specialized_summary", "专项结果摘要"],
    ["material_passport", "材料护照"],
    ["attachment_profile", "并发附件画像"],
    ["attachment_profile_json", "并发附件画像 JSON"],
    ["parallel_task_plan", "并行求解任务计划"],
    ["parallel_task_plan_json", "并行求解任务计划 JSON"],
    ["llm_problem_structure", "大模型赛题结构增强"],
    ["llm_problem_analysis", "大模型赛题分析"],
    ["llm_baseline_review", "大模型基线复盘"],
    ["llm_specialized_review", "大模型专项复盘"],
    ["llm_model_assistant", "大模型辅助"],
    ["llm_model_assistant_history", "大模型辅助历史"],
    ["llm_full_solution", "大模型全流程题解"],
    ["llm_paper_latex", "大模型 LaTeX 生成记录"],
    ["computed_solver_spec", "大模型代码求解规范"],
    ["computed_solver_script", "代码求解脚本"],
    ["computed_solver_repair", "代码求解自动修复记录"],
    ["computed_solver_log", "代码运行日志"],
    ["computed_solution_status", "代码运行状态 JSON"],
    ["computed_completeness", "代码求解完整性检查"],
    ["computed_manifest", "代码计算结果清单"],
    ["computed_summary", "代码计算结果摘要"],
    ["computed_result_prose", "结果整合说明"],
    ["performance_health", "性能与修复健康报告"],
    ["repair_briefing", "自动修复中心"],
    ["delivery_readiness", "交付就绪报告"],
    ["delivery_package", "正式交付包"],
    ["delivery_package_manifest", "交付包清单"],
    ["paper_result_filled", "结果整合论文 LaTeX"],
    ["auto_workflow_report", "自动解题报告"],
    ["auto_workflow_report_json", "自动解题 JSON"],
    ["backend_skill_research", "GitHub 技能库与诚信门禁报告"],
    ["backend_skill_research_json", "GitHub 技能库与诚信门禁 JSON"],
    ["code_graph_report", "代码图谱报告"],
    ["code_graph_json", "代码图谱 JSON"],
    ["paper_autofilled", "回填论文 LaTeX"],
    ["paper_llm", "大模型论文 LaTeX"],
    ["paper_fill_summary", "回填摘要"],
    ["format_rules_summary", "格式规则摘要"],
    ["paper_pdf", "论文 PDF"],
    ["paper_docx", "论文 Word"],
    ["latex_log", "编译日志"],
    ["word_export_log", "Word 导出日志"],
    ["paper_review", "论文审查报告"],
    ["paper_review_json", "论文审查 JSON"],
    ["material_passport_json", "材料护照 JSON"],
    ["llm_problem_structure_json", "大模型赛题结构增强 JSON"],
    ["llm_problem_analysis_json", "大模型赛题分析 JSON"],
    ["llm_baseline_review_json", "大模型基线复盘 JSON"],
    ["llm_specialized_review_json", "大模型专项复盘 JSON"],
    ["llm_model_assistant_json", "大模型辅助 JSON"],
    ["llm_model_assistant_history_json", "大模型辅助历史 JSON"],
    ["llm_full_solution_json", "大模型全流程题解 JSON"],
    ["llm_paper_latex_json", "大模型 LaTeX 生成 JSON"],
    ["computed_solver_spec_json", "大模型代码求解规范 JSON"],
    ["computed_solver_script_json", "代码求解脚本 JSON"],
    ["computed_solver_repair_json", "代码求解自动修复 JSON"],
    ["computed_completeness_json", "代码求解完整性检查 JSON"],
    ["computed_result_prose_json", "结果整合说明 JSON"],
    ["performance_health_json", "性能与修复健康 JSON"],
    ["repair_briefing_json", "自动修复中心 JSON"],
    ["delivery_readiness_json", "交付就绪 JSON"],
    ["delivery_package_manifest_json", "交付包 JSON"],
  ]
    .filter(([key]) => artifacts[key])
    .map(([key, label]) => [key, label, artifacts[key], artifactStatus[key]]);
  items.push(["support_zip", "支撑材料包", "support.zip", artifactStatus.support_zip]);
  if (!items.length) {
    els.artifacts.innerHTML = '<p class="status">暂无生成文件。</p>';
    return;
  }
  const grouped = new Map();
  items.forEach(([key, label, path, status]) => {
    const group = artifactGroup(key, path);
    if (!grouped.has(group)) {
      grouped.set(group, []);
    }
    grouped.get(group).push([key, label, path, status]);
  });
  const summaryHtml = renderArtifactSummary(artifactSummary);
  const foldersHtml = Array.from(grouped.entries())
    .map(([group, groupItems], groupIndex) => {
      const links = groupItems
        .map(([key, label, path, status]) => renderArtifactItem(projectId, key, label, path, status))
        .join("");
      const folderId = `artifact-folder-${groupIndex}`;
      const kinds = artifactFolderKinds(groupItems);
      const missing = groupItems.filter(([, , , status]) => status && (status.exists === false || status.is_file === false)).length;
      const summary = `${groupItems.length} 个文件${missing ? ` · ${missing} 个未生成` : kinds ? ` · ${kinds}` : ""}`;
      return `
        <section class="artifact-folder">
          <button class="artifact-folder-button" type="button" data-artifact-folder="${escapeHtml(folderId)}" aria-expanded="false" aria-controls="${escapeHtml(folderId)}">
            <span class="artifact-folder-mark" aria-hidden="true"></span>
            <span class="artifact-folder-copy">
              <strong>${escapeHtml(group)}</strong>
              <small>${escapeHtml(summary)}</small>
            </span>
          </button>
          <div id="${escapeHtml(folderId)}" class="artifact-list" hidden>${links}</div>
        </section>
      `;
    })
    .join("");
  els.artifacts.innerHTML = `${summaryHtml}${foldersHtml}`;
}

function renderArtifactSummary(summary = {}) {
  const total = Number(summary.total || 0);
  if (!total) {
    return "";
  }
  const available = Number(summary.available || 0);
  const missing = Number(summary.missing || 0);
  const unsafe = Number(summary.unsafe || 0);
  const status = missing || unsafe ? "warning" : "success";
  const text = missing
    ? `可打开 ${available}/${total} 个文件，${missing} 个文件尚未生成或已移动。`
    : `可打开 ${available}/${total} 个文件。`;
  const unsafeText = unsafe ? ` · ${unsafe} 个路径异常` : "";
  return `<p class="artifact-summary" data-status="${status}">${escapeHtml(text + unsafeText)}</p>`;
}

function artifactFolderKinds(items = []) {
  const labels = {
    pdf: "PDF",
    docx: "Word",
    tex: "LaTeX",
    code: "代码",
    data: "数据",
    file: "文件",
  };
  const kinds = [];
  items.forEach(([key, , path]) => {
    const kind = artifactKind(key, path);
    if (!kinds.includes(kind)) {
      kinds.push(kind);
    }
  });
  return kinds.slice(0, 4).map((kind) => labels[kind] || kind).join(" / ");
}

function renderArtifactItem(projectId, key, label, path, status = {}) {
  const encodedProject = encodeURIComponent(projectId);
  const encodedPath = encodeRelativePath(path);
  const safeLabel = escapeHtml(label);
  const safePath = escapeHtml(path);
  const available = !status || (status.exists !== false && status.is_file !== false);
  const reason = status?.missing_reason || "文件尚未生成或已被移动";
  const safeReason = escapeHtml(reason);
  if (!available) {
    return `
      <div class="artifact-row is-missing">
        <span class="artifact-link artifact-link-missing" data-kind="${artifactKind(key, path)}" title="${safePath} · ${safeReason}" aria-disabled="true">
          <span class="artifact-copy">
            <span class="artifact-name">${safeLabel}</span>
            <small class="artifact-missing-reason">${safeReason}</small>
          </span>
        </span>
        <button class="artifact-open" type="button" data-missing="true" disabled title="${safeReason}" aria-label="${safeLabel}尚未生成">未生成</button>
      </div>
    `;
  }
  return `
    <div class="artifact-row">
      <a class="artifact-link" data-kind="${artifactKind(key, path)}" href="/api/projects/${encodedProject}/download/${encodedPath}" title="${safePath}" aria-label="下载或查看${safeLabel}">
        <span class="artifact-copy"><span class="artifact-name">${safeLabel}</span></span>
      </a>
      <button class="artifact-open" type="button" data-project-id="${escapeHtml(projectId)}" data-path="${safePath}" title="在资源管理器中打开所在位置" aria-label="打开${safeLabel}所在文件夹">打开位置</button>
    </div>
  `;
}

els.artifacts.addEventListener("click", async (event) => {
  const folderButton = event.target.closest("[data-artifact-folder]");
  if (folderButton) {
    const folderId = folderButton.dataset.artifactFolder;
    const folder = folderId ? document.getElementById(folderId) : null;
    if (!folder) {
      return;
    }
    const expanded = folderButton.getAttribute("aria-expanded") === "true";
    folderButton.setAttribute("aria-expanded", expanded ? "false" : "true");
    folder.hidden = expanded;
    return;
  }
  const button = event.target.closest(".artifact-open");
  if (!button) {
    return;
  }
  const projectId = button.dataset.projectId;
  const path = button.dataset.path;
  if (!projectId || !path) {
    return;
  }
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "打开中";
  try {
    await api(`/api/projects/${encodeURIComponent(projectId)}/open-location/${encodeRelativePath(path)}`, { method: "POST" });
    button.textContent = "已打开";
    showToast("已打开文件所在位置", "success");
    window.setTimeout(() => {
      button.textContent = originalText;
      button.disabled = false;
    }, 1400);
  } catch (error) {
    button.textContent = "打开失败";
    els.projectStatus.textContent = `打开文件位置失败：${error.message}`;
    showToast(`打开位置失败：${error.message}`, "error");
    window.setTimeout(() => {
      button.textContent = originalText;
      button.disabled = false;
    }, 1800);
  }
});

function artifactGroup(key, path) {
  const value = `${key || ""} ${path || ""}`.toLowerCase();
  if (value.includes("code_graph") || value.includes("call_graph")) {
    return "代码与求解";
  }
  if (value.includes("paper") || value.includes("latex") || value.endsWith(".pdf") || value.endsWith(".tex") || value.endsWith(".docx")) {
    return "论文文件";
  }
  if (value.includes("report") || value.includes("analysis") || value.includes("review") || value.includes("skill") || value.includes("health")) {
    return "分析报告";
  }
  if (value.includes("repair_briefing")) {
    return "分析报告";
  }
  if (value.includes("delivery_readiness")) {
    return "分析报告";
  }
  if (value.includes("passport") || value.includes("attachment_profile")) {
    return "分析报告";
  }
  if (value.includes("script") || value.includes("solver") || value.includes("parallel_task_plan") || value.endsWith(".py")) {
    return "代码与求解";
  }
  if (value.includes("manifest") || value.includes("summary") || value.endsWith(".json") || value.endsWith(".csv") || value.endsWith(".xlsx")) {
    return "数据结果";
  }
  if (value.includes("support") || value.endsWith(".zip") || value.includes("log")) {
    return "支撑材料";
  }
  return "其他文件";
}

function artifactKind(key, path) {
  const value = `${key || ""} ${path || ""}`.toLowerCase();
  if (value.endsWith(".pdf") || value.includes("paper_pdf")) {
    return "pdf";
  }
  if (value.endsWith(".docx") || value.includes("paper_docx")) {
    return "docx";
  }
  if (value.endsWith(".tex") || value.includes("latex") || value.includes("paper_")) {
    return "tex";
  }
  if (value.endsWith(".py") || value.includes("script") || value.includes("solver") || value.includes("code_graph")) {
    return "code";
  }
  if (value.endsWith(".json") || value.endsWith(".csv") || value.endsWith(".xlsx") || value.includes("manifest")) {
    return "data";
  }
  return "file";
}

els.file.addEventListener("change", () => {
  const file = els.file.files[0];
  els.fileLabel.textContent = file ? file.name : "选择 zip、pdf、docx、xlsx 或 csv";
  if (file && els.folder) {
    els.folder.value = "";
    els.folderLabel.textContent = "选择包含全部赛题材料的文件夹";
  }
});

els.folder.addEventListener("change", () => {
  const files = Array.from(els.folder.files || []);
  if (!files.length) {
    els.folderLabel.textContent = "选择包含全部赛题材料的文件夹";
    return;
  }
  const folderName = folderNameFromFiles(files);
  els.folderLabel.textContent = `${folderName} · ${files.length} 个文件`;
  if (els.file) {
    els.file.value = "";
    els.fileLabel.textContent = "选择 zip、pdf、docx、xlsx 或 csv";
  }
});

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const folderFiles = Array.from(els.folder?.files || []);
  const file = els.file.files[0];
  if (!file && !folderFiles.length) {
    els.status.textContent = "请先选择文件、压缩包或赛题文件夹。";
    return;
  }
  const button = els.form.querySelector("button");
  const formData = new FormData();
  const progressId = createProgressId();
  formData.append("progress_id", progressId);
  let endpoint = "/api/projects";
  if (folderFiles.length) {
    endpoint = "/api/projects/folder";
    const folderName = folderNameFromFiles(folderFiles);
    formData.append("folder_name", folderName);
    folderFiles.forEach((item) => {
      formData.append("files", item, item.webkitRelativePath || item.name);
    });
  } else {
    formData.append("file", file);
  }
  button.disabled = true;
  if (state.uploadProgressStop) {
    state.uploadProgressStop();
  }
  renderProgressPanel(
    els.uploadProgress,
    {
      status: "running",
      current_step: {
        id: "upload",
        title: folderFiles.length ? "上传赛题文件夹" : "上传赛题材料",
        status: "running",
        detail: folderFiles.length ? `正在上传 ${folderFiles.length} 个文件。` : `正在上传 ${file.name}。`,
      },
      steps: [],
      completed_steps: 0,
      total_steps: 7,
      percent: 3,
    },
    7,
  );
  state.uploadProgressStop = startUploadProgressPolling(progressId);
  els.status.textContent = folderFiles.length
    ? `正在上传文件夹中的 ${folderFiles.length} 个文件并解析，请稍候。`
    : "正在上传并解析，请稍候。";
  try {
    const detail = await api(endpoint, { method: "POST", body: formData });
    await refreshUploadProgress(progressId);
    els.status.textContent = "分析完成。";
    showToast("赛题分析完成", "success");
    renderProject(detail);
    await loadProjects();
    if (els.autoRunAfterUpload?.checked) {
      const rec = detail.analysis?.recommended_problem || {};
      if (rec.id) {
        await selectProblem(rec.id);
        await runAutoWorkflow(
          detail.metadata.id,
          {
            initialMessage:
              "上传分析完成，已按系统推荐题目确认选择，正在调用大模型生成并运行代码，随后回填结果、撰写论文和审查。",
          },
        );
      } else {
        els.status.textContent = "分析完成，但未识别到可自动确认的推荐题目，请在选题模块手动选择。";
      }
    }
  } catch (error) {
    await refreshUploadProgress(progressId);
    els.status.textContent = `分析失败：${error.message}`;
    showToast(`赛题分析失败：${error.message}`, "error");
  } finally {
    if (state.uploadProgressStop) {
      state.uploadProgressStop();
      state.uploadProgressStop = null;
      await refreshUploadProgress(progressId);
    }
    button.disabled = false;
  }
});

function createProgressId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `upload-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function startUploadProgressPolling(progressId) {
  let stopped = false;
  refreshUploadProgress(progressId);
  const timer = window.setInterval(async () => {
    if (stopped) {
      return;
    }
    const done = await refreshUploadProgress(progressId);
    if (done) {
      stopped = true;
      window.clearInterval(timer);
    }
  }, 500);
  return () => {
    stopped = true;
    window.clearInterval(timer);
  };
}

async function refreshUploadProgress(progressId) {
  if (!progressId || !els.uploadProgress) {
    return false;
  }
  try {
    const payload = await api(`/api/upload-analysis-progress/${encodeURIComponent(progressId)}`);
    const progress = payload.progress || {};
    if (!Object.keys(progress).length) {
      return false;
    }
    renderProgressPanel(els.uploadProgress, progress, 7);
    return ["success", "failed", "completed_with_warnings"].includes(progress.status);
  } catch {
    return false;
  }
}

function folderNameFromFiles(files) {
  const first = files[0];
  const relative = first?.webkitRelativePath || first?.name || "赛题文件夹";
  return relative.split(/[\\/]/)[0] || "赛题文件夹";
}

els.refresh.addEventListener("click", async () => {
  els.refresh.disabled = true;
  try {
    await loadProjects();
    await loadAutoJobs();
    await loadGrowthMetrics();
    await loadTrustCenter();
    showToast("项目列表已刷新", "success");
  } catch (error) {
    showToast(`刷新项目失败：${error.message}`, "error");
  } finally {
    els.refresh.disabled = false;
  }
});

els.refreshAutoJobs?.addEventListener("click", async () => {
  els.refreshAutoJobs.disabled = true;
  try {
    await loadAutoJobs();
    await loadGrowthMetrics();
    await loadTrustCenter();
    showToast("后台任务中心已刷新", "success");
  } catch (error) {
    showToast(`后台任务刷新失败：${error.message}`, "error");
  } finally {
    els.refreshAutoJobs.disabled = false;
  }
});

els.refreshGrowthMetrics?.addEventListener("click", async () => {
  els.refreshGrowthMetrics.disabled = true;
  if (els.growthCenterStatus) {
    els.growthCenterStatus.textContent = "正在刷新项目漏斗、交付产出和任务吞吐指标。";
  }
  try {
    await loadGrowthMetrics();
    await loadTrustCenter();
    if (els.growthCenterStatus) {
      els.growthCenterStatus.textContent = "解题进度中心已刷新。";
    }
    showToast("解题进度中心已刷新", "success");
  } catch (error) {
    if (els.growthCenterStatus) {
      els.growthCenterStatus.textContent = `解题进度刷新失败：${error.message}`;
    }
    showToast(`解题进度刷新失败：${error.message}`, "error");
  } finally {
    els.refreshGrowthMetrics.disabled = false;
  }
});

els.refreshTrustCenter?.addEventListener("click", async () => {
  els.refreshTrustCenter.disabled = true;
  if (els.trustCenterStatus) {
    els.trustCenterStatus.textContent = "正在刷新质量与交付信任证据。";
  }
  try {
    await loadTrustCenter();
    if (els.trustCenterStatus) {
      els.trustCenterStatus.textContent = "信任中心已刷新。";
    }
    showToast("信任中心已刷新", "success");
  } catch (error) {
    if (els.trustCenterStatus) {
      els.trustCenterStatus.textContent = `信任中心刷新失败：${error.message}`;
    }
    showToast(`信任中心刷新失败：${error.message}`, "error");
  } finally {
    els.refreshTrustCenter.disabled = false;
  }
});

els.trustCenter?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-trust-action]");
  if (!button) {
    return;
  }
  const command = button.dataset.trustAction;
  if (!["export_audit", "repair_campaign"].includes(command)) {
    return;
  }
  button.disabled = true;
  if (els.trustCenterStatus) {
    els.trustCenterStatus.textContent = command === "repair_campaign" ? "正在运行修复行动。" : "正在导出信任审计包。";
  }
  try {
    if (command === "repair_campaign") {
      const payload = await api("/api/product/trust/repair-campaign/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ queue_resumes: true, refresh_diagnostics: true, limit: 20 }),
      });
      state.trustMetrics = payload.trust || state.trustMetrics || {};
      state.repairCampaigns = payload.repair_campaigns || state.repairCampaigns || null;
      state.growthMetrics = payload.growth || state.growthMetrics;
      state.autoJobs = payload.auto_jobs || state.autoJobs;
      state.deliveryBatchJobs = payload.delivery_batch_jobs || state.deliveryBatchJobs;
      renderTrustCenter(state.trustMetrics, state.trustExports);
      renderAutoJobCenter(state.autoJobs, state.deliveryBatchJobs);
      if (state.growthMetrics) {
        renderGrowthCenter(state.growthMetrics);
      }
      const campaign = payload.repair_campaign || {};
      if (els.trustCenterStatus) {
        els.trustCenterStatus.textContent = campaign.summary || "修复行动已完成。";
      }
      showToast("修复行动已完成", "success");
      return;
    }
    const payload = await api("/api/product/trust/export", { method: "POST" });
    state.trustMetrics = payload.trust || payload.trust_report?.trust || state.trustMetrics || {};
    state.trustExports = payload.trust_exports || state.trustExports || null;
    renderTrustCenter(state.trustMetrics, state.trustExports);
    const report = payload.trust_report || {};
    if (els.trustCenterStatus) {
      const sizeText = report.size ? ` · ${report.size}` : "";
      els.trustCenterStatus.textContent = `信任审计包已导出：${report.filename || report.id || "压缩包"}${sizeText}`;
    }
    if (report.download_url) {
      window.open(report.download_url, "_blank", "noopener");
    }
    showToast("信任审计包已就绪", "success");
  } catch (error) {
    if (els.trustCenterStatus) {
      els.trustCenterStatus.textContent = `信任审计包导出失败：${error.message}`;
    }
    showToast(`信任审计包导出失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
});

els.growthCenter?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-growth-action]");
  if (!button) {
    return;
  }
  const command = button.dataset.growthAction;
  button.disabled = true;
  try {
    if (command === "batch_packages") {
      if (els.growthCenterStatus) {
        els.growthCenterStatus.textContent = "正在并发生成所有可交付项目的正式交付包。";
      }
      const payload = await api("/api/delivery/packages/batch/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: false, max_workers: Number(state.capacitySettings?.delivery_package_workers || 4) }),
      });
      const job = payload.delivery_batch_job || {};
      if (payload.delivery_batch_jobs) {
        state.deliveryBatchJobs = payload.delivery_batch_jobs;
      }
      if (payload.growth) {
        state.growthMetrics = payload.growth;
        renderGrowthCenter(state.growthMetrics);
      } else {
        await loadGrowthMetrics();
      }
      await loadAutoJobs();
      await loadProjects();
      await loadTrustCenter();
      if (els.growthCenterStatus) {
        els.growthCenterStatus.textContent = job.summary || "批量交付包任务已入队。";
      }
      showToast(`批量交付包任务已入队：${job.requested_count || 0} 个项目`, "success");
    }
  } catch (error) {
    if (els.growthCenterStatus) {
      els.growthCenterStatus.textContent = `批量交付包失败：${error.message}`;
    }
    showToast(`批量交付包失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
});

els.experienceGuide?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-guide-action]");
  if (!button) {
    return;
  }
  button.disabled = true;
  try {
    await runGuideAction(button.dataset.guideAction);
  } finally {
    button.disabled = false;
  }
});

els.projectReadiness?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-readiness-action]");
  if (!button) {
    return;
  }
  button.disabled = true;
  try {
    await runGuideAction(button.dataset.readinessAction);
  } finally {
    button.disabled = false;
  }
});

async function runGuideAction(action) {
  const projectId = state.currentProject?.metadata?.id || "";
  if (action === "focus_upload") {
    scrollIntoViewIfPossible(els.form);
    els.file?.focus();
    return;
  }
  if (action === "focus_projects") {
    scrollIntoViewIfPossible(els.projectList);
    els.projectSearch?.focus();
    return;
  }
  if (action === "focus_llm") {
    scrollIntoViewIfPossible(els.llmSettingsForm);
    els.apiKeyInput?.focus();
    return;
  }
  if (action === "test_llm") {
    els.testLlmSettings?.click();
    return;
  }
  if (action === "open_problems") {
    activateModuleTab("problems", { focus: true });
    return;
  }
  if (action === "open_outputs") {
    activateModuleTab("outputs", { focus: true });
    scrollIntoViewIfPossible(els.autoWorkflowProgress || els.artifacts);
    return;
  }
  if (action === "start_auto") {
    if (!projectId) {
      showToast("请先打开一个项目。", "warning");
      return;
    }
    activateModuleTab("outputs");
    els.runAutoWorkflow?.click();
    return;
  }
  if (action === "resume_auto") {
    if (!projectId) {
      showToast("请先打开一个项目。", "warning");
      return;
    }
    activateModuleTab("outputs");
    els.resumeAutoWorkflow?.click();
    return;
  }
  if (action === "cancel_auto") {
    els.cancelAutoWorkflow?.click();
    return;
  }
  if (action === "compile") {
    activateModuleTab("outputs");
    els.compile?.click();
    return;
  }
  if (action === "review") {
    activateModuleTab("outputs");
    els.reviewPaper?.click();
    return;
  }
  if (action === "refresh_delivery") {
    activateModuleTab("outputs");
    els.refreshDeliveryReadiness?.click();
    return;
  }
  if (action === "refresh_repair") {
    activateModuleTab("outputs");
    els.refreshRepairCenter?.click();
    return;
  }
  if (action === "build_delivery_package") {
    activateModuleTab("outputs");
    const deliveryButton = els.deliveryCenter?.querySelector("[data-delivery-action='package']");
    if (deliveryButton) {
      deliveryButton.click();
    } else {
      els.refreshDeliveryReadiness?.click();
    }
    return;
  }
  if (action === "open_project_root") {
    await openProjectRoot(projectId);
    return;
  }
  if (action === "select_analyzed") {
    els.selectAnalyzedProjects?.click();
    scrollIntoViewIfPossible(els.batchStartProjects);
    return;
  }
  if (action === "batch_packages") {
    const growthButton = els.growthCenter?.querySelector("[data-growth-action='batch_packages']");
    if (growthButton) {
      growthButton.click();
    } else {
      await loadGrowthMetrics();
      els.growthCenter?.querySelector("[data-growth-action='batch_packages']")?.click();
    }
    return;
  }
  if (action === "autotune_capacity") {
    const capacityButton = els.autoJobCenter?.querySelector("[data-capacity-action='autotune']");
    if (capacityButton) {
      capacityButton.click();
    } else {
      await loadAutoJobs();
      els.autoJobCenter?.querySelector("[data-capacity-action='autotune']")?.click();
    }
    return;
  }
  if (action === "repair_campaign") {
    const repairButton = els.trustCenter?.querySelector("[data-trust-action='repair_campaign']");
    if (repairButton) {
      repairButton.click();
    } else {
      await loadTrustCenter();
      els.trustCenter?.querySelector("[data-trust-action='repair_campaign']")?.click();
    }
    return;
  }
  if (action === "refresh_all") {
    await Promise.all([loadProjects(), loadExperienceCenter(), loadAutoJobs(), loadGrowthMetrics(), loadTrustCenter()]);
    showToast("产品状态已刷新", "success");
  }
}

function scrollIntoViewIfPossible(node) {
  if (!node || typeof node.scrollIntoView !== "function") {
    return;
  }
  node.scrollIntoView({ behavior: "smooth", block: "center" });
}

els.autoJobCenter?.addEventListener("click", async (event) => {
  const capacityButton = event.target.closest("[data-capacity-action='autotune']");
  if (capacityButton) {
    capacityButton.disabled = true;
    try {
      const response = await api("/api/product/capacity/autotune", { method: "POST" });
      state.capacitySettings = response.capacity_settings || state.capacitySettings;
      state.capacityAutotune = response.capacity_autotune_history || { latest: response.capacity_autotune, items: [response.capacity_autotune].filter(Boolean) };
      state.autoJobs = response.auto_jobs || state.autoJobs;
      state.deliveryBatchJobs = response.delivery_batch_jobs || state.deliveryBatchJobs;
      renderAutoJobCenter(state.autoJobs, state.deliveryBatchJobs);
      await loadGrowthMetrics();
      await loadTrustCenter();
      const plan = response.capacity_autotune || {};
      showToast(plan.status === "already_optimal" ? "容量已经最优" : "容量推荐已应用", "success");
    } catch (error) {
      showToast(`容量推荐失败：${error.message}`, "error");
    } finally {
      capacityButton.disabled = false;
    }
    return;
  }
  const button = event.target.closest(".job-open");
  if (!button) {
    return;
  }
  const projectId = button.dataset.projectId;
  if (!projectId) {
    return;
  }
  button.disabled = true;
  try {
    await openProject(projectId);
  } finally {
    button.disabled = false;
  }
});

els.autoJobCenter?.addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-capacity-form]");
  if (!form) {
    return;
  }
  event.preventDefault();
  const button = form.querySelector("button[type='submit']");
  if (button) {
    button.disabled = true;
  }
  try {
    const formData = new FormData(form);
    const payload = {
      auto_workflow_workers: Number(formData.get("auto_workflow_workers") || 0),
      delivery_batch_job_workers: Number(formData.get("delivery_batch_job_workers") || 0),
      delivery_package_workers: Number(formData.get("delivery_package_workers") || 0),
    };
    const response = await api("/api/product/capacity", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.capacitySettings = response.capacity_settings || state.capacitySettings;
    state.autoJobs = response.auto_jobs || state.autoJobs;
    state.deliveryBatchJobs = response.delivery_batch_jobs || state.deliveryBatchJobs;
    renderAutoJobCenter(state.autoJobs, state.deliveryBatchJobs);
    await loadGrowthMetrics();
    await loadTrustCenter();
    showToast("容量设置已应用", "success");
  } catch (error) {
    showToast(`容量设置失败：${error.message}`, "error");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
});

if (els.projectSearch) {
  els.projectSearch.addEventListener("input", () => {
    state.projectQuery = els.projectSearch.value;
    renderProjectList();
  });
}

els.projectFilters?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-project-filter]");
  if (!button) {
    return;
  }
  state.projectFilter = validProjectFilter(button.dataset.projectFilter || "all");
  writePreference("mmw-project-filter", state.projectFilter);
  renderProjectList();
});

els.projectBatchDetails?.addEventListener("toggle", () => {
  renderProjectList();
});

els.projectList?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-project-action]");
  if (!button) {
    return;
  }
  const projectId = button.dataset.projectId;
  const action = button.dataset.projectAction;
  if (!projectId || !action) {
    return;
  }
  button.disabled = true;
  try {
    if (action === "open_project_root") {
      await openProjectRoot(projectId);
      return;
    }
    await openProject(projectId);
    await runGuideAction(action);
  } finally {
    button.disabled = false;
  }
});

els.projectList?.addEventListener("change", (event) => {
  const input = event.target.closest(".project-select-input");
  if (!input) {
    return;
  }
  const projectId = input.dataset.projectId;
  if (!projectId) {
    return;
  }
  if (input.checked) {
    state.selectedProjectIds.add(projectId);
  } else {
    state.selectedProjectIds.delete(projectId);
  }
  renderProjectList();
});

els.selectAnalyzedProjects?.addEventListener("click", () => {
  currentFilteredProjects().forEach((project) => {
    if (project.analysis_available && project.id) {
      state.selectedProjectIds.add(project.id);
    }
  });
  renderProjectList();
  els.batchProjectStatus.textContent = `已选择 ${state.selectedProjectIds.size} 个已分析项目。`;
});

els.clearProjectSelection?.addEventListener("click", () => {
  state.selectedProjectIds.clear();
  renderProjectList();
  els.batchProjectStatus.textContent = "已清空批量选择。";
});

els.batchStartProjects?.addEventListener("click", async () => {
  await startSelectedProjectsBatch();
});

if (els.openProjectRoot) {
  els.openProjectRoot.addEventListener("click", async () => {
    await openProjectRoot();
  });
}

els.workflowStrategyInput?.addEventListener("change", () => {
  const selected = els.workflowStrategyInput.value || "balanced";
  const options = state.llmSettings?.workflow_strategy_options || [];
  const option = options.find((item) => item.id === selected);
  if (els.workflowStrategyHint) {
    els.workflowStrategyHint.textContent = option
      ? `当前策略：${option.label}。${option.summary}`
      : "当前策略：均衡。速度和成功率兼顾。";
  }
});

function llmSettingsPayloadFromForm() {
  return {
    api_key: els.apiKeyInput.value,
    base_url: els.baseUrlInput.value,
    model: els.modelInput.value,
    workflow_strategy: els.workflowStrategyInput?.value || "balanced",
  };
}

async function saveLlmSettingsFromForm() {
  const settings = await api("/api/settings/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(llmSettingsPayloadFromForm()),
  });
  renderLlmSettings(settings);
  return settings;
}

els.llmSettingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = els.llmSettingsForm.querySelector("button[type='submit']");
  button.disabled = true;
  els.llmSettingsStatus.textContent = "正在保存大模型设置。";
  try {
    await saveLlmSettingsFromForm();
    showToast("大模型设置已保存", "success");
  } catch (error) {
    els.llmSettingsStatus.textContent = `保存失败：${error.message}`;
    showToast(`大模型设置保存失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
});

els.testLlmSettings?.addEventListener("click", async () => {
  els.testLlmSettings.disabled = true;
  els.llmSettingsStatus.textContent = "正在保存当前大模型设置并测试连接。";
  try {
    await saveLlmSettingsFromForm();
    els.llmSettingsStatus.textContent = "正在测试大模型连接。";
    const result = await api("/api/settings/llm/test", { method: "POST" });
    if (result.ok) {
      els.llmSettingsStatus.textContent = "大模型连接测试成功，可以运行大模型+代码一键流程。";
      showToast("大模型连接测试成功", "success");
      return;
    }
    const diagnosis = result.diagnosis || {};
    const label = diagnosis.label ? `${diagnosis.label}：` : "";
    const hint = diagnosis.suggested_action || result.message || "请检查接口地址、模型名和 API Key。";
    els.llmSettingsStatus.textContent = `大模型连接测试失败：${label}${hint}`;
    showToast("大模型连接测试失败，请查看设置提示", "error");
  } catch (error) {
    els.llmSettingsStatus.textContent = `大模型连接测试失败：${error.message}`;
    showToast(`大模型连接测试失败：${error.message}`, "error");
  } finally {
    els.testLlmSettings.disabled = false;
  }
});

els.clearLlmSettings.addEventListener("click", async () => {
  els.clearLlmSettings.disabled = true;
  els.llmSettingsStatus.textContent = "正在清除大模型设置。";
  try {
    const settings = await api("/api/settings/llm", { method: "DELETE" });
    renderLlmSettings(settings);
    showToast("大模型设置已清除", "success");
  } catch (error) {
    els.llmSettingsStatus.textContent = `清除失败：${error.message}`;
    showToast(`清除大模型设置失败：${error.message}`, "error");
  } finally {
    els.clearLlmSettings.disabled = false;
  }
});

els.templateFileInput.addEventListener("change", () => {
  const file = els.templateFileInput.files[0];
  els.templateFileLabel.textContent = file ? file.name : "选择 LaTeX 模板或 Word/PDF 格式说明";
});

els.templateSelect.addEventListener("change", () => {
  renderTemplateHint(els.templateSelect.value || "builtin-default");
});

els.templateUploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = els.templateFileInput.files[0];
  if (!file) {
    els.templateStatus.textContent = "请先选择 .tex 模板，或 .docx/.pdf/.txt/.md 格式说明文档。";
    return;
  }
  const suffix = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  const supported = [".tex", ".docx", ".pdf", ".txt", ".md"];
  if (!supported.includes(suffix)) {
    els.templateStatus.textContent = "当前只支持 .tex 模板，或 .docx/.pdf/.txt/.md 格式说明文档。";
    return;
  }
  const button = els.templateUploadForm.querySelector("button[type='submit']");
  const formData = new FormData();
  formData.append("name", els.templateNameInput.value);
  formData.append("file", file);
  button.disabled = true;
  els.templateStatus.textContent = "正在上传并解析模板或格式说明。";
  try {
    const payload = await api("/api/templates", { method: "POST", body: formData });
    state.templates = payload.templates || [];
    renderTemplateSelect(payload.template?.id || "builtin-default");
    els.templateStatus.textContent =
      payload.template?.mode === "rules"
        ? "格式说明已上传，生成论文时会作为官方格式规则保留。"
        : "LaTeX 模板已上传，可在格式模板中选择。";
    els.templateFileInput.value = "";
    els.templateFileLabel.textContent = "选择 LaTeX 模板或 Word/PDF 格式说明";
  } catch (error) {
    els.templateStatus.textContent = `模板上传失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
});

els.deleteTemplate.addEventListener("click", async () => {
  const templateId = els.templateSelect.value;
  if (!templateId || templateId === "builtin-default") {
    els.templateStatus.textContent = "内置模板不能删除。";
    return;
  }
  els.deleteTemplate.disabled = true;
  els.templateStatus.textContent = "正在删除模板。";
  try {
    const payload = await api(`/api/templates/${encodeURIComponent(templateId)}`, { method: "DELETE" });
    state.templates = payload.templates || [];
    renderTemplateSelect("builtin-default");
    els.templateStatus.textContent = "模板已删除。";
  } catch (error) {
    els.templateStatus.textContent = `删除失败：${error.message}`;
  } finally {
    els.deleteTemplate.disabled = false;
  }
});

els.paperOptionsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.paperOptionsStatus.textContent = "请先打开一个项目。";
    return;
  }
  const button = els.paperOptionsForm.querySelector("button[type='submit']");
  const rawPages = els.targetBodyPages.value.trim();
  const targetPages = rawPages ? Number(rawPages) : null;
  const payload = {
    template_id: els.templateSelect.value || "builtin-default",
    target_body_pages: targetPages,
  };
  button.disabled = true;
  els.paperOptionsStatus.textContent = "正在保存论文设置。";
  try {
    const result = await api(`/api/projects/${encodeURIComponent(projectId)}/paper/options`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderProject(result.project);
    els.paperOptionsStatus.textContent = targetPages
      ? `已保存：正文不少于 ${targetPages} 页。`
      : "已保存：暂不约束正文页数。";
    await loadProjects();
  } catch (error) {
    els.paperOptionsStatus.textContent = `保存失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
});

els.modelAssistantForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.modelAssistantStatus.textContent = "请先打开一个项目。";
    return;
  }
  const modelName = els.assistModelInput.value.trim();
  if (!modelName) {
    els.modelAssistantStatus.textContent = "请填写模型或算法名称。";
    return;
  }
  const button = els.modelAssistantForm.querySelector("button[type='submit']");
  button.disabled = true;
  els.modelAssistantStatus.textContent = "正在生成模型辅助方案，下面会显示检索、提示词构建和大模型生成过程。";
  const stopProgressPolling = startModelAssistantProgressPolling(projectId);
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/llm/model-assistant`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        problem_ref: els.assistProblemSelect.value,
        model_name: modelName,
        user_goal: els.assistGoalInput.value,
      }),
    });
    renderProject(payload.project);
    const artifacts = payload.artifacts || {};
    const report = artifacts.llm_model_assistant;
    els.modelAssistantStatus.innerHTML = report
      ? `模型辅助方案已生成：<a href="/api/projects/${encodeURIComponent(projectId)}/download/${encodeRelativePath(report)}">查看报告</a>。`
      : "模型辅助方案已生成，可在生成文件中查看。";
    await loadProjects();
  } catch (error) {
    els.modelAssistantStatus.textContent = `模型辅助失败：${error.message}`;
  } finally {
    stopProgressPolling();
    await refreshModelAssistantProgress(projectId);
    button.disabled = false;
  }
});

function startModelAssistantProgressPolling(projectId) {
  let stopped = false;
  refreshModelAssistantProgress(projectId);
  const timer = window.setInterval(() => {
    if (!stopped) {
      refreshModelAssistantProgress(projectId);
    }
  }, 700);
  return () => {
    stopped = true;
    window.clearInterval(timer);
  };
}

async function refreshModelAssistantProgress(projectId) {
  if (!projectId || !els.modelAssistantProgress) {
    return;
  }
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/llm/model-assistant/progress`);
    renderModelAssistantProgress(payload.progress);
  } catch {
    // Progress polling is best-effort; the main action will report hard failures.
  }
}

function renderModelAssistantProgress(progress = {}) {
  renderProgressPanel(els.modelAssistantProgress, progress, 5);
}

els.runModeling.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.modelingStatus.textContent = "请先打开一个项目。";
    return;
  }
  els.runModeling.disabled = true;
  els.modelingStatus.textContent = "正在生成并运行基线建模脚本。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/model/run`, { method: "POST" });
    renderProject(payload.project);
    const out = payload.modeling?.outputs || {};
    const tables = out.tables?.length ?? 0;
    const figures = out.figures?.length ?? 0;
    els.modelingStatus.textContent = payload.modeling.success
      ? `建模完成：生成 ${tables} 个结果表、${figures} 张图。`
      : "建模失败，请查看日志。";
    await loadProjects();
  } catch (error) {
    els.modelingStatus.textContent = `建模失败：${error.message}`;
  } finally {
    els.runModeling.disabled = false;
  }
});

els.runSpecialized.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.specializedStatus.textContent = "请先打开一个项目。";
    return;
  }
  els.runSpecialized.disabled = true;
  els.specializedStatus.textContent = "正在生成并运行专项建模脚本。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/specialized/run`, { method: "POST" });
    renderProject(payload.project);
    const out = payload.specialized?.outputs || {};
    const models = out.specialized_models?.length ?? 0;
    const tables = out.tables?.length ?? 0;
    const figures = out.figures?.length ?? 0;
    els.specializedStatus.textContent = payload.specialized.success
      ? `专项建模完成：${models} 个模型、${tables} 个结果表、${figures} 张图。`
      : "专项建模失败，请查看日志。";
    await loadProjects();
  } catch (error) {
    els.specializedStatus.textContent = `专项建模失败：${error.message}`;
  } finally {
    els.runSpecialized.disabled = false;
  }
});

async function runAutoWorkflow(
  projectId,
  {
    resume = false,
    initialMessage = "正在调用大模型完成选题、生成并运行代码、回填结果、论文生成和审查。",
  } = {},
) {
  if (!projectId) {
    els.autoWorkflowStatus.textContent = "请先打开一个项目。";
    return;
  }
  const settings = state.llmSettings || (await api("/api/settings/llm"));
  state.llmSettings = settings;
  if (!settings.configured) {
    els.autoWorkflowStatus.textContent = "请先在左侧大模型设置中填写接口密钥；大模型+代码自动解题不提供本地降级模式。";
    return;
  }
  const selectedId = selectedProblemId(state.currentProject?.metadata || {});
  if (!selectedId) {
    els.autoWorkflowStatus.textContent = "请先在“选题”模块点击“选择此题”，确认后再运行一键自动流程。";
    return;
  }
  els.runAutoWorkflow.disabled = true;
  if (els.resumeAutoWorkflow) els.resumeAutoWorkflow.disabled = true;
  if (els.cancelAutoWorkflow) els.cancelAutoWorkflow.disabled = false;
  els.autoWorkflowStatus.textContent = resume ? "正在提交后台继续生成任务。" : "正在提交后台自动流程任务。";
  try {
    const endpoint = resume ? "resume/start" : "start";
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/auto/${endpoint}`, { method: "POST" });
    renderProject(payload.project);
    const job = payload.auto_job || {};
    await loadAutoJobs();
    await loadTrustCenter();
    const workerText = job.max_workers ? `，任务池并发 ${job.max_workers}` : "";
    els.autoWorkflowStatus.textContent = job.existing
      ? `已有自动流程后台任务正在执行${workerText}，正在接管进度。`
      : `${initialMessage} 已进入后台任务池${workerText}。`;
    showToast(job.existing ? "已接管正在运行的自动流程" : "自动流程已提交后台任务", "success");
    await refreshAutoProgress(projectId);
    const finalPayload = await waitForAutoWorkflowCompletion(projectId);
    const finalStatus = finalPayload.status || finalPayload.progress?.status || "";
    const steps = finalPayload.progress?.steps || [];
    const warningCount = steps.filter((step) => step.status === "warning").length;
    const failedCount = steps.filter((step) => step.status === "failed").length;
    const detail = await api(`/api/projects/${encodeURIComponent(projectId)}`);
    renderProject(detail);
    if (finalStatus === "success") {
      els.autoWorkflowStatus.textContent = "大模型+代码自动流程完成：已生成题解方案、运行代码得到结果、回填论文、审查报告和支撑材料。";
      showToast("自动流程已完成", "success");
    } else if (finalStatus === "cancelled") {
      els.autoWorkflowStatus.textContent = "自动流程已中断：当前阶段已安全结束，可点击“继续生成”从断点恢复。";
      showToast("自动流程已中断，可继续生成", "warning");
    } else if (finalStatus === "failed" || finalStatus === "requires_api_key") {
      const hint = finalPayload.progress?.resume_hint || finalPayload.progress?.last_failure_diagnosis?.suggested_action || "请查看进度诊断后继续生成。";
      els.autoWorkflowStatus.textContent = `自动流程失败：${hint}`;
      showToast("自动流程失败，可查看诊断后继续生成", "error");
    } else {
      els.autoWorkflowStatus.textContent = `自动流程完成但需复核：${warningCount} 个警告，${failedCount} 个失败项。请查看自动解题报告。`;
      showToast("自动流程完成但需要复核", "warning");
    }
    await loadProjects();
  } catch (error) {
    els.autoWorkflowStatus.textContent = `自动流程失败：${error.message}`;
    showToast(`自动流程失败：${error.message}`, "error");
    try {
      const detail = await api(`/api/projects/${encodeURIComponent(projectId)}`);
      renderProject(detail);
      await loadProjects();
    } catch {
      // Keep the visible error if the follow-up refresh also fails.
    }
  } finally {
    await refreshAutoProgress(projectId);
    await loadAutoJobs();
    await loadGrowthMetrics();
    await loadTrustCenter();
    els.runAutoWorkflow.disabled = false;
    if (els.cancelAutoWorkflow) els.cancelAutoWorkflow.disabled = true;
  }
}

async function waitForAutoWorkflowCompletion(projectId) {
  let latest = null;
  let ticks = 0;
  for (;;) {
    await delay(900);
    latest = await api(`/api/projects/${encodeURIComponent(projectId)}/progress`);
    renderAutoWorkflowProgress(latest.progress);
    updateAutoWorkflowButtons(latest.status, latest.progress || {});
    ticks += 1;
    if (ticks % 4 === 0) {
      await loadAutoJobs();
    }
    if (!isAutoWorkflowActive(latest.status, latest.progress || {})) {
      await loadAutoJobs();
      return latest;
    }
  }
}

function isAutoWorkflowActive(status = "", progress = {}) {
  return (
    ["queued", "running", "cancel_requested"].includes(status) ||
    ["queued", "running", "between_steps"].includes(progress.status)
  );
}

async function refreshAutoProgress(projectId) {
  if (!projectId || !els.autoWorkflowProgress) {
    return;
  }
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/progress`);
    renderAutoWorkflowProgress(payload.progress);
    updateAutoWorkflowButtons(payload.status, payload.progress || {});
  } catch {
    // Progress polling is best-effort; the main action will report hard failures.
  }
}

function renderAutoWorkflowProgress(progress = {}) {
  renderProgressPanel(els.autoWorkflowProgress, progress, 7);
}

function updateAutoWorkflowButtons(status = "", progress = {}) {
  const running = isAutoWorkflowActive(status, progress);
  const canResume = Boolean(progress.can_resume) || ["failed", "cancelled", "completed_with_warnings", "cancel_requested", "interrupted"].includes(status);
  if (els.runAutoWorkflow) {
    els.runAutoWorkflow.disabled = running;
  }
  if (els.resumeAutoWorkflow) {
    els.resumeAutoWorkflow.disabled = running || !canResume;
    els.resumeAutoWorkflow.title = canResume
      ? progress.resume_hint || progress.last_failure_diagnosis?.suggested_action || "从上次成功阶段继续生成"
      : "当前没有可继续的自动流程";
  }
  if (els.cancelAutoWorkflow) {
    els.cancelAutoWorkflow.disabled = !running || Boolean(progress.cancel_requested);
  }
}

function renderProgressPanel(element, progress = {}, fallbackTotal = 6) {
  if (!element) {
    return;
  }
  const steps = progress.steps || [];
  const current = progress.current_step;
  const liveStream = progress.live_stream || {};
  if (!steps.length && !current && !hasLiveStream(liveStream)) {
    element.classList.add("hidden");
    element.innerHTML = "";
    return;
  }
  element.classList.remove("hidden");
  element.setAttribute("role", "status");
  element.setAttribute("aria-live", "polite");
  const percent = Math.max(0, Math.min(100, Number(progress.percent) || 0));
  const allSteps = current ? [...steps, current] : steps;
  const currentTitle = current?.title || statusLabel(progress.status) || "等待更新";
  element.innerHTML = `
    <div class="progress-head">
      <div>
        <strong>${escapeHtml(currentTitle)}</strong>
        <span>${escapeHtml(progress.completed_steps ?? 0)} / ${escapeHtml(progress.total_steps || allSteps.length || fallbackTotal)} 阶段</span>
      </div>
      <b>${escapeHtml(percent)}%</b>
    </div>
    <div class="progress-bar"><i style="width: ${percent}%"></i></div>
    <div class="progress-steps">
      ${allSteps.map((step) => renderProgressStep(step, progress)).join("")}
    </div>
    ${renderLlmLiveStream(liveStream)}
  `;
}

function hasLiveStream(liveStream = {}) {
  return Boolean(
    liveStream &&
      (liveStream.current ||
        (liveStream.events && liveStream.events.length) ||
        liveStream.content_tail)
  );
}

function renderLlmLiveStream(liveStream = {}) {
  if (!hasLiveStream(liveStream)) {
    return "";
  }
  const current = liveStream.current || {};
  const events = (liveStream.events || []).slice(-6).reverse();
  const contentTail = current.content_tail || liveStream.content_tail || "";
  const status = current.status || liveStream.status || "running";
  const label = current.label || liveStream.title || "大模型实时输出";
  const chars = current.content_chars ?? liveStream.content_chars ?? 0;
  return `
    <div class="llm-live-stream" data-status="${escapeHtml(status)}">
      <div class="llm-live-head">
        <div>
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(statusLabel(status))} · 已接收 ${escapeHtml(chars)} 字符</span>
        </div>
        <b>实时</b>
      </div>
      ${contentTail ? `<pre>${escapeHtml(contentTail)}</pre>` : ""}
      <div class="llm-live-events">
        ${events.map(renderLiveEvent).join("")}
      </div>
    </div>
  `;
}

function renderLiveEvent(event) {
  const status = event.status || "info";
  const detail = event.detail ? ` · ${event.detail}` : "";
  return `
    <div class="llm-live-event" data-status="${escapeHtml(status)}">
      <span></span>
      <p>${escapeHtml(event.label || event.kind || "大模型操作")}${escapeHtml(detail)}</p>
    </div>
  `;
}

function renderProgressStep(step, progress = {}) {
  const status = step.status || "pending";
  const duration = step.duration_seconds ? ` · ${step.duration_seconds}s` : "";
  const detail = step.detail ? `<p>${escapeHtml(step.detail)}</p>` : "";
  const diagnosis = renderFailureDiagnosis(step.failure_diagnosis, {
    canResume: Boolean(progress.can_resume),
    resumeHint: progress.resume_hint,
  });
  const projectId = state.currentProject?.metadata?.id;
  const errorLog = projectId && step.error_log
    ? `<a class="progress-link" href="/api/projects/${encodeURIComponent(projectId)}/download/${encodeRelativePath(step.error_log)}">查看错误日志</a>`
    : "";
  return `
    <div class="progress-step" data-status="${escapeHtml(status)}">
      <span></span>
      <div>
        <strong>${escapeHtml(step.title || step.id || "阶段")}</strong>
        <small>${escapeHtml(statusLabel(status))}${escapeHtml(duration)}</small>
        ${detail}
        ${diagnosis}
        ${errorLog}
      </div>
    </div>
  `;
}

function renderFailureDiagnosis(diagnosis = {}, options = {}) {
  if (!diagnosis || typeof diagnosis !== "object" || !diagnosis.category) {
    return "";
  }
  const label = diagnosis.label || diagnosis.category || "失败诊断";
  const focus = diagnosis.repair_focus || diagnosis.evidence || "";
  const category = diagnosis.category ? `<b>${escapeHtml(diagnosis.category)}</b>` : "";
  const action = diagnosis.suggested_action || options.resumeHint || (options.canResume ? "点击继续生成，系统会带着本次诊断继续自动修复。" : "");
  const resumeButton = options.canResume && state.currentProject?.metadata?.id
    ? '<button class="diagnosis-resume" type="button" data-auto-action="resume">继续生成</button>'
    : "";
  return `
    <div class="failure-diagnosis">
      <div>
        <span>诊断</span>
        <strong>${escapeHtml(label)}</strong>
        ${category}
      </div>
      ${focus ? `<p>${escapeHtml(focus)}</p>` : ""}
      ${action || resumeButton ? `
        <div class="failure-diagnosis-actions">
          ${action ? `<p>建议动作：${escapeHtml(action)}</p>` : ""}
          ${resumeButton}
        </div>
      ` : ""}
    </div>
  `;
}

els.autoWorkflowProgress?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-auto-action='resume']");
  if (!button) {
    return;
  }
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.autoWorkflowStatus.textContent = "请先打开一个项目。";
    return;
  }
  button.disabled = true;
  await runAutoWorkflow(projectId, { resume: true });
});

els.runAutoWorkflow.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  await runAutoWorkflow(projectId);
});

if (els.resumeAutoWorkflow) {
  els.resumeAutoWorkflow.addEventListener("click", async () => {
    const projectId = state.currentProject?.metadata?.id;
    await runAutoWorkflow(projectId, { resume: true });
  });
}

if (els.cancelAutoWorkflow) {
  els.cancelAutoWorkflow.addEventListener("click", async () => {
    const projectId = state.currentProject?.metadata?.id;
    if (!projectId) {
      els.autoWorkflowStatus.textContent = "请先打开一个项目。";
      return;
    }
    els.cancelAutoWorkflow.disabled = true;
    els.autoWorkflowStatus.textContent = "已请求中断，系统会在当前阶段安全结束后停止。";
    try {
      const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/auto/cancel`, { method: "POST" });
      renderProject(payload.project);
      await refreshAutoProgress(projectId);
      await loadAutoJobs();
      await loadProjects();
      await loadTrustCenter();
    } catch (error) {
      els.autoWorkflowStatus.textContent = `中断请求失败：${error.message}`;
      els.cancelAutoWorkflow.disabled = false;
    }
  });
}

async function refreshDiagnosticsForProject(projectId) {
  els.refreshDiagnostics.disabled = true;
  els.diagnosticsStatus.textContent = "正在刷新附件画像、并行计划、性能健康和修复中心。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/diagnostics/refresh`, { method: "POST" });
    renderProject(payload.project);
    const health = payload.diagnostics?.health || {};
    const score = health.scores?.overall;
    const scoreText = Number.isFinite(Number(score)) ? `，综合 ${Number(score)} 分` : "";
    const repair = payload.diagnostics?.repair || {};
    const repairText = repair.label ? `，修复中心：${repair.label}` : "";
    els.diagnosticsStatus.textContent = `诊断资产已刷新：${health.label || "已完成"}${scoreText}${repairText}。`;
    showToast("诊断与性能报告已刷新", "success");
    await loadProjects();
    await loadTrustCenter();
  } catch (error) {
    els.diagnosticsStatus.textContent = `诊断刷新失败：${error.message}`;
    showToast(`诊断刷新失败：${error.message}`, "error");
  } finally {
    els.refreshDiagnostics.disabled = false;
  }
}

els.refreshDiagnostics?.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.diagnosticsStatus.textContent = "请先打开一个项目。";
    return;
  }
  await refreshDiagnosticsForProject(projectId);
});

async function refreshRepairCenterForProject(projectId) {
  if (els.refreshRepairCenter) {
    els.refreshRepairCenter.disabled = true;
  }
  if (els.repairCenterStatus) {
    els.repairCenterStatus.textContent = "正在重建自动修复简报。";
  }
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/repair/briefing`, { method: "POST" });
    renderProject(payload.project);
    const label = payload.repair?.label || payload.project?.metadata?.repair_center_label || "已完成";
    if (els.repairCenterStatus) {
      els.repairCenterStatus.textContent = `修复中心已刷新：${label}。`;
    }
    showToast("自动修复中心已刷新", "success");
    await loadProjects();
    await loadTrustCenter();
  } catch (error) {
    if (els.repairCenterStatus) {
      els.repairCenterStatus.textContent = `修复中心刷新失败：${error.message}`;
    }
    showToast(`修复中心刷新失败：${error.message}`, "error");
  } finally {
    if (els.refreshRepairCenter) {
      els.refreshRepairCenter.disabled = false;
    }
  }
}

els.refreshRepairCenter?.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.repairCenterStatus.textContent = "请先打开一个项目。";
    return;
  }
  await refreshRepairCenterForProject(projectId);
});

async function refreshDeliveryReadinessForProject(projectId) {
  if (els.refreshDeliveryReadiness) {
    els.refreshDeliveryReadiness.disabled = true;
  }
  if (els.deliveryReadinessStatus) {
    els.deliveryReadinessStatus.textContent = "正在检查论文、结果、审查和支撑材料交付状态。";
  }
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/delivery/readiness`, { method: "POST" });
    renderProject(payload.project);
    const label = payload.delivery?.label || payload.project?.metadata?.delivery_readiness_label || "已完成";
    const score = payload.delivery?.score ?? payload.project?.metadata?.delivery_readiness_score;
    const scoreText = Number.isFinite(Number(score)) ? `，交付分 ${Number(score)}` : "";
    if (els.deliveryReadinessStatus) {
      els.deliveryReadinessStatus.textContent = `交付就绪已刷新：${label}${scoreText}。`;
    }
    showToast("交付就绪中心已刷新", "success");
    await loadProjects();
    await loadGrowthMetrics();
    await loadTrustCenter();
  } catch (error) {
    if (els.deliveryReadinessStatus) {
      els.deliveryReadinessStatus.textContent = `交付就绪刷新失败：${error.message}`;
    }
    showToast(`交付就绪刷新失败：${error.message}`, "error");
  } finally {
    if (els.refreshDeliveryReadiness) {
      els.refreshDeliveryReadiness.disabled = false;
    }
  }
}

els.refreshDeliveryReadiness?.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.deliveryReadinessStatus.textContent = "请先打开一个项目。";
    return;
  }
  await refreshDeliveryReadinessForProject(projectId);
});

els.repairCenter?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-repair-action]");
  if (!button) {
    return;
  }
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    return;
  }
  const command = button.dataset.repairAction;
  if (command === "resume") {
    await runAutoWorkflow(projectId, { resume: true });
    return;
  }
  if (command === "start") {
    await runAutoWorkflow(projectId, { resume: false });
    return;
  }
  if (command === "diagnostics") {
    await refreshDiagnosticsForProject(projectId);
    return;
  }
  if (command === "open_report") {
    const artifacts = state.currentProject?.metadata?.artifacts || {};
    const path = artifacts.repair_briefing || artifacts.repair_briefing_json || artifacts.computed_solver_repair;
    if (path) {
      window.open(`/api/projects/${encodeURIComponent(projectId)}/download/${encodeRelativePath(path)}`, "_blank", "noopener");
    }
  }
});

els.deliveryCenter?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delivery-action]");
  if (!button) {
    return;
  }
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    return;
  }
  const command = button.dataset.deliveryAction;
  button.disabled = true;
  try {
    if (command === "resume") {
      await runAutoWorkflow(projectId, { resume: true });
      return;
    }
    if (command === "start") {
      await runAutoWorkflow(projectId, { resume: false });
      return;
    }
    if (command === "analyze") {
      if (els.deliveryReadinessStatus) {
        els.deliveryReadinessStatus.textContent = "正在重建赛题分析并刷新交付门禁。";
      }
      const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/analyze`, { method: "POST" });
      renderProject(payload.project);
      await refreshDeliveryReadinessForProject(projectId);
      await loadProjects();
      return;
    }
    if (command === "diagnostics") {
      await refreshDiagnosticsForProject(projectId);
      await refreshDeliveryReadinessForProject(projectId);
      return;
    }
    if (command === "repair") {
      await refreshRepairCenterForProject(projectId);
      await refreshDeliveryReadinessForProject(projectId);
      return;
    }
    if (command === "package") {
      if (els.deliveryReadinessStatus) {
        els.deliveryReadinessStatus.textContent = "正在生成正式交付包、清单和文件哈希。";
      }
      const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/delivery/package`, { method: "POST" });
      renderProject(payload.project);
      const size = payload.package?.package?.size_bytes;
      const sizeText = Number.isFinite(Number(size)) ? `，大小 ${formatBytes(Number(size))}` : "";
      if (els.deliveryReadinessStatus) {
        els.deliveryReadinessStatus.textContent = `正式交付包已生成${sizeText}。`;
      }
      showToast("正式交付包已生成", "success");
      await loadProjects();
      await loadGrowthMetrics();
      await loadTrustCenter();
      return;
    }
    if (command === "compile") {
      els.compileStatus.textContent = "正在编译 PDF 并导出 Word。";
      const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/compile`, { method: "POST" });
      renderProject(payload.project);
      els.compileStatus.textContent = payload.compile.success ? "编译完成：已生成 PDF，并导出 Word 文档。" : "编译失败，请查看编译日志和 Word 导出日志。";
      await loadProjects();
      return;
    }
    if (command === "review") {
      els.paperReviewStatus.textContent = "正在审查论文结构、图表、编译日志和结果可追溯性。";
      const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/paper/review`, { method: "POST" });
      renderProject(payload.project);
      els.paperReviewStatus.textContent = "论文审查完成，可查看审查报告。";
      await loadProjects();
      return;
    }
    if (command === "support_zip") {
      window.open(`/api/projects/${encodeURIComponent(projectId)}/download/support.zip`, "_blank", "noopener");
    }
  } catch (error) {
    if (els.deliveryReadinessStatus) {
      els.deliveryReadinessStatus.textContent = `交付动作失败：${error.message}`;
    }
    showToast(`交付动作失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
});

els.generateSkillReport.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.skillReportStatus.textContent = "请先打开一个项目。";
    return;
  }
  els.generateSkillReport.disabled = true;
  els.skillReportStatus.textContent = "正在整理 GitHub 数学建模、科研写作、模型路由和学术诚信门禁规则。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/skills/report`, { method: "POST" });
    renderProject(payload.project);
    els.skillReportStatus.textContent = "技能库与诚信门禁报告已生成，可在生成文件中查看。";
    await loadProjects();
  } catch (error) {
    els.skillReportStatus.textContent = `技能库与诚信门禁报告生成失败：${error.message}`;
  } finally {
    els.generateSkillReport.disabled = false;
  }
});

els.generateCodeGraph.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.codeGraphStatus.textContent = "请先打开一个项目。";
    return;
  }
  els.generateCodeGraph.disabled = true;
  els.codeGraphStatus.textContent = "正在扫描项目代码，生成符号、导入和调用关系图谱。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/codegraph/report`, { method: "POST" });
    renderProject(payload.project);
    els.codeGraphStatus.textContent = "代码图谱已生成，可在生成文件中查看。";
    await loadProjects();
  } catch (error) {
    els.codeGraphStatus.textContent = `代码图谱生成失败：${error.message}`;
  } finally {
    els.generateCodeGraph.disabled = false;
  }
});

els.fillPaper.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.paperFillStatus.textContent = "请先打开一个项目。";
    return;
  }
  els.fillPaper.disabled = true;
  els.paperFillStatus.textContent = "正在把结果整合到 LaTeX。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/paper/fill`, { method: "POST" });
    renderProject(payload.project);
    els.paperFillStatus.textContent = "论文回填完成，可继续编译 LaTeX。";
    await loadProjects();
  } catch (error) {
    els.paperFillStatus.textContent = `回填失败：${error.message}`;
  } finally {
    els.fillPaper.disabled = false;
  }
});

els.compile.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.compileStatus.textContent = "请先打开一个项目。";
    return;
  }
  els.compile.disabled = true;
  els.compileStatus.textContent = "正在编译 PDF 并导出 Word。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/compile`, { method: "POST" });
    renderProject(payload.project);
    els.compileStatus.textContent = payload.compile.success
      ? "编译完成：已生成 PDF，并导出 Word 文档。"
      : "编译失败，请查看编译日志和 Word 导出日志。";
    await loadProjects();
  } catch (error) {
    els.compileStatus.textContent = `编译失败：${error.message}`;
  } finally {
    els.compile.disabled = false;
  }
});

els.reviewPaper.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.paperReviewStatus.textContent = "请先打开一个项目。";
    return;
  }
  els.reviewPaper.disabled = true;
  els.paperReviewStatus.textContent = "正在审查论文结构、图表、编译日志和结果可追溯性。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/paper/review`, { method: "POST" });
    renderProject(payload.project);
    els.paperReviewStatus.textContent = "论文审查完成，可查看审查报告。";
    await loadProjects();
  } catch (error) {
    els.paperReviewStatus.textContent = `审查失败：${error.message}`;
  } finally {
    els.reviewPaper.disabled = false;
  }
});

function initModuleTabs() {
  const tabs = Array.from(document.querySelectorAll("[data-module-tab]"));
  if (!tabs.length) {
    return;
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => {
      activateModuleTab(tab.dataset.moduleTab);
    });
    tab.addEventListener("keydown", (event) => {
      const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
      if (!keys.includes(event.key)) {
        return;
      }
      event.preventDefault();
      let nextIndex = index;
      if (event.key === "ArrowRight") {
        nextIndex = (index + 1) % tabs.length;
      } else if (event.key === "ArrowLeft") {
        nextIndex = (index - 1 + tabs.length) % tabs.length;
      } else if (event.key === "Home") {
        nextIndex = 0;
      } else if (event.key === "End") {
        nextIndex = tabs.length - 1;
      }
      activateModuleTab(tabs[nextIndex].dataset.moduleTab, { focus: true });
    });
  });
  activateModuleTab(readPreference("mmw-active-module", tabs[0].dataset.moduleTab));
}

els.runLlmAnalysis.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.llmAnalysisStatus.textContent = "请先打开一个项目。";
    return;
  }
  els.runLlmAnalysis.disabled = true;
  els.llmAnalysisStatus.textContent = "正在调用大模型分析赛题并刷新大模型报告。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/llm/analyze`, { method: "POST" });
    renderProject(payload.project);
    els.llmAnalysisStatus.textContent = "大模型分析完成，可查看分析报告。";
    await loadProjects();
  } catch (error) {
    els.llmAnalysisStatus.textContent = `大模型分析失败：${error.message}`;
  } finally {
    els.runLlmAnalysis.disabled = false;
  }
});

initThemeToggle();
initModuleTabs();
checkHealth();
loadProjects({ restore: true }).catch((error) => {
  showToast(`项目列表加载失败：${error.message}`, "error");
});
loadExperienceCenter();
loadAutoJobs();
loadGrowthMetrics();
loadTrustCenter();
