const state = {
  currentProject: null,
  templates: [],
  llmSettings: null,
  uploadProgressStop: null,
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
  projectList: document.querySelector("#project-list"),
  health: document.querySelector("#health"),
  llmSettingsForm: document.querySelector("#llm-settings-form"),
  apiKeyInput: document.querySelector("#api-key-input"),
  baseUrlInput: document.querySelector("#base-url-input"),
  modelInput: document.querySelector("#model-input"),
  clearLlmSettings: document.querySelector("#clear-llm-settings"),
  llmSettingsStatus: document.querySelector("#llm-settings-status"),
  title: document.querySelector("#project-title"),
  environment: document.querySelector("#environment-status"),
  empty: document.querySelector("#empty-state"),
  analysisView: document.querySelector("#analysis-view"),
  recommended: document.querySelector("#recommended-problem"),
  problemSelectionStatus: document.querySelector("#problem-selection-status"),
  documentCount: document.querySelector("#document-count"),
  dataCount: document.querySelector("#data-count"),
  projectStatus: document.querySelector("#project-status"),
  statusCards: document.querySelector("#status-cards"),
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
  autoWorkflowStatus: document.querySelector("#auto-workflow-status"),
  autoWorkflowProgress: document.querySelector("#auto-workflow-progress"),
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
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
    const detail = payload?.detail || text || response.statusText || `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload ?? {};
}

async function checkHealth() {
  try {
    await api("/api/health");
    els.health.textContent = "已连接";
    const env = await api("/api/environments");
    renderEnvironments(env);
    await loadLlmSettings();
    await loadTemplates();
  } catch {
    els.health.textContent = "未连接";
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
  if (settings.configured) {
    const source = settings.source === "env" ? "环境变量" : "本地设置";
    els.llmSettingsStatus.textContent = `已配置：${settings.masked_api_key} · ${source}`;
  } else {
    els.llmSettingsStatus.textContent = "尚未配置 API Key。";
  }
}

async function loadProjects() {
  const projects = await api("/api/projects");
  if (!projects.length) {
    els.projectList.innerHTML = '<p class="status">暂无项目</p>';
    return;
  }
  els.projectList.innerHTML = projects
    .map(
      (project) => {
        const active = state.currentProject?.metadata?.id === project.id ? " is-active" : "";
        return `
        <button class="project-button${active}" type="button" data-project-id="${escapeHtml(project.id)}">
          <span class="project-name">${escapeHtml(project.name)}</span>
          <span class="project-meta">${escapeHtml(project.created_at)} · ${escapeHtml(project.status)}</span>
        </button>
      `;
      },
    )
    .join("");
  els.projectList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => openProject(button.dataset.projectId));
  });
}

async function openProject(projectId) {
  const detail = await api(`/api/projects/${projectId}`);
  renderProject(detail);
}

function renderProject(detail) {
  state.currentProject = detail;
  syncProjectSelection();
  const { metadata, analysis } = detail;
  els.title.textContent = metadata.name || metadata.original_name || "项目";
  els.projectStatus.textContent = metadata.auto_workflow_status
    ? `${metadata.status || "-"} · 自动流程：${metadata.auto_workflow_status}`
    : metadata.status || "-";
  if (!analysis) {
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
  renderPaperOptions(metadata);
  renderModelAssistantOptions(analysis, rec);
  renderArtifacts(metadata, analysis.project?.id || metadata.id);
  renderAutoWorkflowProgress(metadata.auto_workflow_progress);
  renderModelAssistantProgress(metadata.model_assistant_progress);
  renderProgressPanel(els.uploadProgress, metadata.analysis_progress, 7);
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

function renderStatusCards(metadata, analysis) {
  if (!els.statusCards) {
    return;
  }
  const cards = [
    {
      title: "赛题解析",
      value: analysis ? "已完成" : "等待",
      detail: `${analysis?.problems?.length || 0} 个候选题，${analysis?.inventory?.length || 0} 个材料文件`,
      status: analysis ? "success" : "pending",
    },
    {
      title: "LLM 分析",
      value: statusLabel(metadata.llm_analysis_status),
      detail: metadata.llm_analysis_status === "requires_api_key" ? "需要先填写 API Key" : "选题和建模建议",
      status: statusTone(metadata.llm_analysis_status),
    },
    {
      title: "自动解题",
      value: statusLabel(metadata.auto_workflow_status),
      detail: metadata.auto_workflow_mode || "LLM+代码一键流程",
      status: statusTone(metadata.auto_workflow_status),
    },
    {
      title: "模型辅助",
      value: statusLabel(metadata.model_assistant_status),
      detail: "自定义模型补充和过程记录",
      status: statusTone(metadata.model_assistant_status),
    },
    {
      title: "代码求解",
      value: statusLabel(metadata.computed_solution_status),
      detail: "结果表、图片和 manifest",
      status: statusTone(metadata.computed_solution_status),
    },
    {
      title: "LaTeX 编译",
      value: statusLabel(metadata.compile_status),
      detail: "生成 paper/main.pdf",
      status: statusTone(metadata.compile_status),
    },
    {
      title: "论文审查",
      value: statusLabel(metadata.paper_review_status),
      detail: "结构、图表、页数和可追溯性",
      status: statusTone(metadata.paper_review_status),
    },
  ];
  els.statusCards.innerHTML = cards
    .map(
      (card) => `
        <article class="status-card" data-status="${card.status}">
          <span class="status-dot"></span>
          <div>
            <h3>${escapeHtml(card.title)}</h3>
            <strong>${escapeHtml(card.value)}</strong>
            <p>${escapeHtml(card.detail)}</p>
          </div>
        </article>
      `,
    )
    .join("");
}

function statusLabel(value) {
  const labels = {
    success: "已完成",
    analyzed: "已分析",
    running: "运行中",
    failed: "失败",
    completed_with_warnings: "需复核",
    requires_api_key: "待配置",
    script_generated: "已生成",
    between_steps: "阶段切换中",
    idle: "未开始",
    warning: "需注意",
  };
  return labels[value] || value || "未开始";
}

function statusTone(value) {
  if (value === "success" || value === "analyzed" || value === "script_generated") {
    return "success";
  }
  if (value === "running") {
    return "running";
  }
  if (value === "failed") {
    return "failed";
  }
  if (value === "completed_with_warnings" || value === "requires_api_key") {
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
      const tasks = (problem.tasks || []).slice(0, 3).map((task) => `<li>${escapeHtml(task)}</li>`).join("");
      const modelTypes = renderChipRow(problem.model_types, "is-muted");
      const methods = renderChipRow(problem.suggested_methods);
      const risks = renderChipRow(problem.risk_items, "is-risk");
      const selectDisabled = problem.id === selectedId ? " disabled" : "";
      const selectLabel = problem.id === selectedId ? "已选择" : "选择此题";
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
          <div class="chip-row">
            <span class="problem-score">综合得分 ${escapeHtml(problem.fit_score)}</span>
            <span class="chip is-muted">AI适配 ${escapeHtml(problem.ai_fit || "-")}</span>
            <span class="chip is-muted">可行性 ${escapeHtml(problem.feasibility || "-")}</span>
          </div>
          ${renderScoreBreakdown(problem.score_breakdown)}
          ${modelTypes ? `<div class="chip-row">${modelTypes}</div>` : ""}
          ${methods ? `<div class="chip-row">${methods}</div>` : ""}
          ${risks ? `<div class="chip-row">${risks}</div>` : ""}
          ${tasks ? `<ul class="problem-meta">${tasks}</ul>` : ""}
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
    ["llm_problem_structure", "LLM 赛题结构增强"],
    ["llm_problem_analysis", "LLM 赛题分析"],
    ["llm_baseline_review", "LLM 基线复盘"],
    ["llm_specialized_review", "LLM 专项复盘"],
    ["llm_model_assistant", "LLM 模型辅助"],
    ["llm_model_assistant_history", "LLM 模型辅助历史"],
    ["llm_full_solution", "LLM 全流程题解"],
    ["llm_paper_latex", "LLM LaTeX 生成记录"],
    ["computed_solver_spec", "LLM 代码求解规范"],
    ["computed_solver_script", "代码求解脚本"],
    ["computed_solver_repair", "代码求解自动修复记录"],
    ["computed_solver_log", "代码运行日志"],
    ["computed_solution_status", "代码运行状态 JSON"],
    ["computed_manifest", "代码计算结果清单"],
    ["computed_summary", "代码计算结果摘要"],
    ["computed_result_prose", "结果整合说明"],
    ["paper_result_filled", "结果整合论文 LaTeX"],
    ["auto_workflow_report", "自动解题报告"],
    ["auto_workflow_report_json", "自动解题 JSON"],
    ["backend_skill_research", "GitHub 技能库与诚信门禁报告"],
    ["backend_skill_research_json", "GitHub 技能库与诚信门禁 JSON"],
    ["code_graph_report", "代码图谱报告"],
    ["code_graph_json", "代码图谱 JSON"],
    ["paper_autofilled", "回填论文 LaTeX"],
    ["paper_llm", "LLM 论文 LaTeX"],
    ["paper_fill_summary", "回填摘要"],
    ["format_rules_summary", "格式规则摘要"],
    ["paper_pdf", "论文 PDF"],
    ["paper_docx", "论文 Word"],
    ["latex_log", "编译日志"],
    ["word_export_log", "Word 导出日志"],
    ["paper_review", "论文审查报告"],
    ["paper_review_json", "论文审查 JSON"],
    ["material_passport_json", "材料护照 JSON"],
    ["llm_problem_structure_json", "LLM 赛题结构增强 JSON"],
    ["llm_problem_analysis_json", "LLM 赛题分析 JSON"],
    ["llm_baseline_review_json", "LLM 基线复盘 JSON"],
    ["llm_specialized_review_json", "LLM 专项复盘 JSON"],
    ["llm_model_assistant_json", "LLM 模型辅助 JSON"],
    ["llm_model_assistant_history_json", "LLM 模型辅助历史 JSON"],
    ["llm_full_solution_json", "LLM 全流程题解 JSON"],
    ["llm_paper_latex_json", "LLM LaTeX 生成 JSON"],
    ["computed_solver_spec_json", "LLM 代码求解规范 JSON"],
    ["computed_solver_script_json", "代码求解脚本 JSON"],
    ["computed_solver_repair_json", "代码求解自动修复 JSON"],
    ["computed_result_prose_json", "结果整合说明 JSON"],
  ]
    .filter(([key]) => artifacts[key])
    .map(([key, label]) => [key, label, artifacts[key]]);
  items.push(["support_zip", "支撑材料包", "support.zip"]);
  if (!items.length) {
    els.artifacts.innerHTML = '<p class="status">暂无生成文件。</p>';
    return;
  }
  const grouped = new Map();
  items.forEach(([key, label, path]) => {
    const group = artifactGroup(key, path);
    if (!grouped.has(group)) {
      grouped.set(group, []);
    }
    grouped.get(group).push([key, label, path]);
  });
  els.artifacts.innerHTML = Array.from(grouped.entries())
    .map(([group, groupItems]) => {
      const links = groupItems
        .map(([key, label, path]) => renderArtifactItem(projectId, key, label, path))
        .join("");
      return `
        <section class="artifact-group">
          <h3>${escapeHtml(group)}</h3>
          <div class="artifact-list">${links}</div>
        </section>
      `;
    })
    .join("");
}

function renderArtifactItem(projectId, key, label, path) {
  const encodedProject = encodeURIComponent(projectId);
  const encodedPath = encodeURI(path);
  return `
    <div class="artifact-row">
      <a class="artifact-link" data-kind="${artifactKind(key, path)}" href="/api/projects/${encodedProject}/download/${encodedPath}" title="${escapeHtml(path)}">${escapeHtml(label)}</a>
      <button class="artifact-open" type="button" data-project-id="${escapeHtml(projectId)}" data-path="${escapeHtml(path)}" title="在资源管理器中打开所在位置">打开位置</button>
    </div>
  `;
}

els.artifacts.addEventListener("click", async (event) => {
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
    await api(`/api/projects/${encodeURIComponent(projectId)}/open-location/${encodeURI(path)}`, { method: "POST" });
    button.textContent = "已打开";
    window.setTimeout(() => {
      button.textContent = originalText;
      button.disabled = false;
    }, 1400);
  } catch (error) {
    button.textContent = "打开失败";
    els.projectStatus.textContent = `打开文件位置失败：${error.message}`;
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
  if (value.includes("report") || value.includes("analysis") || value.includes("review") || value.includes("skill")) {
    return "分析报告";
  }
  if (value.includes("passport")) {
    return "分析报告";
  }
  if (value.includes("script") || value.includes("solver") || value.endsWith(".py")) {
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
    renderProject(detail);
    await loadProjects();
    if (els.autoRunAfterUpload?.checked) {
      const rec = detail.analysis?.recommended_problem || {};
      if (rec.id) {
        await selectProblem(rec.id);
        await runAutoWorkflow(
          detail.metadata.id,
          "上传分析完成，已按系统推荐题目确认选择，正在调用大模型生成并运行代码，随后回填结果、撰写论文和审查。",
        );
      } else {
        els.status.textContent = "分析完成，但未识别到可自动确认的推荐题目，请在选题模块手动选择。";
      }
    }
  } catch (error) {
    await refreshUploadProgress(progressId);
    els.status.textContent = `分析失败：${error.message}`;
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

els.refresh.addEventListener("click", loadProjects);

els.llmSettingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = els.llmSettingsForm.querySelector("button[type='submit']");
  button.disabled = true;
  els.llmSettingsStatus.textContent = "正在保存 AI 设置。";
  try {
    const payload = {
      api_key: els.apiKeyInput.value,
      base_url: els.baseUrlInput.value,
      model: els.modelInput.value,
    };
    const settings = await api("/api/settings/llm", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderLlmSettings(settings);
  } catch (error) {
    els.llmSettingsStatus.textContent = `保存失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
});

