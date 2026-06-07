(globalThis.TURBOPACK||(globalThis.TURBOPACK=[])).push(["object"==typeof document?document.currentScript:void 0,46021,(e,t,a)=>{let r={currentProject:null,projects:[],projectQuery:"",selectedProjectIds:new Set,templates:[],llmSettings:null,autoJobs:null,deliveryBatchJobs:null,capacitySettings:null,capacityAutotune:null,growthMetrics:null,trustMetrics:null,trustExports:null,repairCampaigns:null,repairBriefing:null,deliveryReadiness:null,deliveryPackage:null,uploadProgressStop:null},s={form:document.querySelector("#upload-form"),file:document.querySelector("#file-input"),fileLabel:document.querySelector("#file-label"),folder:document.querySelector("#folder-input"),folderLabel:document.querySelector("#folder-label"),autoRunAfterUpload:document.querySelector("#auto-run-after-upload"),status:document.querySelector("#upload-status"),uploadProgress:document.querySelector("#upload-analysis-progress"),refresh:document.querySelector("#refresh-projects"),projectSearch:document.querySelector("#project-search"),projectCount:document.querySelector("#project-count"),selectAnalyzedProjects:document.querySelector("#select-analyzed-projects"),clearProjectSelection:document.querySelector("#clear-project-selection"),batchStartProjects:document.querySelector("#batch-start-projects"),batchProjectStatus:document.querySelector("#batch-project-status"),projectList:document.querySelector("#project-list"),health:document.querySelector("#health"),themeToggle:document.querySelector("#theme-toggle"),themeToggleLabel:document.querySelector("#theme-toggle-label"),llmSettingsForm:document.querySelector("#llm-settings-form"),apiKeyInput:document.querySelector("#api-key-input"),baseUrlInput:document.querySelector("#base-url-input"),modelInput:document.querySelector("#model-input"),workflowStrategyInput:document.querySelector("#workflow-strategy-input"),workflowStrategyHint:document.querySelector("#workflow-strategy-hint"),clearLlmSettings:document.querySelector("#clear-llm-settings"),llmSettingsStatus:document.querySelector("#llm-settings-status"),title:document.querySelector("#project-title"),openProjectRoot:document.querySelector("#open-project-root"),environment:document.querySelector("#environment-status"),empty:document.querySelector("#empty-state"),analysisView:document.querySelector("#analysis-view"),recommended:document.querySelector("#recommended-problem"),problemSelectionStatus:document.querySelector("#problem-selection-status"),documentCount:document.querySelector("#document-count"),dataCount:document.querySelector("#data-count"),projectStatus:document.querySelector("#project-status"),statusCards:document.querySelector("#status-cards"),growthCenter:document.querySelector("#growth-center"),refreshGrowthMetrics:document.querySelector("#refresh-growth-metrics"),growthCenterStatus:document.querySelector("#growth-center-status"),trustCenter:document.querySelector("#trust-center"),refreshTrustCenter:document.querySelector("#refresh-trust-center"),trustCenterStatus:document.querySelector("#trust-center-status"),refreshAutoJobs:document.querySelector("#refresh-auto-jobs"),autoJobCenter:document.querySelector("#auto-job-center"),repairCenter:document.querySelector("#repair-center"),refreshRepairCenter:document.querySelector("#refresh-repair-center"),repairCenterStatus:document.querySelector("#repair-center-status"),deliveryCenter:document.querySelector("#delivery-center"),refreshDeliveryReadiness:document.querySelector("#refresh-delivery-readiness"),deliveryReadinessStatus:document.querySelector("#delivery-readiness-status"),problemCards:document.querySelector("#problem-cards"),workflow:document.querySelector("#workflow"),inventory:document.querySelector("#inventory"),paperOptionsForm:document.querySelector("#paper-options-form"),templateSelect:document.querySelector("#template-select"),targetBodyPages:document.querySelector("#target-body-pages"),paperOptionsStatus:document.querySelector("#paper-options-status"),templateUploadForm:document.querySelector("#template-upload-form"),templateNameInput:document.querySelector("#template-name-input"),templateFileInput:document.querySelector("#template-file-input"),templateFileLabel:document.querySelector("#template-file-label"),templateStatus:document.querySelector("#template-status"),templateHint:document.querySelector("#template-hint"),deleteTemplate:document.querySelector("#delete-template"),modelAssistantForm:document.querySelector("#model-assistant-form"),assistProblemSelect:document.querySelector("#assist-problem-select"),assistModelInput:document.querySelector("#assist-model-input"),assistGoalInput:document.querySelector("#assist-goal-input"),modelAssistantStatus:document.querySelector("#model-assistant-status"),modelAssistantProgress:document.querySelector("#model-assistant-progress"),artifacts:document.querySelector("#artifacts"),runModeling:document.querySelector("#run-modeling"),modelingStatus:document.querySelector("#modeling-status"),runSpecialized:document.querySelector("#run-specialized"),specializedStatus:document.querySelector("#specialized-status"),runAutoWorkflow:document.querySelector("#run-auto-workflow"),resumeAutoWorkflow:document.querySelector("#resume-auto-workflow"),cancelAutoWorkflow:document.querySelector("#cancel-auto-workflow"),autoWorkflowStatus:document.querySelector("#auto-workflow-status"),autoWorkflowProgress:document.querySelector("#auto-workflow-progress"),refreshDiagnostics:document.querySelector("#refresh-diagnostics"),diagnosticsStatus:document.querySelector("#diagnostics-status"),generateSkillReport:document.querySelector("#generate-skill-report"),skillReportStatus:document.querySelector("#skill-report-status"),generateCodeGraph:document.querySelector("#generate-code-graph"),codeGraphStatus:document.querySelector("#code-graph-status"),fillPaper:document.querySelector("#fill-paper"),paperFillStatus:document.querySelector("#paper-fill-status"),compile:document.querySelector("#compile-latex"),compileStatus:document.querySelector("#compile-status"),reviewPaper:document.querySelector("#review-paper"),paperReviewStatus:document.querySelector("#paper-review-status"),runLlmAnalysis:document.querySelector("#run-llm-analysis"),llmAnalysisStatus:document.querySelector("#llm-analysis-status"),toastRegion:document.querySelector("#toast-region")};function n(e){return String(e??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;")}function o(e){return String(e??"").split("/").map(e=>encodeURIComponent(e)).join("/")}function i(e,t=""){try{return window.localStorage.getItem(e)||t}catch{return t}}function l(e,t){try{window.localStorage.setItem(e,t)}catch{}}function c(e,{persist:t=!1}={}){let a="dark"===e?"dark":"light";document.documentElement.dataset.theme=a,t&&l("modelark-theme",a);let r="dark"===a;s.themeToggle&&(s.themeToggle.setAttribute("aria-checked",r?"true":"false"),s.themeToggle.setAttribute("aria-label",r?"切换到浅色模式":"切换到深色模式")),s.themeToggleLabel&&(s.themeToggleLabel.textContent=r?"深色":"浅色")}function u(e){return String(e??"").trim().toLowerCase()}function d(e,t="info"){if(!s.toastRegion||!e)return;let a=document.createElement("div");a.className=`toast toast-${t}`,a.setAttribute("role","error"===t?"alert":"status"),a.textContent=e,s.toastRegion.appendChild(a),window.setTimeout(()=>{a.classList.add("is-leaving"),window.setTimeout(()=>a.remove(),180)},2800)}async function p(e,t={}){let a=await fetch(e,t),r=await a.text(),s=null;if(r)try{s=JSON.parse(r)}catch{s=null}if(!a.ok)throw Error(s?.detail||r||a.statusText||`HTTP ${a.status}`);return s??{}}async function m(){try{var e;let t,a,r,n;await p("/api/health"),s.health.textContent="已连接",s.health.dataset.status="connected";e=await p("/api/environments"),t=e.local_python?.available?`Python ${e.local_python.version}`:"Python 不可用",a=e.pandoc?.available?"Pandoc 可用":"Pandoc 缺失",r=e.xelatex?.available?"XeLaTeX 可用":"XeLaTeX 缺失",n=function(e={}){return({checking:"依赖检查中",installing:"依赖下载中",ready:"依赖已就绪",partial:"依赖需重启/复核",manual_required:"需手动安装依赖",unreadable:"依赖状态不可读"})[e.status||""]||""}(e.dependency_install),s.environment.textContent=`${t} \xb7 ${a} \xb7 ${r}${n?` \xb7 ${n}`:""}`,await _(),await g()}catch{s.health.textContent="未连接",s.health.dataset.status="disconnected"}}async function _(){f(await p("/api/settings/llm"))}async function g(){r.templates=(await p("/api/templates")).templates||[],b(r.currentProject?.metadata?.paper_options?.template_id||"builtin-default")}function b(e="builtin-default"){s.templateSelect&&(s.templateSelect.innerHTML=r.templates.map(t=>{let a=t.id===e?" selected":"",r=t.is_builtin?"（内置）":"rules"===t.mode?"（格式说明）":"（LaTeX 模板）";return`<option value="${n(t.id)}"${a}>${n(t.name+r)}</option>`}).join(""),y(e))}function y(e="builtin-default"){if(!s.templateHint)return;let t=r.templates.find(t=>t.id===e);if(!t||t.is_builtin){s.templateHint.textContent="当前使用内置 LaTeX 模板；若上传 Word/PDF 格式说明，系统会提取规则并保留审查提示。";return}if("rules"===t.mode){let e=t.extracted_chars??0,a=t.rule_summary?` 摘要：${t.rule_summary.slice(0,180)}`:"";s.templateHint.textContent=`当前选择格式说明文档，已提取 ${e} 个字符；生成论文时仍使用内置 LaTeX 模板。${a}`;return}let a=t.placeholders?.length?t.placeholders.join("、"):"未记录";s.templateHint.textContent=`当前选择自定义 LaTeX 模板，占位符：${a}`}function f(e){if(r.llmSettings=e,s.apiKeyInput.value="",s.baseUrlInput.value=e.base_url||"https://api.chshapi.org/v1",s.modelInput.value=e.model||"gpt-5.5",s.workflowStrategyInput){let t=e.workflow_strategy_options?.length?e.workflow_strategy_options:[{id:"balanced",label:"均衡",summary:"速度和成功率兼顾"},{id:"stable",label:"稳妥",summary:"更多校验和自动修复"},{id:"turbo",label:"极速",summary:"并行读取附件和子问题"}];s.workflowStrategyInput.innerHTML=t.map(t=>{let a=t.id===(e.workflow_strategy||"balanced")?" selected":"";return`<option value="${n(t.id)}"${a}>${n(t.label)}：${n(t.summary)}</option>`}).join("")}if(s.workflowStrategyHint){let t=e.workflow_strategy_label||"均衡",a=e.workflow_strategy_summary||"速度和成功率兼顾。";s.workflowStrategyHint.textContent=`当前策略：${t}。${a}`}if(e.configured){let t="env"===e.source?"环境变量":"本地设置",a=e.workflow_strategy_label?` \xb7 ${e.workflow_strategy_label}`:"";s.llmSettingsStatus.textContent=`已配置：${e.masked_api_key} \xb7 ${t}${a}`}else s.llmSettingsStatus.textContent="尚未配置 API 密钥。"}async function h(){let e;r.projects=await p("/api/projects"),e=new Set((r.projects||[]).map(e=>e.id).filter(Boolean)),Array.from(r.selectedProjectIds).forEach(t=>{e.has(t)||r.selectedProjectIds.delete(t)}),S()}async function w(){if(s.autoJobCenter)try{let e=await p("/api/auto/jobs");r.autoJobs=e.auto_jobs||{},r.deliveryBatchJobs=e.delivery_batch_jobs||{},r.capacitySettings=e.capacity_settings||r.autoJobs.capacity_settings||r.deliveryBatchJobs.capacity_settings||null,r.capacityAutotune=e.capacity_autotune||r.capacityAutotune||null,F(r.autoJobs,r.deliveryBatchJobs)}catch(e){s.autoJobCenter.innerHTML=`<p class="status">后台任务中心暂不可用：${n(e.message)}</p>`}}async function $(){if(s.growthCenter)try{let e=await p("/api/product/growth");r.growthMetrics=e.growth||{},N(r.growthMetrics),e.trust&&s.trustCenter&&(r.trustMetrics=e.trust,O(r.trustMetrics))}catch(e){s.growthCenter.innerHTML=`<p class="status">解题进度中心暂不可用：${n(e.message)}</p>`}}async function v(){if(s.trustCenter)try{let e=await p("/api/product/trust");r.trustMetrics=e.trust||{},r.trustExports=e.trust_exports||null,r.repairCampaigns=e.repair_campaigns||null,O(r.trustMetrics,r.trustExports)}catch(e){s.trustCenter.innerHTML=`<p class="status">信任中心暂不可用：${n(e.message)}</p>`}}function S(){let e=r.projects||[],t=u(r.projectQuery),a=t?e.filter(e=>x(e).includes(t)):e,o=r.selectedProjectIds.size;if(s.projectCount&&(s.projectCount.textContent=e.length?t?`筛选出 ${a.length} / ${e.length} 个项目${o?` \xb7 已选 ${o}`:""}`:`${e.length} 个项目${o?` \xb7 已选 ${o}`:""}`:"暂无项目"),!e.length){s.projectList.innerHTML='<p class="status">暂无项目</p>',j();return}if(!a.length){s.projectList.innerHTML='<p class="status">没有匹配的项目。</p>',j(a);return}s.projectList.innerHTML=a.map(e=>{let t=r.currentProject?.metadata?.id===e.id?" is-active":"",a=e.auto_workflow_status?`<span class="project-badge">${n(e.auto_workflow_status)}</span>`:"",s=e.analysis_available?'<span class="project-badge project-badge-ok">已分析</span>':'<span class="project-badge project-badge-muted">未分析</span>',o=function(e={}){let t=e.delivery_readiness_status||"";if(!t)return"";let a=e.delivery_readiness_label||D(t),r=Number(e.delivery_readiness_score),s=Number.isFinite(r)?` ${r}分`:"",o=X(t),i=e.delivery_readiness_summary||a;return`<span class="project-badge${"success"===o?" project-badge-ok":"failed"===o?" project-badge-error":"pending"===o?" project-badge-muted":""}" title="${n(i)}">${n(a)}${n(s)}</span>`}(e),i=e.last_failure_diagnosis||{},l=i.category?`<span class="project-badge project-badge-error" title="${n(i.suggested_action||i.repair_focus||i.evidence||"")}">${n(i.label||i.category)}</span>`:"",c=e.status||"-",u=r.selectedProjectIds.has(e.id)?" checked":"",d=e.analysis_available?"":" disabled";return`
        <article class="project-row${t}">
          <label class="project-select">
            <input class="project-select-input" type="checkbox" data-project-id="${n(e.id)}"${u}${d} />
            <span class="sr-only">选择${n(e.name||e.id)}</span>
          </label>
          <button class="project-button project-open${t}" type="button" data-project-id="${n(e.id)}">
            <span class="project-name">${n(e.name)}</span>
            <span class="project-meta">${n(L(e.created_at))} \xb7 ${n(c)}</span>
            <span class="project-badges">${s}${a}${o}${l}</span>
          </button>
        </article>
      `}).join(""),j(a),s.projectList.querySelectorAll(".project-open").forEach(e=>{e.addEventListener("click",()=>A(e.dataset.projectId))})}function j(e=null){let t=r.selectedProjectIds.size,a=(Array.isArray(e)?e:k()).filter(e=>e.analysis_available).length;s.batchStartProjects&&(s.batchStartProjects.disabled=0===t,s.batchStartProjects.textContent=t?`批量入队 ${t}`:"批量入队"),s.clearProjectSelection&&(s.clearProjectSelection.disabled=0===t),s.selectAnalyzedProjects&&(s.selectAnalyzedProjects.disabled=0===a,s.selectAnalyzedProjects.textContent=a?`选择已分析 ${a}`:"选择已分析")}function k(){let e=r.projects||[],t=u(r.projectQuery);return t?e.filter(e=>x(e).includes(t)):e}async function C(){let e=Array.from(r.selectedProjectIds);if(!e.length){s.batchProjectStatus.textContent="请先选择已分析项目。";return}s.batchStartProjects.disabled=!0,s.selectAnalyzedProjects.disabled=!0,s.clearProjectSelection.disabled=!0,s.batchProjectStatus.textContent=`正在将 ${e.length} 个项目加入后台任务池。`;try{let t=await p("/api/auto/batch/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_ids:e,mode:"auto"})}),a=t.batch||{},n=Array.isArray(a.submitted)?a.submitted:[];n.forEach(e=>{e.project_id&&r.selectedProjectIds.delete(e.project_id)}),t.auto_jobs?(r.autoJobs=t.auto_jobs,F(r.autoJobs,r.deliveryBatchJobs)):await w(),await h(),await $(),await v();let o=Array.isArray(a.skipped)?a.skipped:[],i=o.length?`，跳过 ${o.length} 个：${o.slice(0,2).map(e=>e.reason||e.project_id).join("；")}${o.length>2?"…":""}`:"";s.batchProjectStatus.textContent=`批量入队完成：${a.submitted_count||n.length} 个进入任务池${i}。`,d("批量任务已提交后台任务池","success")}catch(e){s.batchProjectStatus.textContent=`批量入队失败：${e.message}`,d(`批量入队失败：${e.message}`,"error")}finally{j()}}function x(e={}){return u([e.id,e.name,e.original_name,e.created_at,e.status,e.auto_workflow_status,e.performance_health_label,e.performance_health_summary,e.repair_center_label,e.repair_center_summary,e.repair_center_action,e.delivery_readiness_label,e.delivery_readiness_summary,e.delivery_readiness_action,e.delivery_package_summary,e.delivery_package_sha256,e.last_failure_diagnosis?.label,e.last_failure_diagnosis?.category,e.last_failure_diagnosis?.repair_focus,e.last_failure_diagnosis?.suggested_action,e.analysis_available?"已分析":"未分析"].filter(Boolean).join(" "))}function L(e){return e?String(e).replace("T"," ").slice(0,16):"-"}function P(e){let t=["B","KB","MB","GB"],a=Number(e)||0;for(let e of t){if(a<1024||e===t[t.length-1])return"B"===e?`${Math.round(a)} B`:`${a.toFixed(1)} ${e}`;a/=1024}return`${a.toFixed(1)} GB`}async function A(e){q(await p(`/api/projects/${e}`)),d("已打开项目","success")}function q(e){var t;let a,i;r.currentProject=e,r.repairBriefing=e.repair||null,r.deliveryReadiness=e.delivery||null,r.deliveryPackage=e.package||null,a=r.currentProject?.metadata?.id,s.projectList.querySelectorAll(".project-button").forEach(e=>{e.classList.toggle("is-active",e.dataset.projectId===a)});let{metadata:l,analysis:c}=e;s.title.textContent=l.name||l.original_name||"项目",s.openProjectRoot&&(s.openProjectRoot.classList.remove("hidden"),s.openProjectRoot.disabled=!1);let u=l.last_failure_diagnosis||{},d=u.category?` \xb7 诊断：${u.label||u.category}`:"";if(s.projectStatus.textContent=l.auto_workflow_status?`${l.status||"-"} \xb7 自动流程：${l.auto_workflow_status}${d}`:`${l.status||"-"}${d}`,!c){s.empty.classList.remove("hidden"),s.analysisView.classList.add("hidden"),eo(s.uploadProgress,l.analysis_progress,7);return}s.empty.classList.add("hidden"),s.analysisView.classList.remove("hidden");let p=function(e,t){let a=e.final_problem||{},r=t.recommended_problem||{},s=a.id||a.final_problem_id;if(s&&"Unknown"!==s){let e=(t.problems||[]).find(e=>e.id===s)||{};return{...e,...r,...a,id:s,title:a.title||a.final_problem_title||e.title||r.title||""}}return r}(l,c),m=(t=l,"user"===(i=t.final_problem?.source)?"用户选择":i?"流程选择":"系统推荐");s.recommended.textContent=`${m} ${p.id||"-"} 题：${p.title||""}`,s.documentCount.textContent=c.contest_summary?.document_count??"-",s.dataCount.textContent=c.contest_summary?.data_count??"-";let _=c.system_recommended_problem||c.recommended_problem||{},g=T(l);(function(e,t,a=""){if(!e.length){s.problemCards.innerHTML='<p class="status">尚未生成选题分析。</p>';return}s.problemCards.innerHTML=e.map(e=>{let r=e.id===t?" selected":"",s=e.id===a,o=(e.tasks||[]).slice(0,3).map(e=>`<li>${n(e)}</li>`).join(""),i=G(e.model_types,"is-muted"),l=G(e.suggested_methods),c=G(e.risk_items,"is-risk"),u=e.id===t?" disabled":"",d=e.id===t?"已选择":"选择此题";return`
        <article class="problem-card${r}">
          <div class="problem-head">
            <div class="problem-title">
              <h3>${n(e.id)} 题</h3>
              <p class="problem-subtitle">${n(e.title)}</p>
            </div>
            <div class="problem-badges">
              ${e.id===t?'<span class="selection-badge">已选择</span>':""}
              ${s?'<span class="recommend-badge">系统推荐</span>':""}
            </div>
          </div>
          <div class="chip-row">
            <span class="problem-score">综合得分 ${n(e.fit_score)}</span>
            <span class="chip is-muted">AI适配 ${n(e.ai_fit||"-")}</span>
            <span class="chip is-muted">可行性 ${n(e.feasibility||"-")}</span>
          </div>
          ${function(e={}){let t=[["data","数据",25],["task","任务",25],["model","模型",20],["computation","计算",20],["paper","论文",20]].filter(([t])=>void 0!==e[t]&&null!==e[t]).map(([t,a,r])=>{let s=Number(e[t])||0,o=Math.max(0,Math.min(100,s/r*100));return`
        <div class="score-breakdown-row">
          <span>${n(a)}</span>
          <span class="score-track"><i style="width: ${o}%"></i></span>
          <strong>${n(s)}</strong>
        </div>
      `}).join("");if(!t)return"";let a=void 0!==e.risk_penalty?`<span>风险扣分 ${n(e.risk_penalty)}</span>`:"";return`
    <div class="score-breakdown">
      ${t}
      ${a?`<div class="score-risk">${a}</div>`:""}
    </div>
  `}(e.score_breakdown)}
          ${i?`<div class="chip-row">${i}</div>`:""}
          ${l?`<div class="chip-row">${l}</div>`:""}
          ${c?`<div class="chip-row">${c}</div>`:""}
          ${o?`<ul class="problem-meta">${o}</ul>`:""}
          <button class="select-problem-button" type="button" data-problem-id="${n(e.id)}"${u}>${d}</button>
        </article>
      `}).join(""),s.problemCards.querySelectorAll(".select-problem-button").forEach(e=>{e.addEventListener("click",()=>K(e.dataset.problemId))}),s.problemSelectionStatus&&(s.problemSelectionStatus.textContent=t?`当前后续自动解题与论文生成将使用 ${t} 题。`:"请先选择一个题目，再运行一键自动流程。")})(c.problems||[],g,_.id),function(e,t=null){if(!e.length){s.workflow.innerHTML='<p class="status">尚未生成工作流。</p>';return}s.workflow.innerHTML=e.map((e,a)=>{let r=0===a&&t?.id&&"Unknown"!==t.id?`确认选择 ${t.id} 题：${t.title||""}`:e.output;return`
        <div class="workflow-step">
          <span class="workflow-index">${a+1}</span>
          <strong>${n(e.stage)}</strong>
          <span>${n(e.owner)}</span>
          <span>${n(r)}</span>
        </div>
      `}).join("")}(c.workflow||[],p),function(e){if(!e.length){s.inventory.innerHTML='<p class="status">没有解析到文件</p>';return}s.inventory.innerHTML=e.map(e=>{let t=e.schema?function(e){if("csv"===e.type)return`${e.rows??"-"} 行 \xb7 ${e.cols??"-"} 列`;if("excel"===e.type){let t=e.sheets||[];return`${t.length} 个工作表`}return"已解析"}(e.schema):`${Math.round(e.size/1024)} KB`;return`
        <div class="inventory-item">
          <span class="pill">${n(e.kind)}</span>
          <span class="file-path">${n(e.path)}</span>
          <span class="inventory-size">${n(t)}</span>
        </div>
      `}).join("")}(c.inventory||[]),function(e,t){if(!s.statusCards)return;let a=function(e={}){if(!e||"object"!=typeof e||!e.category)return"";let t=e.label||e.category,a=e.repair_focus||e.suggested_action||"可在自动流程进度中查看修复重点";return`${t}：${a}`}(e.last_failure_diagnosis||{}),r=function(e={}){let t=e.performance_health_scores||{},a=e.performance_health_metrics||{},r=[],s=e.performance_health_score??t.overall,n=t.speed??a.speed,o=t.reliability??a.reliability;return Number.isFinite(Number(n))&&r.push(["速度",`${Number(n)}`]),Number.isFinite(Number(o))&&r.push(["可靠",`${Number(o)}`]),Number(a.attachment_workers)>0&&r.push(["线程",`${Number(a.attachment_workers)}`]),Number(a.planned_task_count)>0&&r.push(["任务",`${Number(a.planned_task_count)}`]),{badge:Number.isFinite(Number(s))?`${Number(s)} 分`:"",items:r.slice(0,4)}}(e),o=[{title:"赛题解析",value:t?"已完成":"等待",detail:`${t?.problems?.length||0} 个候选题，${t?.inventory?.length||0} 个材料文件`,status:t?"success":"pending"},{title:"LLM 分析",value:D(e.llm_analysis_status),detail:"requires_api_key"===e.llm_analysis_status?"需要先填写 API 密钥":"选题和建模建议",status:X(e.llm_analysis_status)},{title:"自动解题",value:D(e.auto_workflow_status),detail:a||e.auto_workflow_mode||"LLM+代码一键流程",status:X(e.auto_workflow_status)},{title:"修复中心",value:e.repair_center_label||D(e.repair_center_status),detail:e.repair_center_summary||"失败诊断、证据和续跑入口",status:X(e.repair_center_status)},{title:"模型辅助",value:D(e.model_assistant_status),detail:"自定义模型补充和过程记录",status:X(e.model_assistant_status)},{title:"代码求解",value:D(e.computed_solution_status),detail:a&&"failed"===e.computed_solution_status?a:"结果表、图片和 manifest",status:X(e.computed_solution_status)},{title:"性能健康",value:e.performance_health_label||D(e.performance_health_status),detail:e.performance_health_summary||"速度、并发和自动修复指标",status:X(e.performance_health_status),badge:r.badge,metrics:r.items},{title:"交付就绪",value:e.delivery_readiness_label||D(e.delivery_readiness_status),detail:e.delivery_readiness_summary||"论文、结果、审查和支撑包",status:X(e.delivery_readiness_status),badge:Number.isFinite(Number(e.delivery_readiness_score))?`${Number(e.delivery_readiness_score)} 分`:""},{title:"LaTeX 编译",value:D(e.compile_status),detail:"生成 paper/main.pdf",status:X(e.compile_status)},{title:"论文审查",value:D(e.paper_review_status),detail:"结构、图表、页数和可追溯性",status:X(e.paper_review_status)}];s.statusCards.innerHTML=o.map(e=>`
        <article class="status-card" data-status="${e.status}">
          <span class="status-dot"></span>
          <div>
            <div class="status-card-head">
              <h3>${n(e.title)}</h3>
              ${e.badge?`<span class="status-card-badge">${n(e.badge)}</span>`:""}
            </div>
            <strong>${n(e.value)}</strong>
            <p>${n(e.detail)}</p>
            ${function(e=[]){return e.length?`
    <div class="status-card-metrics">
      ${e.map(([e,t])=>`
            <span class="status-card-metric">
              <b>${n(e)}</b>
              <strong>${n(t)}</strong>
            </span>
          `).join("")}
    </div>
  `:""}(e.metrics||[])}
          </div>
        </article>
      `).join("")}(l,c),function(e){let t=e.paper_options||{};if(b(t.template_id||"builtin-default"),s.targetBodyPages&&(s.targetBodyPages.value=t.target_body_pages||""),s.paperOptionsStatus){let e=t.target_body_pages?`${t.target_body_pages} 页`:"未设置";s.paperOptionsStatus.textContent=`当前正文目标：${e}`}}(l),function(e,t=null){let a=t||e.recommended_problem||{},r=a.tasks||[],o=`${a.id||"推荐题"}：${a.title||"整体问题"}`,i=[`<option value="${n(o)}">${n(o)}</option>`];r.forEach((e,t)=>{let a=`问题 ${t+1}：${e}`;i.push(`<option value="${n(a)}">${n(a)}</option>`)}),s.assistProblemSelect.innerHTML=i.join("")}(c,p),function(e={},t="",a={}){if(!s.repairCenter)return;let r=a&&"object"==typeof a?a:{},i=r.status||e.repair_center_status||"",l=r.label||e.repair_center_label||D(i),c=r.summary||e.repair_center_summary||"尚未生成修复简报。",u=r.latest_failure_diagnosis||e.last_failure_diagnosis||{},d=function(e={},t={}){let a=t.primary_action&&"object"==typeof t.primary_action?t.primary_action:{};if(a.id)return a;let r=Array.isArray(t.actions)?t.actions:[];if(r[0]?.id)return r[0];let s=e.repair_center_action||"";return s?{id:s,label:({resume_auto_workflow:"继续生成并自动修复",inspect_failure_evidence:"查看失败证据",refresh_diagnostics:"刷新诊断与并行计划",start_auto_workflow:"启动一键自动流程",fix_completeness_gate:"补齐完整性门禁",continue_review:"继续编译和审查"})[s]||s,priority:"medium"}:{}}(e,r),p=function(e={},t="",a={}){let r=function(e=""){return"resume_auto_workflow"===e||"fix_completeness_gate"===e?"resume":"start_auto_workflow"===e?"start":"refresh_diagnostics"===e?"diagnostics":"inspect_failure_evidence"===e||"continue_review"===e?"open_report":""}(e.id);if(!r||!t)return"";let s=a.artifacts||{};return"open_report"!==r||s.repair_briefing||s.repair_briefing_json||s.computed_solver_repair?`<button class="repair-action" type="button" data-repair-action="${n(r)}">${n(e.label||"处理")}</button>`:""}(d,t,e),m=Array.isArray(r.evidence)&&r.evidence.length?r.evidence:function(e={},t={}){let a=[];return t?.category&&a.push({label:t.label||t.category,detail:t.repair_focus||t.suggested_action||t.evidence||"",source:"last_failure_diagnosis"}),[["自动流程",e.auto_workflow_status],["代码求解",e.computed_solution_status],["性能健康",e.performance_health_label||e.performance_health_status],["论文回填",e.paper_fill_status],["LaTeX",e.compile_status]].forEach(([e,t])=>{t&&a.push({label:e,detail:t,source:"metadata/status"})}),a}(e,u),_=m.length?m.slice(0,8).map(R).join(""):'<p class="status">暂无阻断证据。</p>',g=function(e={},t=""){let a=e.artifacts||{},r=[["repair_briefing","修复简报"],["repair_briefing_json","修复 JSON"],["performance_health","性能健康"],["computed_solver_repair","自动修复记录"],["computed_solver_log","代码日志"]].filter(([e])=>t&&a[e]).map(([e,r])=>{let s=a[e];return`<a href="/api/projects/${encodeURIComponent(t)}/download/${o(s)}" target="_blank" rel="noreferrer">${n(r)}</a>`});return r.length?`<div class="repair-links">${r.join("")}</div>`:""}(e,t),b=r.generated_at?`<span>更新 ${n(L(r.generated_at))}</span>`:"",y=e.repair_center_can_resume?"可继续生成":i?"当前无需续跑":"需先刷新诊断";s.repairCenter.innerHTML=`
    <div class="repair-head" data-status="${n(X(i))}">
      <span class="repair-status-dot"></span>
      <div>
        <strong>${n(l||"未开始")}</strong>
        <p>${n(c)}</p>
      </div>
      ${p}
    </div>
    <div class="repair-meta">
      <span>${n(y)}</span>
      ${d?.label?`<span>${n(d.label)}</span>`:""}
      ${b}
    </div>
    <div class="repair-evidence">
      ${_}
    </div>
    ${g}
  `}(l,c.project?.id||l.id,e.repair||{}),function(e={},t="",a={}){if(!s.deliveryCenter)return;let r=a&&"object"==typeof a?a:{},i=r.status||e.delivery_readiness_status||"",l=r.label||e.delivery_readiness_label||D(i),c=r.score??e.delivery_readiness_score,u=r.summary||e.delivery_readiness_summary||"尚未生成交付就绪报告。",d=Array.isArray(r.checks)?r.checks:function(e={}){return[{label:"代码结果",status:"success"===e.computed_solution_status?"pass":"fail",detail:D(e.computed_solution_status),required:!0},{label:"论文回填",status:"success"===e.paper_fill_status?"pass":"warning",detail:D(e.paper_fill_status),required:!1},{label:"LaTeX 编译",status:"success"===e.compile_status?"pass":"fail",detail:D(e.compile_status),required:!0},{label:"论文审查",status:"success"===e.paper_review_status?"pass":"warning",detail:D(e.paper_review_status),required:!1}]}(e),p=function(e={},t={},a=[]){let r=t.primary_action&&"object"==typeof t.primary_action?t.primary_action:{};if(r.id)return r;let s=Array.isArray(t.actions)?t.actions:[];if(s[0]?.id)return s[0];let n=e.delivery_readiness_action||"",o={resume_auto_workflow:"继续生成并自动修复",analyze_project:"重建赛题分析",run_auto_workflow:"启动一键自动流程",compile_latex:"编译 PDF/Word",review_paper:"审查论文",refresh_diagnostics:"刷新诊断/性能",refresh_repair:"刷新修复中心",build_delivery_package:"生成正式交付包",download_support_zip:"下载支撑材料包"};if(n)return{id:n,label:o[n]||n,priority:"medium"};let i=a.find(e=>"fail"===e.status||"warning"===e.status);return i?.action?{id:i.action,label:o[i.action]||i.action,priority:i.required?"high":"medium"}:{}}(e,r,d),m=function(e={},t=""){let a=function(e=""){return({resume_auto_workflow:"resume",analyze_project:"analyze",run_auto_workflow:"start",compile_latex:"compile",review_paper:"review",refresh_diagnostics:"diagnostics",refresh_repair:"repair",build_delivery_package:"package",download_support_zip:"support_zip"})[e]||""}(e.id);return a&&t?`<button class="delivery-action" type="button" data-delivery-action="${n(a)}">${n(e.label||"处理")}</button>`:""}(p,t),_=d.length?d.slice(0,10).map(M).join(""):'<p class="status">暂无交付检查项。</p>',g=Array.isArray(r.required_missing)?r.required_missing:d.filter(e=>e.required&&"fail"===e.status),b=g.length?`${g.length} 个必需项缺失`:r.can_submit||e.delivery_readiness_can_submit?"可提交":"等待检查",y=function(e={},t=""){let a=e.artifacts||{},r=[["delivery_readiness","交付报告"],["delivery_readiness_json","交付 JSON"],["delivery_package","正式交付包"],["delivery_package_manifest","交付包清单"],["delivery_package_manifest_json","交付包 JSON"],["paper_pdf","论文 PDF"],["paper_docx","论文 Word"],["paper_review","审查报告"],["support_zip","支撑材料包"]].filter(([e])=>t&&("support_zip"===e||a[e])).map(([e,r])=>{let s="support_zip"===e?"support.zip":a[e];return`<a href="/api/projects/${encodeURIComponent(t)}/download/${o(s)}" target="_blank" rel="noreferrer">${n(r)}</a>`});return r.length?`<div class="delivery-links">${r.join("")}</div>`:""}(e,t),f=r.generated_at?`<span>更新 ${n(L(r.generated_at))}</span>`:"";s.deliveryCenter.innerHTML=`
    <div class="delivery-head" data-status="${n(X(i))}">
      <span class="delivery-score">${Number.isFinite(Number(c))?n(Number(c)):"--"}</span>
      <div>
        <strong>${n(l||"未检查")}</strong>
        <p>${n(u)}</p>
      </div>
      ${m}
    </div>
    <div class="delivery-meta">
      <span>${n(b)}</span>
      ${p?.label?`<span>${n(p.label)}</span>`:""}
      ${f}
    </div>
    <div class="delivery-checks">
      ${_}
    </div>
    ${y}
  `}(l,c.project?.id||l.id,e.delivery||{}),function(e,t){let a=e.artifacts||{},r=[["analysis_report","分析报告"],["outline","论文提纲"],["model_plan","模型计划"],["latex_skeleton","LaTeX 骨架"],["modeling_script","建模脚本"],["modeling_log","建模日志"],["modeling_manifest","结果清单"],["baseline_summary","基线结果摘要"],["specialized_script","专项脚本"],["specialized_log","专项日志"],["specialized_manifest","专项结果清单"],["specialized_summary","专项结果摘要"],["material_passport","材料护照"],["attachment_profile","并发附件画像"],["attachment_profile_json","并发附件画像 JSON"],["parallel_task_plan","并行求解任务计划"],["parallel_task_plan_json","并行求解任务计划 JSON"],["llm_problem_structure","LLM 赛题结构增强"],["llm_problem_analysis","LLM 赛题分析"],["llm_baseline_review","LLM 基线复盘"],["llm_specialized_review","LLM 专项复盘"],["llm_model_assistant","LLM 模型辅助"],["llm_model_assistant_history","LLM 模型辅助历史"],["llm_full_solution","LLM 全流程题解"],["llm_paper_latex","LLM LaTeX 生成记录"],["computed_solver_spec","LLM 代码求解规范"],["computed_solver_script","代码求解脚本"],["computed_solver_repair","代码求解自动修复记录"],["computed_solver_log","代码运行日志"],["computed_solution_status","代码运行状态 JSON"],["computed_completeness","代码求解完整性检查"],["computed_manifest","代码计算结果清单"],["computed_summary","代码计算结果摘要"],["computed_result_prose","结果整合说明"],["performance_health","性能与修复健康报告"],["repair_briefing","自动修复中心"],["delivery_readiness","交付就绪报告"],["delivery_package","正式交付包"],["delivery_package_manifest","交付包清单"],["paper_result_filled","结果整合论文 LaTeX"],["auto_workflow_report","自动解题报告"],["auto_workflow_report_json","自动解题 JSON"],["backend_skill_research","GitHub 技能库与诚信门禁报告"],["backend_skill_research_json","GitHub 技能库与诚信门禁 JSON"],["code_graph_report","代码图谱报告"],["code_graph_json","代码图谱 JSON"],["paper_autofilled","回填论文 LaTeX"],["paper_llm","LLM 论文 LaTeX"],["paper_fill_summary","回填摘要"],["format_rules_summary","格式规则摘要"],["paper_pdf","论文 PDF"],["paper_docx","论文 Word"],["latex_log","编译日志"],["word_export_log","Word 导出日志"],["paper_review","论文审查报告"],["paper_review_json","论文审查 JSON"],["material_passport_json","材料护照 JSON"],["llm_problem_structure_json","LLM 赛题结构增强 JSON"],["llm_problem_analysis_json","LLM 赛题分析 JSON"],["llm_baseline_review_json","LLM 基线复盘 JSON"],["llm_specialized_review_json","LLM 专项复盘 JSON"],["llm_model_assistant_json","LLM 模型辅助 JSON"],["llm_model_assistant_history_json","LLM 模型辅助历史 JSON"],["llm_full_solution_json","LLM 全流程题解 JSON"],["llm_paper_latex_json","LLM LaTeX 生成 JSON"],["computed_solver_spec_json","LLM 代码求解规范 JSON"],["computed_solver_script_json","代码求解脚本 JSON"],["computed_solver_repair_json","代码求解自动修复 JSON"],["computed_completeness_json","代码求解完整性检查 JSON"],["computed_result_prose_json","结果整合说明 JSON"],["performance_health_json","性能与修复健康 JSON"],["repair_briefing_json","自动修复中心 JSON"],["delivery_readiness_json","交付就绪 JSON"],["delivery_package_manifest_json","交付包 JSON"]].filter(([e])=>a[e]).map(([e,t])=>[e,t,a[e]]);if(r.push(["support_zip","支撑材料包","support.zip"]),!r.length){s.artifacts.innerHTML='<p class="status">暂无生成文件。</p>';return}let i=new Map;r.forEach(([e,t,a])=>{var r,s;let n,o=(r=e,s=a,(n=`${r||""} ${s||""}`.toLowerCase()).includes("code_graph")||n.includes("call_graph")?"代码与求解":n.includes("paper")||n.includes("latex")||n.endsWith(".pdf")||n.endsWith(".tex")||n.endsWith(".docx")?"论文文件":n.includes("report")||n.includes("analysis")||n.includes("review")||n.includes("skill")||n.includes("health")||n.includes("repair_briefing")||n.includes("delivery_readiness")||n.includes("passport")||n.includes("attachment_profile")?"分析报告":n.includes("script")||n.includes("solver")||n.includes("parallel_task_plan")||n.endsWith(".py")?"代码与求解":n.includes("manifest")||n.includes("summary")||n.endsWith(".json")||n.endsWith(".csv")||n.endsWith(".xlsx")?"数据结果":n.includes("support")||n.endsWith(".zip")||n.includes("log")?"支撑材料":"其他文件");i.has(o)||i.set(o,[]),i.get(o).push([e,t,a])}),s.artifacts.innerHTML=Array.from(i.entries()).map(([e,a])=>{let r=a.map(([e,a,r])=>{var s,i,l,c,u,d;let p,m,_,g,b;return s=t,i=e,l=a,c=r,p=encodeURIComponent(s),m=o(c),_=n(l),g=n(c),`
    <div class="artifact-row">
      <a class="artifact-link" data-kind="${u=i,d=c,(b=`${u||""} ${d||""}`.toLowerCase()).endsWith(".pdf")||b.includes("paper_pdf")?"pdf":b.endsWith(".docx")||b.includes("paper_docx")?"docx":b.endsWith(".tex")||b.includes("latex")||b.includes("paper_")?"tex":b.endsWith(".py")||b.includes("script")||b.includes("solver")||b.includes("code_graph")?"code":b.endsWith(".json")||b.endsWith(".csv")||b.endsWith(".xlsx")||b.includes("manifest")?"data":"file"}" href="/api/projects/${p}/download/${m}" title="${g}" aria-label="下载或查看${_}">${_}</a>
      <button class="artifact-open" type="button" data-project-id="${n(s)}" data-path="${g}" title="在资源管理器中打开所在位置" aria-label="打开${_}所在文件夹">打开位置</button>
    </div>
  `}).join("");return`
        <section class="artifact-group">
          <h3>${n(e)}</h3>
          <div class="artifact-list">${r}</div>
        </section>
      `}).join("")}(l,c.project?.id||l.id),es(l.auto_workflow_progress),en(l.auto_workflow_status,l.auto_workflow_progress||{}),Z(l.model_assistant_progress),eo(s.uploadProgress,l.analysis_progress,7)}function T(e){let t=e.final_problem||{};return t.id||t.final_problem_id||""}function R(e={}){return`
    <div class="repair-evidence-row">
      <b>${n(e.label||e.source||"证据")}</b>
      <span>${n(e.detail||"-")}</span>
    </div>
  `}function M(e={}){return`
    <div class="delivery-check-row" data-status="${n(X(e.status))}">
      <span></span>
      <div>
        <b>${n(e.label||e.id||"检查项")}</b>
        <small>${n(e.required?"必需":"建议")} \xb7 ${n(D(e.status))}</small>
        <p>${n(e.detail||"-")}</p>
      </div>
    </div>
  `}function N(e={}){if(!s.growthCenter)return;let t=Array.isArray(e.metrics)?e.metrics:[],a=Array.isArray(e.funnel)?e.funnel:[],r=Array.isArray(e.signals)?e.signals:[],o=e.recommended_action||{},i=function(e={}){return"batch_delivery_packages"===(e.command||"")||"build_packages"===e.id?"batch_packages":""}(o),l=e.delivery_batch||{},c=e.workflow||{},u=e.generated_at?`<span>更新 ${n(L(e.generated_at))}</span>`:"";s.growthCenter.innerHTML=`
    <section class="growth-hero" data-status="${n(X(e.status))}">
      <div>
        <strong>${n(e.label||"解题待命")}</strong>
        <p>${n(e.summary||"上传赛题后会汇总分析、求解、交付和打包进度。")}</p>
      </div>
      ${u}
    </section>
    <div class="growth-metrics">
      ${t.length?t.map(I).join(""):'<p class="status">暂无解题指标。</p>'}
    </div>
    <div class="growth-funnel">
      ${a.length?a.map(E).join(""):""}
    </div>
    ${function(e={}){if(!e.id)return"";let t=Number(e.packaged_count)||0,a=Number(e.skipped_count)||0,r=Number(e.failed_count)||0,s=Number(e.requested_count)||0,o=B(e.duration_seconds||0),i=Number(e.total_package_bytes)||0,l=i?` \xb7 ${P(i)}`:"",c=e.generated_at?` \xb7 ${L(e.generated_at)}`:"";return`
    <article class="growth-batch" data-status="${n(r?"failed":t?"success":"warning")}">
      <div>
        <b>最近批量交付包</b>
        <span>${n(`请求 ${s} \xb7 生成 ${t} \xb7 跳过 ${a} \xb7 失败 ${r}`)}</span>
      </div>
      <p>${n(`并发 ${e.max_workers||0} \xb7 耗时 ${o}${l}${c}`)}</p>
    </article>
  `}(l)}
    ${function(e={}){if(!e||!e.stage)return"";let t=Array.isArray(e.proof_points)?e.proof_points:[],a=Array.isArray(e.risks)?e.risks:[],r=Array.isArray(e.actions)?e.actions:[],s=Number(e.solution_assets)||0,o=Number(e.package_count)||0,i=Number(e.estimated_hours_saved)||0;return`
    <section class="growth-workflow" data-status="${n(X(e.stage))}">
      <div class="growth-workflow-head">
        <div>
          <b>${n(e.label||"解题准备度")}</b>
          <p>${n(e.summary||"")}</p>
        </div>
        <strong>${n(e.score??0)}/100</strong>
      </div>
      <div class="growth-workflow-metrics">
        <span><b>解题资产</b><strong>${n(s)}</strong></span>
        <span><b>正式交付包</b><strong>${n(o)}</strong></span>
        <span><b>节省工时</b><strong>${n(i?`${i.toFixed(1)}h`:"-")}</strong></span>
      </div>
      ${t.length?`<div class="growth-workflow-proof">${t.map(e=>`<span>${n(e)}</span>`).join("")}</div>`:""}
      ${a.length?`<ul class="growth-workflow-risks">${a.map(e=>`<li>${n(e)}</li>`).join("")}</ul>`:""}
      ${r.length?`<div class="growth-workflow-actions">${r.map(e=>`
        <article>
          <b>${n(e.label||e.id||"动作")}</b>
          <p>${n(e.detail||"")}</p>
        </article>
      `).join("")}</div>`:""}
    </section>
  `}(c)}
    <div class="growth-footer">
      ${o.label?`
        <div class="growth-action">
          <div>
            <b>${n(o.label)}</b>
            <span>${n(o.detail||"")}</span>
          </div>
          ${i?`<button class="growth-action-button" type="button" data-growth-action="${n(i)}">${n(o.label)}</button>`:""}
        </div>
      `:""}
      ${r.length?`<div class="growth-signals">${r.map(e=>`<span>${n(e)}</span>`).join("")}</div>`:""}
    </div>
  `}function I(e={}){return`
    <article class="growth-metric" data-status="${n(X(e.status))}">
      <span></span>
      <div>
        <b>${n(e.label||e.id||"指标")}</b>
        <strong>${n(e.value??"-")}</strong>
        <p>${n(e.detail||"")}</p>
      </div>
    </article>
  `}function E(e={}){let t=Math.max(0,Math.min(100,Number(e.conversion)||0));return`
    <article class="growth-funnel-row">
      <div>
        <b>${n(e.label||e.id||"阶段")}</b>
        <span>${n(e.count??0)} \xb7 ${t}%</span>
      </div>
      <div class="growth-funnel-track"><i style="width: ${t}%"></i></div>
      <p>${n(e.detail||"")}</p>
    </article>
  `}function O(e={},t=null){if(!s.trustCenter)return;let a=(t||r.trustExports||{}).latest||{},o=(r.repairCampaigns||{}).latest||{},i=Array.isArray(e.metrics)?e.metrics:[],l=Array.isArray(e.sla)?e.sla:[],c=Array.isArray(e.evidence)?e.evidence:[],u=Array.isArray(e.incidents)?e.incidents:[],d=Array.isArray(e.actions)?e.actions:[],p=e.generated_at?`<span>${n(L(e.generated_at))}</span>`:"";s.trustCenter.innerHTML=`
    <section class="trust-hero" data-status="${n(X(e.status))}">
      <div>
        <b>${n(e.label||"信任中心")}</b>
        <p>${n(e.summary||"项目运行后会在这里汇总质量、交付和可审计证据。")}</p>
      </div>
      <strong>${n(e.score??0)}/100</strong>
      ${p}
    </section>
    ${function(e={}){let t=!!(e&&e.download_url),a=e.size?` \xb7 ${e.size}`:"",r=e.sha256?` \xb7 SHA256 ${String(e.sha256).slice(0,12)}`:"",s=t?`最近 ${L(e.generated_at)} \xb7 评分 ${e.trust_score??"-"}${a}${r}`:"尚未导出审计包。";return`
    <section class="trust-export">
      <div>
        <b>审计包</b>
        <p>${n(s)}</p>
      </div>
      <div class="trust-export-actions">
        <button class="trust-export-button" type="button" data-trust-action="export_audit">导出审计包</button>
        ${t?`<a class="trust-export-link" href="${n(e.download_url)}" target="_blank" rel="noreferrer">下载最新包</a>`:""}
      </div>
    </section>
  `}(a)}
    ${function(e={}){let t=e&&e.id?`最近 ${L(e.generated_at)} \xb7 ${e.summary||`${e.queued||0} 个已入队，${e.briefed||0} 个已重建简报`}`:"尚未运行修复行动。";return`
    <section class="trust-campaign">
      <div>
        <b>修复行动</b>
        <p>${n(t)}</p>
      </div>
      <div class="trust-campaign-actions">
        <button class="trust-campaign-button" type="button" data-trust-action="repair_campaign">运行修复行动</button>
      </div>
    </section>
  `}(o)}
    <div class="trust-metrics">
      ${i.length?i.map(J).join(""):'<p class="status">暂无信任指标。</p>'}
    </div>
    <div class="trust-sla">
      ${l.length?l.map(W).join(""):""}
    </div>
    <div class="trust-grid">
      ${z("证据",c,"evidence")}
      ${z("异常",u,"incident")}
    </div>
    ${d.length?`<div class="trust-actions">${d.map(U).join("")}</div>`:""}
  `}function J(e={}){return`
    <article class="trust-metric" data-status="${n(X(e.status))}">
      <b>${n(e.label||e.id||"指标")}</b>
      <strong>${n(e.value??"-")}</strong>
      <p>${n(e.detail||"")}</p>
    </article>
  `}function W(e={}){let t=Number.isFinite(Number(e.value))?Math.max(0,Math.min(100,Number(e.value))):0,a=Number.isFinite(Number(e.value))?`${Math.round(t)}%`:"-";return`
    <article class="trust-sla-row" data-status="${n(X(e.status))}">
      <div>
        <b>${n(e.label||e.id||"SLA")}</b>
        <span>${n(a)} / 目标 ${n(e.target??"-")}%</span>
      </div>
      <div class="trust-sla-track"><i style="width: ${t}%"></i></div>
      <p>${n(e.detail||"")}</p>
    </article>
  `}function z(e,t=[],a="evidence"){return`
    <section class="trust-list trust-list-${n(a)}">
      <b>${n(e)}</b>
      ${t.length?t.map(e=>`
            <article data-status="${n(X(e.status))}">
              <strong>${n(e.label||e.id||"-")}</strong>
              <p>${n(e.detail||"")}</p>
            </article>
          `).join(""):`<p class="status">${"incident"===a?"暂无活跃异常。":"暂无证据。"}</p>`}
    </section>
  `}function U(e={}){return`
    <article>
      <b>${n(e.label||e.id||"动作")}</b>
      <p>${n(e.detail||"")}</p>
    </article>
  `}function F(e={},t={}){if(!s.autoJobCenter)return;let a=Array.isArray(e.jobs)?e.jobs.map(e=>({...e,kind:e.kind||"auto_workflow"})):[],o=[...Array.isArray(t.jobs)?t.jobs.map(e=>({...e,kind:"delivery_batch"})):[],...a].sort((e,t)=>String(t.submitted_at||"").localeCompare(String(e.submitted_at||""))),i=e.throughput||{},l=r.capacitySettings||e.capacity_settings||t.capacity_settings||{},c=[["并发槽",e.capacity??0],["运行",e.running_count??0],["排队",e.queued_count??0],["可用",e.available_slots??0],["历史",e.finished_count??0]].map(([e,t])=>`
        <span class="job-metric">
          <b>${n(e)}</b>
          <strong>${n(t)}</strong>
        </span>
      `).join(""),u=o.length?o.map(H).join(""):'<p class="status">当前没有后台自动流程任务。</p>';s.autoJobCenter.innerHTML=`
    <div class="job-center-summary">
      ${c}
    </div>
    ${function(e={}){if(!e||"object"!=typeof e||!Object.keys(e).length)return"";let t=Number(e.utilization||0),a=Number(e.active_pressure||0),r=[["推荐槽",`${e.recommended_workers??e.capacity??0}/${e.max_configurable_workers??8}`],["利用率",`${Math.round(100*t)}%`],["压力",`${a.toFixed(2)}x`],["下个启动",B(e.eta_next_start_seconds)],["队列清空",B(e.eta_queue_clear_seconds)],["成功率",Number.isFinite(Number(e.recent_success_rate))?`${e.recent_success_rate}%`:"-"]],s=Array.isArray(e.signals)?e.signals:[],o=Number(e.capacity||0),i=Number(e.max_configurable_workers||0),l=Number(e.recommended_workers||o||0),c=Math.max(1,Math.min(i||l||1,Number.isFinite(l)?Math.round(l):o||1)),u=!0===e.runtime_configurable,d=c>o?`应用 ${c} 个槽位`:"应用推荐";return`
    <section class="throughput-panel" data-status="${n(X(e.status))}">
      <div class="throughput-head">
        <span class="throughput-dot"></span>
        <div>
          <strong>${n(e.label||"吞吐状态")}</strong>
          <p>${n(e.summary||"后台任务池处于待命状态。")}</p>
        </div>
      </div>
      <div class="throughput-metrics">
        ${r.map(([e,t])=>`
          <span>
            <b>${n(e)}</b>
            <strong>${n(t)}</strong>
          </span>
        `).join("")}
      </div>
      ${e.scaling_action?`<p class="throughput-action">${n(e.scaling_action)}</p>`:""}
      ${s.length?`<div class="throughput-signals">${s.map(e=>`<span>${n(e)}</span>`).join("")}</div>`:""}
      ${u?`
        <div class="throughput-tools">
          <button class="throughput-apply" type="button" data-capacity-action="autotune" title="应用容量推荐">${n(d)}</button>
        </div>
      `:""}
    </section>
  `}(i)}
    ${function(e={}){let t=e?.latest||(e?.status?e:null);if(!t)return"";let a=t.updates&&"object"==typeof t.updates?t.updates:{},r=t.signals&&"object"==typeof t.signals?t.signals:{},s=Object.entries(a).length?Object.entries(a).map(([e,t])=>`${function(e=""){return({auto_workflow_workers:"自动流程槽",delivery_batch_job_workers:"批量任务槽",delivery_package_workers:"打包线程"})[e]||String(e||"").replaceAll("_"," ")}(e)} -> ${t}`).join(" | "):"无需调整容量",o=[["自动队列",r.auto_queue],["压力",r.active_pressure],["交付队列",r.delivery_queue],["打包积压",r.package_backlog]].filter(([,e])=>null!=e&&""!==e).map(([e,t])=>`<span><b>${n(e)}</b><strong>${n(t)}</strong></span>`).join("");return`
    <section class="capacity-autotune" data-status="${n(X("applied"===t.status?"success":"idle"))}">
      <div>
        <b>自动调优审计</b>
        <p>${n(t.summary||"尚未运行容量推荐。")}</p>
      </div>
      <strong>${n(s)}</strong>
      ${o?`<div class="capacity-autotune-signals">${o}</div>`:""}
    </section>
  `}(r.capacityAutotune)}
    ${function(e={},t={},a={}){let r=Number(e.auto_workflow_workers||t.capacity||2),s=Number(e.delivery_batch_job_workers||a.capacity||1),o=Number(e.delivery_package_workers||4),i=Number(e.max_auto_workflow_workers||8),l=Number(e.max_delivery_batch_job_workers||4),c=Number(e.max_delivery_package_workers||8),u=e.source?` \xb7 ${e.source}`:"";return`
    <form class="capacity-panel" data-capacity-form>
      <div>
        <b>容量设置</b>
        <p>调整运行时并发上限，用于提升求解、打包和结果查看响应速度${n(u)}。</p>
      </div>
      <label>
        <span>自动流程槽</span>
        <input class="text-input" name="auto_workflow_workers" type="number" min="1" max="${n(i)}" value="${n(r)}" />
      </label>
      <label>
        <span>批量任务</span>
        <input class="text-input" name="delivery_batch_job_workers" type="number" min="1" max="${n(l)}" value="${n(s)}" />
      </label>
      <label>
        <span>打包线程</span>
        <input class="text-input" name="delivery_package_workers" type="number" min="1" max="${n(c)}" value="${n(o)}" />
      </label>
      <button class="capacity-save" type="submit">应用</button>
    </form>
  `}(l,e,t)}
    <div class="job-list">
      ${u}
    </div>
  `}function H(e={}){if("delivery_batch"===e.kind)return function(e={}){let t="queued"===e.status?`等待 ${B(e.wait_seconds)}`:"running"===e.status?`运行 ${B(e.run_seconds)}`:`耗时 ${B(e.run_seconds)}`,a=`请求 ${e.requested_count||0} \xb7 生成 ${e.packaged_count||0} \xb7 跳过 ${e.skipped_count||0} \xb7 失败 ${e.failed_count||0}`,r=e.summary||a,s=e.error?`<p>${n(e.error)}</p>`:"";return`
    <article class="job-row job-row-delivery" data-status="${n(X(e.status))}">
      <span class="job-status-dot"></span>
      <div class="job-main">
        <strong>批量交付包</strong>
        <small>${n(D(e.status))} \xb7 ${n(t)} \xb7 ${n(a)}</small>
        <p>${n(r)}</p>
        ${s}
      </div>
      <span class="job-open job-open-static">交付</span>
    </article>
  `}(e);let t=r.currentProject?.metadata?.id||"",a=e.project_name||e.project_id||"项目",s=t&&e.project_id===t,o="queued"===e.status?`等待 ${B(e.wait_seconds)}`:"running"===e.status?`运行 ${B(e.run_seconds)}`:`耗时 ${B(e.run_seconds)}`,i=e.resume?"继续生成":"一键流程",l=e.error?`<p>${n(e.error)}</p>`:"";return`
    <article class="job-row${s?" is-current":""}" data-status="${n(X(e.status))}">
      <span class="job-status-dot"></span>
      <div class="job-main">
        <strong>${n(a)}</strong>
        <small>${n(i)} \xb7 ${n(D(e.status))} \xb7 ${n(o)}</small>
        ${l}
      </div>
      <button class="job-open" type="button" data-project-id="${n(e.project_id||"")}">打开</button>
    </article>
  `}function B(e){let t=Math.max(0,Number(e)||0);if(t<60)return`${Math.round(t)}s`;let a=Math.floor(t/60),r=Math.round(t%60);if(a<60)return`${a}m ${r}s`;let s=Math.floor(a/60);return`${s}h ${a%60}m`}function D(e){return({success:"已完成",analyzed:"已分析",running:"运行中",queued:"排队中",failed:"失败",completed_with_warnings:"需复核",requires_api_key:"待配置",script_generated:"已生成",between_steps:"阶段切换中",cancel_requested:"正在中断",cancelled:"已中断",interrupted:"可继续",idle:"未开始",warning:"需注意",action_required:"需修复",repairable:"可继续",optimize:"可优化",ready:"可启动",clear:"无阻断",healthy:"稳定",busy:"高负载",saturated:"拥堵",growth_ready:"解题就绪",delivery_ready:"待打包",operating:"运行中",building:"建设中",empty:"等待项目",deliverable:"可提交",blocked:"不可提交",needs_work:"需补齐",review:"需复核",pass:"通过",fail:"失败",submission_ready:"提交就绪",solution_ready:"求解就绪",incubating:"培育中",trusted:"可信",watch:"观察中",at_risk:"存在风险",hot:"高意向",warm:"跟进中",nurture:"培育中",packaged:"已打包",skipped:"已跳过"})[e]||e||"未开始"}function X(e){return"success"===e||"analyzed"===e||"script_generated"===e||"clear"===e||"healthy"===e||"ready"===e||"growth_ready"===e||"deliverable"===e||"pass"===e||"submission_ready"===e||"trusted"===e?"success":"running"===e||"queued"===e||"cancel_requested"===e||"operating"===e?"running":"failed"===e||"interrupted"===e||"action_required"===e||"saturated"===e||"blocked"===e||"fail"===e||"at_risk"===e?"failed":"completed_with_warnings"===e||"requires_api_key"===e||"cancelled"===e||"repairable"===e||"optimize"===e||"busy"===e||"delivery_ready"===e||"building"===e||"needs_work"===e||"review"===e||"solution_ready"===e||"incubating"===e||"watch"===e?"warning":"pending"}function G(e,t=""){return(e||[]).filter(Boolean).slice(0,6).map(e=>`<span class="chip ${t}">${n(e)}</span>`).join("")}async function K(e){let t=r.currentProject?.metadata?.id;if(!t){s.problemSelectionStatus&&(s.problemSelectionStatus.textContent="请先打开一个项目。");return}if(!e){s.problemSelectionStatus&&(s.problemSelectionStatus.textContent="未识别到要选择的题号。");return}s.problemSelectionStatus&&(s.problemSelectionStatus.textContent=`正在选择 ${e} 题。`);try{let a=await p(`/api/projects/${encodeURIComponent(t)}/problem/selection`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({problem_id:e})});q(a.project),s.problemSelectionStatus&&(s.problemSelectionStatus.textContent=`已选择 ${e} 题，后续一键流程会以该题为准。`),await h()}catch(e){s.problemSelectionStatus&&(s.problemSelectionStatus.textContent=`选择失败：${e.message}`)}}async function Q(e){if(!e||!s.uploadProgress)return!1;try{let t=(await p(`/api/upload-analysis-progress/${encodeURIComponent(e)}`)).progress||{};if(!Object.keys(t).length)return!1;return eo(s.uploadProgress,t,7),["success","failed","completed_with_warnings"].includes(t.status)}catch{return!1}}function V(e){let t=e[0];return(t?.webkitRelativePath||t?.name||"赛题文件夹").split(/[\\/]/)[0]||"赛题文件夹"}async function Y(e){if(e&&s.modelAssistantProgress)try{let t=await p(`/api/projects/${encodeURIComponent(e)}/llm/model-assistant/progress`);Z(t.progress)}catch{}}function Z(e={}){eo(s.modelAssistantProgress,e,5)}async function ee(e,{resume:t=!1,initialMessage:a="正在调用大模型完成选题、生成并运行代码、回填结果、论文生成和审查。"}={}){if(!e){s.autoWorkflowStatus.textContent="请先打开一个项目。";return}let n=r.llmSettings||await p("/api/settings/llm");if(r.llmSettings=n,!n.configured){s.autoWorkflowStatus.textContent="请先在左侧 AI 设置中填写 API 密钥；LLM+代码自动解题不提供本地降级模式。";return}if(!T(r.currentProject?.metadata||{})){s.autoWorkflowStatus.textContent="请先在“选题”模块点击“选择此题”，确认后再运行一键自动流程。";return}s.runAutoWorkflow.disabled=!0,s.resumeAutoWorkflow&&(s.resumeAutoWorkflow.disabled=!0),s.cancelAutoWorkflow&&(s.cancelAutoWorkflow.disabled=!1),s.autoWorkflowStatus.textContent=t?"正在提交后台继续生成任务。":"正在提交后台自动流程任务。";try{let r=await p(`/api/projects/${encodeURIComponent(e)}/auto/${t?"resume/start":"start"}`,{method:"POST"});q(r.project);let n=r.auto_job||{};await w(),await v();let o=n.max_workers?`，任务池并发 ${n.max_workers}`:"";s.autoWorkflowStatus.textContent=n.existing?`已有自动流程后台任务正在执行${o}，正在接管进度。`:`${a} 已进入后台任务池${o}。`,d(n.existing?"已接管正在运行的自动流程":"自动流程已提交后台任务","success"),await er(e);let i=await et(e),l=i.status||i.progress?.status||"",c=i.progress?.steps||[],u=c.filter(e=>"warning"===e.status).length,m=c.filter(e=>"failed"===e.status).length,_=await p(`/api/projects/${encodeURIComponent(e)}`);if(q(_),"success"===l)s.autoWorkflowStatus.textContent="LLM+代码自动流程完成：已生成题解方案、运行代码得到结果、回填论文、审查报告和支撑材料。",d("自动流程已完成","success");else if("cancelled"===l)s.autoWorkflowStatus.textContent="自动流程已中断：当前阶段已安全结束，可点击“继续生成”从断点恢复。",d("自动流程已中断，可继续生成","warning");else if("failed"===l||"requires_api_key"===l){let e=i.progress?.resume_hint||i.progress?.last_failure_diagnosis?.suggested_action||"请查看进度诊断后继续生成。";s.autoWorkflowStatus.textContent=`自动流程失败：${e}`,d("自动流程失败，可查看诊断后继续生成","error")}else s.autoWorkflowStatus.textContent=`自动流程完成但需复核：${u} 个警告，${m} 个失败项。请查看自动解题报告。`,d("自动流程完成但需要复核","warning");await h()}catch(t){s.autoWorkflowStatus.textContent=`自动流程失败：${t.message}`,d(`自动流程失败：${t.message}`,"error");try{let t=await p(`/api/projects/${encodeURIComponent(e)}`);q(t),await h()}catch{}}finally{await er(e),await w(),await $(),await v(),s.runAutoWorkflow.disabled=!1,s.cancelAutoWorkflow&&(s.cancelAutoWorkflow.disabled=!0)}}async function et(e){let t=null,a=0;for(;;)if(await new Promise(e=>window.setTimeout(e,900)),es((t=await p(`/api/projects/${encodeURIComponent(e)}/progress`)).progress),en(t.status,t.progress||{}),(a+=1)%4==0&&await w(),!ea(t.status,t.progress||{}))return await w(),t}function ea(e="",t={}){return["queued","running","cancel_requested"].includes(e)||["queued","running","between_steps"].includes(t.status)}async function er(e){if(e&&s.autoWorkflowProgress)try{let t=await p(`/api/projects/${encodeURIComponent(e)}/progress`);es(t.progress),en(t.status,t.progress||{})}catch{}}function es(e={}){eo(s.autoWorkflowProgress,e,7)}function en(e="",t={}){let a=ea(e,t),r=!!t.can_resume||["failed","cancelled","completed_with_warnings","cancel_requested","interrupted"].includes(e);s.runAutoWorkflow&&(s.runAutoWorkflow.disabled=a),s.resumeAutoWorkflow&&(s.resumeAutoWorkflow.disabled=a||!r,s.resumeAutoWorkflow.title=r?t.resume_hint||t.last_failure_diagnosis?.suggested_action||"从上次成功阶段继续生成":"当前没有可继续的自动流程"),s.cancelAutoWorkflow&&(s.cancelAutoWorkflow.disabled=!a||!!t.cancel_requested)}function eo(e,t={},a=6){if(!e)return;let s=t.steps||[],i=t.current_step,l=t.live_stream||{};if(!s.length&&!i&&!ei(l)){e.classList.add("hidden"),e.innerHTML="";return}e.classList.remove("hidden"),e.setAttribute("role","status"),e.setAttribute("aria-live","polite");let c=Math.max(0,Math.min(100,Number(t.percent)||0)),u=i?[...s,i]:s,d=i?.title||D(t.status)||"等待更新";e.innerHTML=`
    <div class="progress-head">
      <div>
        <strong>${n(d)}</strong>
        <span>${n(t.completed_steps??0)} / ${n(t.total_steps||u.length||a)} 阶段</span>
      </div>
      <b>${n(c)}%</b>
    </div>
    <div class="progress-bar"><i style="width: ${c}%"></i></div>
    <div class="progress-steps">
      ${u.map(e=>(function(e,t={}){let a=e.status||"pending",s=e.duration_seconds?` \xb7 ${e.duration_seconds}s`:"",i=e.detail?`<p>${n(e.detail)}</p>`:"",l=function(e={},t={}){if(!e||"object"!=typeof e||!e.category)return"";let a=e.label||e.category||"失败诊断",s=e.repair_focus||e.evidence||"",o=e.category?`<b>${n(e.category)}</b>`:"",i=e.suggested_action||t.resumeHint||(t.canResume?"点击继续生成，系统会带着本次诊断继续自动修复。":""),l=t.canResume&&r.currentProject?.metadata?.id?'<button class="diagnosis-resume" type="button" data-auto-action="resume">继续生成</button>':"";return`
    <div class="failure-diagnosis">
      <div>
        <span>诊断</span>
        <strong>${n(a)}</strong>
        ${o}
      </div>
      ${s?`<p>${n(s)}</p>`:""}
      ${i||l?`
        <div class="failure-diagnosis-actions">
          ${i?`<p>建议动作：${n(i)}</p>`:""}
          ${l}
        </div>
      `:""}
    </div>
  `}(e.failure_diagnosis,{canResume:!!t.can_resume,resumeHint:t.resume_hint}),c=r.currentProject?.metadata?.id,u=c&&e.error_log?`<a class="progress-link" href="/api/projects/${encodeURIComponent(c)}/download/${o(e.error_log)}">查看错误日志</a>`:"";return`
    <div class="progress-step" data-status="${n(a)}">
      <span></span>
      <div>
        <strong>${n(e.title||e.id||"阶段")}</strong>
        <small>${n(D(a))}${n(s)}</small>
        ${i}
        ${l}
        ${u}
      </div>
    </div>
  `})(e,t)).join("")}
    </div>
    ${function(e={}){if(!ei(e))return"";let t=e.current||{},a=(e.events||[]).slice(-6).reverse(),r=t.content_tail||e.content_tail||"",s=t.status||e.status||"running",o=t.label||e.title||"大模型实时输出",i=t.content_chars??e.content_chars??0;return`
    <div class="llm-live-stream" data-status="${n(s)}">
      <div class="llm-live-head">
        <div>
          <strong>${n(o)}</strong>
          <span>${n(D(s))} \xb7 已接收 ${n(i)} 字符</span>
        </div>
        <b>实时</b>
      </div>
      ${r?`<pre>${n(r)}</pre>`:""}
      <div class="llm-live-events">
        ${a.map(el).join("")}
      </div>
    </div>
  `}(l)}
  `}function ei(e={}){return!!(e&&(e.current||e.events&&e.events.length||e.content_tail))}function el(e){let t=e.status||"info",a=e.detail?` \xb7 ${e.detail}`:"";return`
    <div class="llm-live-event" data-status="${n(t)}">
      <span></span>
      <p>${n(e.label||e.kind||"LLM 操作")}${n(a)}</p>
    </div>
  `}async function ec(e){s.refreshDiagnostics.disabled=!0,s.diagnosticsStatus.textContent="正在刷新附件画像、并行计划、性能健康和修复中心。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/diagnostics/refresh`,{method:"POST"});q(t.project);let a=t.diagnostics?.health||{},r=a.scores?.overall,n=Number.isFinite(Number(r))?`，综合 ${Number(r)} 分`:"",o=t.diagnostics?.repair||{},i=o.label?`，修复中心：${o.label}`:"";s.diagnosticsStatus.textContent=`诊断资产已刷新：${a.label||"已完成"}${n}${i}。`,d("诊断与性能报告已刷新","success"),await h(),await v()}catch(e){s.diagnosticsStatus.textContent=`诊断刷新失败：${e.message}`,d(`诊断刷新失败：${e.message}`,"error")}finally{s.refreshDiagnostics.disabled=!1}}async function eu(e){s.refreshRepairCenter&&(s.refreshRepairCenter.disabled=!0),s.repairCenterStatus&&(s.repairCenterStatus.textContent="正在重建自动修复简报。");try{let t=await p(`/api/projects/${encodeURIComponent(e)}/repair/briefing`,{method:"POST"});q(t.project);let a=t.repair?.label||t.project?.metadata?.repair_center_label||"已完成";s.repairCenterStatus&&(s.repairCenterStatus.textContent=`修复中心已刷新：${a}。`),d("自动修复中心已刷新","success"),await h(),await v()}catch(e){s.repairCenterStatus&&(s.repairCenterStatus.textContent=`修复中心刷新失败：${e.message}`),d(`修复中心刷新失败：${e.message}`,"error")}finally{s.refreshRepairCenter&&(s.refreshRepairCenter.disabled=!1)}}async function ed(e){s.refreshDeliveryReadiness&&(s.refreshDeliveryReadiness.disabled=!0),s.deliveryReadinessStatus&&(s.deliveryReadinessStatus.textContent="正在检查论文、结果、审查和支撑材料交付状态。");try{let t=await p(`/api/projects/${encodeURIComponent(e)}/delivery/readiness`,{method:"POST"});q(t.project);let a=t.delivery?.label||t.project?.metadata?.delivery_readiness_label||"已完成",r=t.delivery?.score??t.project?.metadata?.delivery_readiness_score,n=Number.isFinite(Number(r))?`，交付分 ${Number(r)}`:"";s.deliveryReadinessStatus&&(s.deliveryReadinessStatus.textContent=`交付就绪已刷新：${a}${n}。`),d("交付就绪中心已刷新","success"),await h(),await $(),await v()}catch(e){s.deliveryReadinessStatus&&(s.deliveryReadinessStatus.textContent=`交付就绪刷新失败：${e.message}`),d(`交付就绪刷新失败：${e.message}`,"error")}finally{s.refreshDeliveryReadiness&&(s.refreshDeliveryReadiness.disabled=!1)}}s.artifacts.addEventListener("click",async e=>{let t=e.target.closest(".artifact-open");if(!t)return;let a=t.dataset.projectId,r=t.dataset.path;if(!a||!r)return;t.disabled=!0;let n=t.textContent;t.textContent="打开中";try{await p(`/api/projects/${encodeURIComponent(a)}/open-location/${o(r)}`,{method:"POST"}),t.textContent="已打开",d("已打开文件所在位置","success"),window.setTimeout(()=>{t.textContent=n,t.disabled=!1},1400)}catch(e){t.textContent="打开失败",s.projectStatus.textContent=`打开文件位置失败：${e.message}`,d(`打开位置失败：${e.message}`,"error"),window.setTimeout(()=>{t.textContent=n,t.disabled=!1},1800)}}),s.file.addEventListener("change",()=>{let e=s.file.files[0];s.fileLabel.textContent=e?e.name:"选择 zip、pdf、docx、xlsx 或 csv",e&&s.folder&&(s.folder.value="",s.folderLabel.textContent="选择包含全部赛题材料的文件夹")}),s.folder.addEventListener("change",()=>{let e=Array.from(s.folder.files||[]);if(!e.length){s.folderLabel.textContent="选择包含全部赛题材料的文件夹";return}let t=V(e);s.folderLabel.textContent=`${t} \xb7 ${e.length} 个文件`,s.file&&(s.file.value="",s.fileLabel.textContent="选择 zip、pdf、docx、xlsx 或 csv")}),s.form.addEventListener("submit",async e=>{var t;let a,n;e.preventDefault();let o=Array.from(s.folder?.files||[]),i=s.file.files[0];if(!i&&!o.length){s.status.textContent="请先选择文件、压缩包或赛题文件夹。";return}let l=s.form.querySelector("button"),c=new FormData,u=window.crypto?.randomUUID?window.crypto.randomUUID():`upload-${Date.now()}-${Math.random().toString(16).slice(2)}`;c.append("progress_id",u);let m="/api/projects";if(o.length){m="/api/projects/folder";let e=V(o);c.append("folder_name",e),o.forEach(e=>{c.append("files",e,e.webkitRelativePath||e.name)})}else c.append("file",i);l.disabled=!0,r.uploadProgressStop&&r.uploadProgressStop(),eo(s.uploadProgress,{status:"running",current_step:{id:"upload",title:o.length?"上传赛题文件夹":"上传赛题材料",status:"running",detail:o.length?`正在上传 ${o.length} 个文件。`:`正在上传 ${i.name}。`},steps:[],completed_steps:0,total_steps:7,percent:3},7),a=!1,Q(t=u),n=window.setInterval(async()=>{a||await Q(t)&&(a=!0,window.clearInterval(n))},500),r.uploadProgressStop=()=>{a=!0,window.clearInterval(n)},s.status.textContent=o.length?`正在上传文件夹中的 ${o.length} 个文件并解析，请稍候。`:"正在上传并解析，请稍候。";try{let e=await p(m,{method:"POST",body:c});if(await Q(u),s.status.textContent="分析完成。",d("赛题分析完成","success"),q(e),await h(),s.autoRunAfterUpload?.checked){let t=e.analysis?.recommended_problem||{};t.id?(await K(t.id),await ee(e.metadata.id,{initialMessage:"上传分析完成，已按系统推荐题目确认选择，正在调用大模型生成并运行代码，随后回填结果、撰写论文和审查。"})):s.status.textContent="分析完成，但未识别到可自动确认的推荐题目，请在选题模块手动选择。"}}catch(e){await Q(u),s.status.textContent=`分析失败：${e.message}`,d(`赛题分析失败：${e.message}`,"error")}finally{r.uploadProgressStop&&(r.uploadProgressStop(),r.uploadProgressStop=null,await Q(u)),l.disabled=!1}}),s.refresh.addEventListener("click",async()=>{s.refresh.disabled=!0;try{await h(),await w(),await $(),await v(),d("项目列表已刷新","success")}catch(e){d(`刷新项目失败：${e.message}`,"error")}finally{s.refresh.disabled=!1}}),s.refreshAutoJobs?.addEventListener("click",async()=>{s.refreshAutoJobs.disabled=!0;try{await w(),await $(),await v(),d("后台任务中心已刷新","success")}catch(e){d(`后台任务刷新失败：${e.message}`,"error")}finally{s.refreshAutoJobs.disabled=!1}}),s.refreshGrowthMetrics?.addEventListener("click",async()=>{s.refreshGrowthMetrics.disabled=!0,s.growthCenterStatus&&(s.growthCenterStatus.textContent="正在刷新项目漏斗、交付产出和任务吞吐指标。");try{await $(),await v(),s.growthCenterStatus&&(s.growthCenterStatus.textContent="解题进度中心已刷新。"),d("解题进度中心已刷新","success")}catch(e){s.growthCenterStatus&&(s.growthCenterStatus.textContent=`解题进度刷新失败：${e.message}`),d(`解题进度刷新失败：${e.message}`,"error")}finally{s.refreshGrowthMetrics.disabled=!1}}),s.refreshTrustCenter?.addEventListener("click",async()=>{s.refreshTrustCenter.disabled=!0,s.trustCenterStatus&&(s.trustCenterStatus.textContent="正在刷新质量与交付信任证据。");try{await v(),s.trustCenterStatus&&(s.trustCenterStatus.textContent="信任中心已刷新。"),d("信任中心已刷新","success")}catch(e){s.trustCenterStatus&&(s.trustCenterStatus.textContent=`信任中心刷新失败：${e.message}`),d(`信任中心刷新失败：${e.message}`,"error")}finally{s.refreshTrustCenter.disabled=!1}}),s.trustCenter?.addEventListener("click",async e=>{let t=e.target.closest("[data-trust-action]");if(!t)return;let a=t.dataset.trustAction;if(["export_audit","repair_campaign"].includes(a)){t.disabled=!0,s.trustCenterStatus&&(s.trustCenterStatus.textContent="repair_campaign"===a?"正在运行修复行动。":"正在导出信任审计包。");try{if("repair_campaign"===a){let e=await p("/api/product/trust/repair-campaign/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({queue_resumes:!0,refresh_diagnostics:!0,limit:20})});r.trustMetrics=e.trust||r.trustMetrics||{},r.repairCampaigns=e.repair_campaigns||r.repairCampaigns||null,r.growthMetrics=e.growth||r.growthMetrics,r.autoJobs=e.auto_jobs||r.autoJobs,r.deliveryBatchJobs=e.delivery_batch_jobs||r.deliveryBatchJobs,O(r.trustMetrics,r.trustExports),F(r.autoJobs,r.deliveryBatchJobs),r.growthMetrics&&N(r.growthMetrics);let t=e.repair_campaign||{};s.trustCenterStatus&&(s.trustCenterStatus.textContent=t.summary||"修复行动已完成。"),d("修复行动已完成","success");return}let e=await p("/api/product/trust/export",{method:"POST"});r.trustMetrics=e.trust||e.trust_report?.trust||r.trustMetrics||{},r.trustExports=e.trust_exports||r.trustExports||null,O(r.trustMetrics,r.trustExports);let t=e.trust_report||{};if(s.trustCenterStatus){let e=t.size?` \xb7 ${t.size}`:"";s.trustCenterStatus.textContent=`信任审计包已导出：${t.filename||t.id||"压缩包"}${e}`}t.download_url&&window.open(t.download_url,"_blank","noopener"),d("信任审计包已就绪","success")}catch(e){s.trustCenterStatus&&(s.trustCenterStatus.textContent=`信任审计包导出失败：${e.message}`),d(`信任审计包导出失败：${e.message}`,"error")}finally{t.disabled=!1}}}),s.growthCenter?.addEventListener("click",async e=>{let t=e.target.closest("[data-growth-action]");if(!t)return;let a=t.dataset.growthAction;t.disabled=!0;try{if("batch_packages"===a){s.growthCenterStatus&&(s.growthCenterStatus.textContent="正在并发生成所有可交付项目的正式交付包。");let e=await p("/api/delivery/packages/batch/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({force:!1,max_workers:Number(r.capacitySettings?.delivery_package_workers||4)})}),t=e.delivery_batch_job||{};e.delivery_batch_jobs&&(r.deliveryBatchJobs=e.delivery_batch_jobs),e.growth?(r.growthMetrics=e.growth,N(r.growthMetrics)):await $(),await w(),await h(),await v(),s.growthCenterStatus&&(s.growthCenterStatus.textContent=t.summary||"批量交付包任务已入队。"),d(`批量交付包任务已入队：${t.requested_count||0} 个项目`,"success")}}catch(e){s.growthCenterStatus&&(s.growthCenterStatus.textContent=`批量交付包失败：${e.message}`),d(`批量交付包失败：${e.message}`,"error")}finally{t.disabled=!1}}),s.autoJobCenter?.addEventListener("click",async e=>{let t=e.target.closest("[data-capacity-action='autotune']");if(t){t.disabled=!0;try{let e=await p("/api/product/capacity/autotune",{method:"POST"});r.capacitySettings=e.capacity_settings||r.capacitySettings,r.capacityAutotune=e.capacity_autotune_history||{latest:e.capacity_autotune,items:[e.capacity_autotune].filter(Boolean)},r.autoJobs=e.auto_jobs||r.autoJobs,r.deliveryBatchJobs=e.delivery_batch_jobs||r.deliveryBatchJobs,F(r.autoJobs,r.deliveryBatchJobs),await $(),await v();let t=e.capacity_autotune||{};d("already_optimal"===t.status?"容量已经最优":"容量推荐已应用","success")}catch(e){d(`容量推荐失败：${e.message}`,"error")}finally{t.disabled=!1}return}let a=e.target.closest(".job-open");if(!a)return;let s=a.dataset.projectId;if(s){a.disabled=!0;try{await A(s)}finally{a.disabled=!1}}}),s.autoJobCenter?.addEventListener("submit",async e=>{let t=e.target.closest("[data-capacity-form]");if(!t)return;e.preventDefault();let a=t.querySelector("button[type='submit']");a&&(a.disabled=!0);try{let e=new FormData(t),a={auto_workflow_workers:Number(e.get("auto_workflow_workers")||0),delivery_batch_job_workers:Number(e.get("delivery_batch_job_workers")||0),delivery_package_workers:Number(e.get("delivery_package_workers")||0)},s=await p("/api/product/capacity",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(a)});r.capacitySettings=s.capacity_settings||r.capacitySettings,r.autoJobs=s.auto_jobs||r.autoJobs,r.deliveryBatchJobs=s.delivery_batch_jobs||r.deliveryBatchJobs,F(r.autoJobs,r.deliveryBatchJobs),await $(),await v(),d("容量设置已应用","success")}catch(e){d(`容量设置失败：${e.message}`,"error")}finally{a&&(a.disabled=!1)}}),s.projectSearch&&s.projectSearch.addEventListener("input",()=>{r.projectQuery=s.projectSearch.value,S()}),s.projectList?.addEventListener("change",e=>{let t=e.target.closest(".project-select-input");if(!t)return;let a=t.dataset.projectId;a&&(t.checked?r.selectedProjectIds.add(a):r.selectedProjectIds.delete(a),S())}),s.selectAnalyzedProjects?.addEventListener("click",()=>{k().forEach(e=>{e.analysis_available&&e.id&&r.selectedProjectIds.add(e.id)}),S(),s.batchProjectStatus.textContent=`已选择 ${r.selectedProjectIds.size} 个已分析项目。`}),s.clearProjectSelection?.addEventListener("click",()=>{r.selectedProjectIds.clear(),S(),s.batchProjectStatus.textContent="已清空批量选择。"}),s.batchStartProjects?.addEventListener("click",async()=>{await C()}),s.openProjectRoot&&s.openProjectRoot.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e)return void d("请先打开一个项目。","warning");s.openProjectRoot.disabled=!0;let t=s.openProjectRoot.textContent;s.openProjectRoot.textContent="打开中";try{await p(`/api/projects/${encodeURIComponent(e)}/open-root`,{method:"POST"}),s.openProjectRoot.textContent="已打开",d("已打开项目文件夹","success"),window.setTimeout(()=>{s.openProjectRoot.textContent=t},1200)}catch(e){d(`打开项目文件夹失败：${e.message}`,"error"),s.openProjectRoot.textContent=t}finally{window.setTimeout(()=>{s.openProjectRoot.disabled=!1},250)}}),s.workflowStrategyInput?.addEventListener("change",()=>{let e=s.workflowStrategyInput.value||"balanced",t=(r.llmSettings?.workflow_strategy_options||[]).find(t=>t.id===e);s.workflowStrategyHint&&(s.workflowStrategyHint.textContent=t?`当前策略：${t.label}。${t.summary}`:"当前策略：均衡。速度和成功率兼顾。")}),s.llmSettingsForm.addEventListener("submit",async e=>{e.preventDefault();let t=s.llmSettingsForm.querySelector("button[type='submit']");t.disabled=!0,s.llmSettingsStatus.textContent="正在保存 AI 设置。";try{let e={api_key:s.apiKeyInput.value,base_url:s.baseUrlInput.value,model:s.modelInput.value,workflow_strategy:s.workflowStrategyInput?.value||"balanced"},t=await p("/api/settings/llm",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(e)});f(t),d("AI 设置已保存","success")}catch(e){s.llmSettingsStatus.textContent=`保存失败：${e.message}`,d(`AI 设置保存失败：${e.message}`,"error")}finally{t.disabled=!1}}),s.clearLlmSettings.addEventListener("click",async()=>{s.clearLlmSettings.disabled=!0,s.llmSettingsStatus.textContent="正在清除 AI 设置。";try{let e=await p("/api/settings/llm",{method:"DELETE"});f(e),d("AI 设置已清除","success")}catch(e){s.llmSettingsStatus.textContent=`清除失败：${e.message}`,d(`清除 AI 设置失败：${e.message}`,"error")}finally{s.clearLlmSettings.disabled=!1}}),s.templateFileInput.addEventListener("change",()=>{let e=s.templateFileInput.files[0];s.templateFileLabel.textContent=e?e.name:"选择 LaTeX 模板或 Word/PDF 格式说明"}),s.templateSelect.addEventListener("change",()=>{y(s.templateSelect.value||"builtin-default")}),s.templateUploadForm.addEventListener("submit",async e=>{e.preventDefault();let t=s.templateFileInput.files[0];if(!t){s.templateStatus.textContent="请先选择 .tex 模板，或 .docx/.pdf/.txt/.md 格式说明文档。";return}if(![".tex",".docx",".pdf",".txt",".md"].includes(t.name.slice(t.name.lastIndexOf(".")).toLowerCase())){s.templateStatus.textContent="当前只支持 .tex 模板，或 .docx/.pdf/.txt/.md 格式说明文档。";return}let a=s.templateUploadForm.querySelector("button[type='submit']"),n=new FormData;n.append("name",s.templateNameInput.value),n.append("file",t),a.disabled=!0,s.templateStatus.textContent="正在上传并解析模板或格式说明。";try{let e=await p("/api/templates",{method:"POST",body:n});r.templates=e.templates||[],b(e.template?.id||"builtin-default"),s.templateStatus.textContent=e.template?.mode==="rules"?"格式说明已上传，生成论文时会作为官方格式规则保留。":"LaTeX 模板已上传，可在格式模板中选择。",s.templateFileInput.value="",s.templateFileLabel.textContent="选择 LaTeX 模板或 Word/PDF 格式说明"}catch(e){s.templateStatus.textContent=`模板上传失败：${e.message}`}finally{a.disabled=!1}}),s.deleteTemplate.addEventListener("click",async()=>{let e=s.templateSelect.value;if(!e||"builtin-default"===e){s.templateStatus.textContent="内置模板不能删除。";return}s.deleteTemplate.disabled=!0,s.templateStatus.textContent="正在删除模板。";try{r.templates=(await p(`/api/templates/${encodeURIComponent(e)}`,{method:"DELETE"})).templates||[],b("builtin-default"),s.templateStatus.textContent="模板已删除。"}catch(e){s.templateStatus.textContent=`删除失败：${e.message}`}finally{s.deleteTemplate.disabled=!1}}),s.paperOptionsForm.addEventListener("submit",async e=>{e.preventDefault();let t=r.currentProject?.metadata?.id;if(!t){s.paperOptionsStatus.textContent="请先打开一个项目。";return}let a=s.paperOptionsForm.querySelector("button[type='submit']"),n=s.targetBodyPages.value.trim(),o=n?Number(n):null,i={template_id:s.templateSelect.value||"builtin-default",target_body_pages:o};a.disabled=!0,s.paperOptionsStatus.textContent="正在保存论文设置。";try{let e=await p(`/api/projects/${encodeURIComponent(t)}/paper/options`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(i)});q(e.project),s.paperOptionsStatus.textContent=o?`已保存：正文不少于 ${o} 页。`:"已保存：暂不约束正文页数。",await h()}catch(e){s.paperOptionsStatus.textContent=`保存失败：${e.message}`}finally{a.disabled=!1}}),s.modelAssistantForm.addEventListener("submit",async e=>{var t;let a,n;e.preventDefault();let i=r.currentProject?.metadata?.id;if(!i){s.modelAssistantStatus.textContent="请先打开一个项目。";return}let l=s.assistModelInput.value.trim();if(!l){s.modelAssistantStatus.textContent="请填写模型或算法名称。";return}let c=s.modelAssistantForm.querySelector("button[type='submit']");c.disabled=!0,s.modelAssistantStatus.textContent="正在生成模型辅助方案，下面会显示检索、提示词构建和 LLM 生成过程。";let u=(a=!1,Y(t=i),n=window.setInterval(()=>{a||Y(t)},700),()=>{a=!0,window.clearInterval(n)});try{let e=await p(`/api/projects/${encodeURIComponent(i)}/llm/model-assistant`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({problem_ref:s.assistProblemSelect.value,model_name:l,user_goal:s.assistGoalInput.value})});q(e.project);let t=(e.artifacts||{}).llm_model_assistant;s.modelAssistantStatus.innerHTML=t?`模型辅助方案已生成：<a href="/api/projects/${encodeURIComponent(i)}/download/${o(t)}">查看报告</a>。`:"模型辅助方案已生成，可在生成文件中查看。",await h()}catch(e){s.modelAssistantStatus.textContent=`模型辅助失败：${e.message}`}finally{u(),await Y(i),c.disabled=!1}}),s.runModeling.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.modelingStatus.textContent="请先打开一个项目。";return}s.runModeling.disabled=!0,s.modelingStatus.textContent="正在生成并运行基线建模脚本。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/model/run`,{method:"POST"});q(t.project);let a=t.modeling?.outputs||{},r=a.tables?.length??0,n=a.figures?.length??0;s.modelingStatus.textContent=t.modeling.success?`建模完成：生成 ${r} 个结果表、${n} 张图。`:"建模失败，请查看日志。",await h()}catch(e){s.modelingStatus.textContent=`建模失败：${e.message}`}finally{s.runModeling.disabled=!1}}),s.runSpecialized.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.specializedStatus.textContent="请先打开一个项目。";return}s.runSpecialized.disabled=!0,s.specializedStatus.textContent="正在生成并运行专项建模脚本。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/specialized/run`,{method:"POST"});q(t.project);let a=t.specialized?.outputs||{},r=a.specialized_models?.length??0,n=a.tables?.length??0,o=a.figures?.length??0;s.specializedStatus.textContent=t.specialized.success?`专项建模完成：${r} 个模型、${n} 个结果表、${o} 张图。`:"专项建模失败，请查看日志。",await h()}catch(e){s.specializedStatus.textContent=`专项建模失败：${e.message}`}finally{s.runSpecialized.disabled=!1}}),s.autoWorkflowProgress?.addEventListener("click",async e=>{let t=e.target.closest("[data-auto-action='resume']");if(!t)return;let a=r.currentProject?.metadata?.id;if(!a){s.autoWorkflowStatus.textContent="请先打开一个项目。";return}t.disabled=!0,await ee(a,{resume:!0})}),s.runAutoWorkflow.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;await ee(e)}),s.resumeAutoWorkflow&&s.resumeAutoWorkflow.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;await ee(e,{resume:!0})}),s.cancelAutoWorkflow&&s.cancelAutoWorkflow.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.autoWorkflowStatus.textContent="请先打开一个项目。";return}s.cancelAutoWorkflow.disabled=!0,s.autoWorkflowStatus.textContent="已请求中断，系统会在当前阶段安全结束后停止。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/auto/cancel`,{method:"POST"});q(t.project),await er(e),await w(),await h(),await v()}catch(e){s.autoWorkflowStatus.textContent=`中断请求失败：${e.message}`,s.cancelAutoWorkflow.disabled=!1}}),s.refreshDiagnostics?.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.diagnosticsStatus.textContent="请先打开一个项目。";return}await ec(e)}),s.refreshRepairCenter?.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.repairCenterStatus.textContent="请先打开一个项目。";return}await eu(e)}),s.refreshDeliveryReadiness?.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.deliveryReadinessStatus.textContent="请先打开一个项目。";return}await ed(e)}),s.repairCenter?.addEventListener("click",async e=>{let t=e.target.closest("[data-repair-action]");if(!t)return;let a=r.currentProject?.metadata?.id;if(!a)return;let s=t.dataset.repairAction;if("resume"===s)return void await ee(a,{resume:!0});if("start"===s)return void await ee(a,{resume:!1});if("diagnostics"===s)return void await ec(a);if("open_report"===s){let e=r.currentProject?.metadata?.artifacts||{},t=e.repair_briefing||e.repair_briefing_json||e.computed_solver_repair;t&&window.open(`/api/projects/${encodeURIComponent(a)}/download/${o(t)}`,"_blank","noopener")}}),s.deliveryCenter?.addEventListener("click",async e=>{let t=e.target.closest("[data-delivery-action]");if(!t)return;let a=r.currentProject?.metadata?.id;if(!a)return;let n=t.dataset.deliveryAction;t.disabled=!0;try{if("resume"===n)return void await ee(a,{resume:!0});if("start"===n)return void await ee(a,{resume:!1});if("analyze"===n){s.deliveryReadinessStatus&&(s.deliveryReadinessStatus.textContent="正在重建赛题分析并刷新交付门禁。");let e=await p(`/api/projects/${encodeURIComponent(a)}/analyze`,{method:"POST"});q(e.project),await ed(a),await h();return}if("diagnostics"===n){await ec(a),await ed(a);return}if("repair"===n){await eu(a),await ed(a);return}if("package"===n){s.deliveryReadinessStatus&&(s.deliveryReadinessStatus.textContent="正在生成正式交付包、清单和文件哈希。");let e=await p(`/api/projects/${encodeURIComponent(a)}/delivery/package`,{method:"POST"});q(e.project);let t=e.package?.package?.size_bytes,r=Number.isFinite(Number(t))?`，大小 ${P(Number(t))}`:"";s.deliveryReadinessStatus&&(s.deliveryReadinessStatus.textContent=`正式交付包已生成${r}。`),d("正式交付包已生成","success"),await h(),await $(),await v();return}if("compile"===n){s.compileStatus.textContent="正在编译 PDF 并导出 Word。";let e=await p(`/api/projects/${encodeURIComponent(a)}/compile`,{method:"POST"});q(e.project),s.compileStatus.textContent=e.compile.success?"编译完成：已生成 PDF，并导出 Word 文档。":"编译失败，请查看编译日志和 Word 导出日志。",await h();return}if("review"===n){s.paperReviewStatus.textContent="正在审查论文结构、图表、编译日志和结果可追溯性。";let e=await p(`/api/projects/${encodeURIComponent(a)}/paper/review`,{method:"POST"});q(e.project),s.paperReviewStatus.textContent="论文审查完成，可查看审查报告。",await h();return}"support_zip"===n&&window.open(`/api/projects/${encodeURIComponent(a)}/download/support.zip`,"_blank","noopener")}catch(e){s.deliveryReadinessStatus&&(s.deliveryReadinessStatus.textContent=`交付动作失败：${e.message}`),d(`交付动作失败：${e.message}`,"error")}finally{t.disabled=!1}}),s.generateSkillReport.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.skillReportStatus.textContent="请先打开一个项目。";return}s.generateSkillReport.disabled=!0,s.skillReportStatus.textContent="正在整理 GitHub 数学建模、科研写作、模型路由和学术诚信门禁规则。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/skills/report`,{method:"POST"});q(t.project),s.skillReportStatus.textContent="技能库与诚信门禁报告已生成，可在生成文件中查看。",await h()}catch(e){s.skillReportStatus.textContent=`技能库与诚信门禁报告生成失败：${e.message}`}finally{s.generateSkillReport.disabled=!1}}),s.generateCodeGraph.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.codeGraphStatus.textContent="请先打开一个项目。";return}s.generateCodeGraph.disabled=!0,s.codeGraphStatus.textContent="正在扫描项目代码，生成符号、导入和调用关系图谱。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/codegraph/report`,{method:"POST"});q(t.project),s.codeGraphStatus.textContent="代码图谱已生成，可在生成文件中查看。",await h()}catch(e){s.codeGraphStatus.textContent=`代码图谱生成失败：${e.message}`}finally{s.generateCodeGraph.disabled=!1}}),s.fillPaper.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.paperFillStatus.textContent="请先打开一个项目。";return}s.fillPaper.disabled=!0,s.paperFillStatus.textContent="正在把结果整合到 LaTeX。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/paper/fill`,{method:"POST"});q(t.project),s.paperFillStatus.textContent="论文回填完成，可继续编译 LaTeX。",await h()}catch(e){s.paperFillStatus.textContent=`回填失败：${e.message}`}finally{s.fillPaper.disabled=!1}}),s.compile.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.compileStatus.textContent="请先打开一个项目。";return}s.compile.disabled=!0,s.compileStatus.textContent="正在编译 PDF 并导出 Word。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/compile`,{method:"POST"});q(t.project),s.compileStatus.textContent=t.compile.success?"编译完成：已生成 PDF，并导出 Word 文档。":"编译失败，请查看编译日志和 Word 导出日志。",await h()}catch(e){s.compileStatus.textContent=`编译失败：${e.message}`}finally{s.compile.disabled=!1}}),s.reviewPaper.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.paperReviewStatus.textContent="请先打开一个项目。";return}s.reviewPaper.disabled=!0,s.paperReviewStatus.textContent="正在审查论文结构、图表、编译日志和结果可追溯性。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/paper/review`,{method:"POST"});q(t.project),s.paperReviewStatus.textContent="论文审查完成，可查看审查报告。",await h()}catch(e){s.paperReviewStatus.textContent=`审查失败：${e.message}`}finally{s.reviewPaper.disabled=!1}}),s.runLlmAnalysis.addEventListener("click",async()=>{let e=r.currentProject?.metadata?.id;if(!e){s.llmAnalysisStatus.textContent="请先打开一个项目。";return}s.runLlmAnalysis.disabled=!0,s.llmAnalysisStatus.textContent="正在调用大模型分析赛题并刷新 LLM 报告。";try{let t=await p(`/api/projects/${encodeURIComponent(e)}/llm/analyze`,{method:"POST"});q(t.project),s.llmAnalysisStatus.textContent="LLM 分析完成，可查看分析报告。",await h()}catch(e){s.llmAnalysisStatus.textContent=`LLM 分析失败：${e.message}`}finally{s.runLlmAnalysis.disabled=!1}}),c(function(){let e=new URLSearchParams(window.location.search).get("theme");if("light"===e||"dark"===e)return l("modelark-theme",e),e;let t=i("modelark-theme","");return"light"===t||"dark"===t?t:window.matchMedia?.("(prefers-color-scheme: dark)").matches?"dark":"light"}()),s.themeToggle?.addEventListener("click",()=>{c("dark"==("dark"===document.documentElement.dataset.theme?"dark":"light")?"light":"dark",{persist:!0})}),function(){let e=Array.from(document.querySelectorAll("[data-module-tab]")),t=Array.from(document.querySelectorAll("[data-module-panel]"));if(!e.length)return;let a=(a,{focus:r=!1}={})=>{let s=e.find(e=>e.dataset.moduleTab===a)||e[0];e.forEach(e=>{let t=e===s;e.classList.toggle("is-active",t),e.setAttribute("aria-selected",t?"true":"false"),e.tabIndex=t?0:-1}),t.forEach(e=>{let t=e.dataset.modulePanel===s.dataset.moduleTab;e.classList.toggle("is-active",t),e.hidden=!t}),l("mmw-active-module",s.dataset.moduleTab),r&&s.focus()};e.forEach((t,r)=>{t.addEventListener("click",()=>{a(t.dataset.moduleTab)}),t.addEventListener("keydown",t=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(t.key))return;t.preventDefault();let s=r;"ArrowRight"===t.key?s=(r+1)%e.length:"ArrowLeft"===t.key?s=(r-1+e.length)%e.length:"Home"===t.key?s=0:"End"===t.key&&(s=e.length-1),a(e[s].dataset.moduleTab,{focus:!0})})}),a(i("mmw-active-module",e[0].dataset.moduleTab))}(),m(),h(),w(),$(),v()}]);