import LegacyRuntime from "./LegacyRuntime";

export default function WorkbenchPage() {
  return (
    <>
      <a className="skip-link" href="#main-content">跳到工作区</a>
      <main className="shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="mark" aria-hidden="true">
              <svg viewBox="0 0 64 64" focusable="false">
                <path className="mark-sail" d="M32 9 48 35H32Z" />
                <path className="mark-fold" d="M30 16 15 35h15Z" />
                <path className="mark-hull" d="M13 39h38l-7 10H20Z" />
                <path className="mark-route" d="M18 28c6-6 16-8 27-5" />
                <circle cx="18" cy="28" r="3" />
                <circle cx="45" cy="23" r="3" />
              </svg>
            </div>
            <div className="brand-copy">
              <span className="brand-kicker">ModelArk</span>
              <h1>数模方舟</h1>
              <p>竞赛建模闭环助手</p>
            </div>
          </div>

          <section className="panel">
            <h2>上传赛题</h2>
            <form id="upload-form">
              <label className="drop-zone" htmlFor="file-input">
                <span id="file-label">选择赛题文件或压缩包</span>
                <input id="file-input" name="file" type="file" />
              </label>
              <details className="simple-advanced">
                <summary>高级上传选项</summary>
                <label className="drop-zone" htmlFor="folder-input">
                  <span id="folder-label">选择包含全部赛题材料的文件夹</span>
                  <input id="folder-input" name="files" type="file" webkitdirectory="" directory="" multiple />
                </label>
                <label className="check-row">
                  <input id="auto-run-after-upload" type="checkbox" />
                  <span>上传后按推荐题目自动运行一键流程</span>
                </label>
              </details>
              <button className="primary" type="submit">开始分析</button>
            </form>
            <p id="upload-status" className="status" aria-live="polite"></p>
            <div id="upload-analysis-progress" className="workflow-progress hidden" aria-live="polite"></div>
          </section>

          <section className="panel">
            <div className="section-title panel-title-actions">
              <h2>大模型设置</h2>
              <a
                id="get-api-key"
                className="ghost compact external-link"
                href="https://api.chshapi.org"
                target="_blank"
                rel="noreferrer"
              >
                获取密钥
              </a>
            </div>
            <form id="llm-settings-form" className="settings-form">
              <label>
                <span className="label">大模型接口密钥</span>
                <input id="api-key-input" className="text-input" type="password" autoComplete="off" placeholder="sk-..." />
              </label>
              <details className="simple-advanced">
                <summary>高级模型设置</summary>
                <label>
                  <span className="label">接口地址</span>
                  <input id="base-url-input" className="text-input" type="url" autoComplete="off" />
                </label>
                <label>
                  <span className="label">模型</span>
                  <input id="model-input" className="text-input" type="text" autoComplete="off" />
                </label>
                <label>
                  <span className="label">求解策略</span>
                  <select id="workflow-strategy-input" className="text-input">
                    <option value="balanced">均衡：速度和成功率兼顾</option>
                    <option value="stable">稳妥：更多校验和自动修复</option>
                    <option value="turbo">极速：并行读取附件和子问题</option>
                  </select>
                </label>
                <p id="workflow-strategy-hint" className="strategy-hint">
                  默认使用均衡档；只有需要更快或更稳时再调整。
                </p>
                <button id="clear-llm-settings" className="ghost" type="button">清除设置</button>
              </details>
              <div className="inline-actions">
                <button id="save-llm-settings" className="primary compact" type="submit">保存</button>
                <button id="test-llm-settings" className="ghost" type="button">测试连接</button>
              </div>
            </form>
            <p id="llm-settings-status" className="status" aria-live="polite"></p>
          </section>

          <section className="panel">
            <div className="section-title">
              <h2>项目</h2>
              <button id="refresh-projects" className="ghost" type="button">刷新</button>
            </div>
            <label className="project-search" htmlFor="project-search">
              <span className="sr-only">搜索项目</span>
              <input id="project-search" className="text-input" type="search" placeholder="搜索项目名、状态、文件/元数据异常或时间" autoComplete="off" />
            </label>
            <div id="project-filters" className="project-filters" role="group" aria-label="项目筛选">
              <button className="project-filter is-active" type="button" data-project-filter="all">全部</button>
              <button className="project-filter" type="button" data-project-filter="urgent">优先处理</button>
              <button className="project-filter" type="button" data-project-filter="needs_action">需处理</button>
              <button className="project-filter" type="button" data-project-filter="running">运行中</button>
              <button className="project-filter" type="button" data-project-filter="deliverable">可交付</button>
              <button className="project-filter" type="button" data-project-filter="artifact_issue">文件/元数据异常</button>
            </div>
            <p id="project-count" className="project-count" aria-live="polite">暂无项目</p>
            <details id="project-batch-details" className="simple-advanced">
              <summary>高级批量操作</summary>
              <div className="project-batch-actions">
                <button id="select-analyzed-projects" className="ghost compact" type="button">选择已分析</button>
                <button id="clear-project-selection" className="ghost compact" type="button">清空</button>
                <button id="batch-start-projects" className="primary compact" type="button">批量入队</button>
              </div>
            </details>
            <p id="batch-project-status" className="status" aria-live="polite"></p>
            <div id="project-list" className="project-list"></div>
          </section>
        </aside>

        <section id="main-content" className="workspace" tabIndex="-1">
          <header className="topbar">
            <div>
              <p className="eyebrow">数模方舟工作台</p>
              <h2 id="project-title">等待上传赛题</h2>
              <p id="environment-status" className="environment-status" aria-live="polite">检测执行环境中</p>
              <p id="project-stage-summary" className="project-stage-summary hidden" aria-live="polite"></p>
              <div id="project-stage-progress" className="project-stage-progress hidden" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
                <span></span>
              </div>
            </div>
            <div className="topbar-actions">
              <div id="project-next-action-wrap" className="topbar-next-action hidden">
                <button id="project-next-action" className="primary compact" type="button">下一步</button>
                <span id="project-next-action-reason" className="topbar-next-action-reason hidden"></span>
              </div>
              <button id="open-project-root" className="ghost compact hidden" type="button">打开项目文件夹</button>
              <button id="theme-toggle" className="theme-toggle" type="button" role="switch" aria-checked="false" aria-label="切换深色模式">
                <span className="theme-toggle-track" aria-hidden="true">
                  <span className="theme-toggle-thumb"></span>
                </span>
                <span id="theme-toggle-label">浅色</span>
              </button>
              <div id="health" className="health" data-status="checking" aria-live="polite">连接中</div>
            </div>
          </header>

          <div id="empty-state" className="empty-state">
            <h3>上传一个赛题包后，这里会显示自动分析结果。</h3>
            <p>系统会识别赛题、附件、格式规范，生成推荐选题、任务工作流和 LaTeX 论文骨架。</p>
          </div>

          <div id="analysis-view" className="analysis hidden">
            <nav className="module-tabs" aria-label="工作台模块" role="tablist">
              <button className="module-tab is-active" type="button" role="tab" aria-selected="true" data-module-tab="overview">概览</button>
              <button className="module-tab" type="button" role="tab" aria-selected="false" data-module-tab="problems">选题</button>
              <button className="module-tab" type="button" role="tab" aria-selected="false" data-module-tab="outputs">输出</button>
              <details className="module-more">
                <summary>更多</summary>
                <button className="module-tab" type="button" role="tab" aria-selected="false" data-module-tab="materials">材料</button>
                <button className="module-tab" type="button" role="tab" aria-selected="false" data-module-tab="paper">论文设置</button>
              </details>
            </nav>

            <section className="module-panel is-active" role="tabpanel" data-module-panel="overview">
              <section className="guide-panel" id="experience-guide" aria-live="polite">
                <div className="guide-main">
                  <span className="guide-kicker">下一步</span>
                  <h2 id="guide-title">上传赛题材料</h2>
                  <p id="guide-detail">先选择赛题压缩包或文件夹，系统会自动识别题目、附件和推荐选题。</p>
                  <p id="guide-outcome" className="guide-outcome" hidden>上传完成后，会自动进入赛题分析。</p>
                </div>
                <div className="guide-actions" id="guide-actions">
                  <button className="primary compact" type="button" data-guide-action="focus_upload">选择赛题</button>
                </div>
                <ol className="guide-steps" id="guide-steps">
                  <li data-status="current"><span>1</span><b>上传赛题</b></li>
                  <li><span>2</span><b>确认选题</b></li>
                  <li><span>3</span><b>自动求解</b></li>
                  <li><span>4</span><b>导出交付</b></li>
                </ol>
              </section>
              <section className="summary-strip">
                <div>
                  <span className="label">当前选题</span>
                  <strong id="recommended-problem">-</strong>
                </div>
                <div>
                  <span className="label">文档数</span>
                  <strong id="document-count">-</strong>
                </div>
                <div>
                  <span className="label">数据附件</span>
                  <strong id="data-count">-</strong>
                </div>
                <div>
                  <span className="label">状态</span>
                  <strong id="project-status">-</strong>
                </div>
              </section>
              <section className="panel wide">
                <div className="section-title">
                  <h2>流程状态</h2>
                </div>
                <div id="status-cards" className="status-grid"></div>
              </section>
              <section className="panel wide">
                <div className="section-title">
                  <h2>当前准备度</h2>
                </div>
                <div id="project-readiness" className="readiness-panel" aria-live="polite"></div>
              </section>
              <details className="advanced-fold">
                <summary>高级状态：并发、修复与交付检查</summary>
                <section className="panel wide">
                  <div className="section-title">
                    <h2>解题进度中心</h2>
                    <button id="refresh-growth-metrics" className="ghost" type="button">刷新</button>
                  </div>
                  <div id="growth-center" className="growth-center" aria-live="polite"></div>
                  <p id="growth-center-status" className="status" aria-live="polite"></p>
                </section>
                <section className="panel wide">
                  <div className="section-title">
                    <h2>交付质检</h2>
                    <button id="refresh-trust-center" className="ghost" type="button">刷新</button>
                  </div>
                  <div id="trust-center" className="trust-center" aria-live="polite"></div>
                  <p id="trust-center-status" className="status" aria-live="polite"></p>
                </section>
                <section className="panel wide">
                  <div className="section-title">
                    <h2>后台任务中心</h2>
                    <button id="refresh-auto-jobs" className="ghost" type="button">刷新</button>
                  </div>
                  <div id="auto-job-center" className="job-center" aria-live="polite"></div>
                </section>
              </details>
            </section>

            <section className="module-panel" role="tabpanel" data-module-panel="problems" hidden>
              <section className="panel wide">
                <div className="section-title">
                  <h2>选题分析</h2>
                </div>
                <p id="problem-selection-status" className="status" aria-live="polite"></p>
                <div id="problem-cards" className="problem-grid"></div>
              </section>
            </section>

            <section className="module-panel" role="tabpanel" data-module-panel="materials" hidden>
              <section className="panel wide">
                <div className="section-title">
                  <h2>自动工作流</h2>
                </div>
                <div id="workflow" className="workflow"></div>
              </section>
              <section className="panel wide">
                <div className="section-title">
                  <h2>附件盘点</h2>
                </div>
                <div id="inventory" className="inventory"></div>
              </section>
            </section>

            <section className="module-panel" role="tabpanel" data-module-panel="paper" hidden>
              <section className="panel wide">
                <div className="section-title">
                  <h2>论文设置</h2>
                </div>
                <form id="paper-options-form" className="settings-grid">
                  <label>
                    <span className="label">格式模板</span>
                    <select id="template-select" className="text-input"></select>
                  </label>
                  <label>
                    <span className="label">正文目标页数</span>
                    <input id="target-body-pages" className="text-input" type="number" min="1" max="100" placeholder="例如 25" />
                  </label>
                  <button id="save-paper-options" className="primary compact" type="submit">保存论文设置</button>
                </form>
                <form id="template-upload-form" className="template-upload">
                  <label>
                    <span className="label">新增模板名称</span>
                    <input id="template-name-input" className="text-input" type="text" placeholder="例如 竞赛官方模板" />
                  </label>
                  <label className="drop-zone compact-zone" htmlFor="template-file-input">
                    <span id="template-file-label">选择 LaTeX 模板或 Word/PDF 格式说明</span>
                    <input id="template-file-input" name="file" type="file" accept=".tex,.docx,.pdf,.txt,.md" />
                  </label>
                  <div className="inline-actions">
                    <button id="upload-template" className="primary compact" type="submit">上传模板</button>
                    <button id="delete-template" className="ghost" type="button">删除所选模板</button>
                  </div>
                </form>
                <p id="paper-options-status" className="status" aria-live="polite"></p>
                <p id="template-status" className="status" aria-live="polite"></p>
                <p id="template-hint" className="status template-hint"></p>
              </section>

              <section className="panel wide">
                <div className="section-title">
                  <h2>模型辅助</h2>
                </div>
                <form id="model-assistant-form" className="model-assistant-form">
                  <label>
                    <span className="label">指定问题</span>
                    <select id="assist-problem-select" className="text-input"></select>
                  </label>
                  <label>
                    <span className="label">模型或算法</span>
                    <input id="assist-model-input" className="text-input" type="text" placeholder="例如 LSTM、GM(1,1)、TOPSIS、整数规划" />
                  </label>
                  <label className="full-row">
                    <span className="label">补充目标</span>
                    <textarea id="assist-goal-input" className="text-area" rows="3" placeholder="例如：用于问题 2 的预测，生成可写入模型建立和模型求解的方案"></textarea>
                  </label>
                  <button id="run-model-assistant" className="primary compact" type="submit">生成模型辅助方案</button>
                </form>
                <p id="model-assistant-status" className="status" aria-live="polite"></p>
                <div id="model-assistant-progress" className="workflow-progress hidden" aria-live="polite"></div>
              </section>
            </section>

            <section className="module-panel" role="tabpanel" data-module-panel="outputs" hidden>
              <section className="panel wide">
                <div className="section-title">
                  <h2>执行操作</h2>
                  <div className="action-row">
                    <button id="run-auto-workflow" className="primary compact" type="button">开始一键生成</button>
                    <button id="resume-auto-workflow" className="ghost" type="button">继续</button>
                  </div>
                </div>
                <details className="simple-advanced output-advanced-actions">
                  <summary>高级操作</summary>
                  <div className="action-row">
                    <button id="run-modeling" className="ghost hidden" type="button">运行基线建模</button>
                    <button id="run-specialized" className="ghost hidden" type="button">运行专项建模</button>
                    <button id="cancel-auto-workflow" className="ghost" type="button">中断流程</button>
                    <button id="refresh-diagnostics" className="ghost" type="button">刷新诊断/性能</button>
                    <button id="generate-skill-report" className="ghost" type="button">生成技能库/规范检查</button>
                    <button id="generate-code-graph" className="ghost" type="button">生成代码图谱</button>
                    <button id="fill-paper" className="ghost hidden" type="button">回填论文</button>
                    <button id="compile-latex" className="ghost" type="button">编译 LaTeX</button>
                    <button id="review-paper" className="ghost" type="button">审查论文</button>
                    <button id="run-llm-analysis" className="ghost hidden" type="button">大模型分析</button>
                  </div>
                </details>
                <div className="status-stack">
                  <p id="modeling-status" className="status" aria-live="polite"></p>
                  <p id="specialized-status" className="status" aria-live="polite"></p>
                  <p id="auto-workflow-status" className="status" aria-live="polite"></p>
                  <div id="auto-workflow-progress" className="workflow-progress hidden" aria-live="polite"></div>
                  <p id="diagnostics-status" className="status" aria-live="polite"></p>
                  <p id="skill-report-status" className="status" aria-live="polite"></p>
                  <p id="code-graph-status" className="status" aria-live="polite"></p>
                  <p id="paper-fill-status" className="status" aria-live="polite"></p>
                  <p id="compile-status" className="status" aria-live="polite"></p>
                  <p id="paper-review-status" className="status" aria-live="polite"></p>
                  <p id="llm-analysis-status" className="status" aria-live="polite"></p>
                  <div id="llm-analysis-progress" className="workflow-progress hidden" aria-live="polite"></div>
                </div>
              </section>

              <details className="advanced-fold output-advanced-panels">
                <summary>高级检查：修复与交付</summary>
                <section className="panel wide">
                  <div className="section-title">
                    <h2>自动修复中心</h2>
                    <button id="refresh-repair-center" className="ghost" type="button">刷新修复</button>
                  </div>
                  <div id="repair-center" className="repair-center" aria-live="polite"></div>
                  <p id="repair-center-status" className="status" aria-live="polite"></p>
                </section>

                <section className="panel wide">
                  <div className="section-title">
                    <h2>交付就绪中心</h2>
                    <button id="refresh-delivery-readiness" className="ghost" type="button">刷新交付</button>
                  </div>
                  <div id="delivery-center" className="delivery-center" aria-live="polite"></div>
                  <p id="delivery-readiness-status" className="status" aria-live="polite"></p>
                </section>
              </details>

              <section className="panel wide">
                <div className="section-title">
                  <h2>生成文件</h2>
                </div>
                <div id="artifacts" className="artifacts"></div>
              </section>
            </section>
          </div>
        </section>
      </main>
      <div id="toast-region" className="toast-region" aria-live="polite" aria-atomic="true"></div>
      <LegacyRuntime />
    </>
  );
}