els.clearLlmSettings.addEventListener("click", async () => {
  els.clearLlmSettings.disabled = true;
  els.llmSettingsStatus.textContent = "正在清除 AI 设置。";
  try {
    const settings = await api("/api/settings/llm", { method: "DELETE" });
    renderLlmSettings(settings);
  } catch (error) {
    els.llmSettingsStatus.textContent = `清除失败：${error.message}`;
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
  els.modelAssistantStatus.textContent = "正在生成模型辅助方案，下面会显示检索、提示词构建和 LLM 生成过程。";
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
      ? `模型辅助方案已生成：<a href="/api/projects/${encodeURIComponent(projectId)}/download/${encodeURI(report)}">查看报告</a>。`
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

async function runAutoWorkflow(projectId, initialMessage = "正在调用大模型完成选题、生成并运行代码、回填结果、论文生成和审查。") {
  if (!projectId) {
    els.autoWorkflowStatus.textContent = "请先打开一个项目。";
    return;
  }
  const settings = state.llmSettings || (await api("/api/settings/llm"));
  state.llmSettings = settings;
  if (!settings.configured) {
    els.autoWorkflowStatus.textContent = "请先在左侧 AI 设置中填写 API Key；LLM+代码自动解题不提供本地降级模式。";
    return;
  }
  const selectedId = selectedProblemId(state.currentProject?.metadata || {});
  if (!selectedId) {
    els.autoWorkflowStatus.textContent = "请先在“选题”模块点击“选择此题”，确认后再运行一键自动流程。";
    return;
  }
  els.runAutoWorkflow.disabled = true;
  els.autoWorkflowStatus.textContent = initialMessage;
  const stopProgressPolling = startAutoProgressPolling(projectId);
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/auto/run`, { method: "POST" });
    renderProject(payload.project);
    const workflow = payload.auto_workflow || {};
    const steps = workflow.steps || [];
    const warningCount = steps.filter((step) => step.status === "warning").length;
    const failedCount = steps.filter((step) => step.status === "failed").length;
    if (workflow.overall_status === "success") {
      els.autoWorkflowStatus.textContent = "LLM+代码自动流程完成：已生成题解方案、运行代码得到结果、回填论文、审查报告和支撑材料。";
    } else {
      els.autoWorkflowStatus.textContent = `自动流程完成但需复核：${warningCount} 个警告，${failedCount} 个失败项。请查看自动解题报告。`;
    }
    await loadProjects();
  } catch (error) {
    els.autoWorkflowStatus.textContent = `自动流程失败：${error.message}`;
  } finally {
    stopProgressPolling();
    await refreshAutoProgress(projectId);
    els.runAutoWorkflow.disabled = false;
  }
}

function startAutoProgressPolling(projectId) {
  let stopped = false;
  refreshAutoProgress(projectId);
  const timer = window.setInterval(() => {
    if (!stopped) {
      refreshAutoProgress(projectId);
    }
  }, 700);
  return () => {
    stopped = true;
    window.clearInterval(timer);
  };
}

async function refreshAutoProgress(projectId) {
  if (!projectId || !els.autoWorkflowProgress) {
    return;
  }
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/progress`);
    renderAutoWorkflowProgress(payload.progress);
  } catch {
    // Progress polling is best-effort; the main action will report hard failures.
  }
}

function renderAutoWorkflowProgress(progress = {}) {
  renderProgressPanel(els.autoWorkflowProgress, progress, 6);
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
      ${allSteps.map(renderProgressStep).join("")}
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
      <p>${escapeHtml(event.label || event.kind || "LLM 操作")}${escapeHtml(detail)}</p>
    </div>
  `;
}

function renderProgressStep(step) {
  const status = step.status || "pending";
  const duration = step.duration_seconds ? ` · ${step.duration_seconds}s` : "";
  const detail = step.detail ? `<p>${escapeHtml(step.detail)}</p>` : "";
  const projectId = state.currentProject?.metadata?.id;
  const errorLog = projectId && step.error_log
    ? `<a class="progress-link" href="/api/projects/${encodeURIComponent(projectId)}/download/${encodeURI(step.error_log)}">查看错误日志</a>`
    : "";
  return `
    <div class="progress-step" data-status="${escapeHtml(status)}">
      <span></span>
      <div>
        <strong>${escapeHtml(step.title || step.id || "阶段")}</strong>
        <small>${escapeHtml(statusLabel(status))}${escapeHtml(duration)}</small>
        ${detail}
        ${errorLog}
      </div>
    </div>
  `;
}

els.runAutoWorkflow.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  await runAutoWorkflow(projectId);
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
  const panels = Array.from(document.querySelectorAll("[data-module-panel]"));
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.moduleTab;
      tabs.forEach((item) => item.classList.toggle("is-active", item === tab));
      panels.forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.modulePanel === target);
      });
    });
  });
}

els.runLlmAnalysis.addEventListener("click", async () => {
  const projectId = state.currentProject?.metadata?.id;
  if (!projectId) {
    els.llmAnalysisStatus.textContent = "请先打开一个项目。";
    return;
  }
  els.runLlmAnalysis.disabled = true;
  els.llmAnalysisStatus.textContent = "正在调用大模型分析赛题并刷新 LLM 报告。";
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/llm/analyze`, { method: "POST" });
    renderProject(payload.project);
    els.llmAnalysisStatus.textContent = "LLM 分析完成，可查看分析报告。";
    await loadProjects();
  } catch (error) {
    els.llmAnalysisStatus.textContent = `LLM 分析失败：${error.message}`;
  } finally {
    els.runLlmAnalysis.disabled = false;
  }
});

initModuleTabs();
checkHealth();
loadProjects();
