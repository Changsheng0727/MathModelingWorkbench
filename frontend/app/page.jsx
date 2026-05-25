import LegacyRuntime from "./LegacyRuntime";

export default function WorkbenchPage() {
  return (
    <>
      <main className="shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="mark">M</div>
            <div>
              <h1>数学建模工作台</h1>
              <p>赛题解析、选题分析、论文骨架生成</p>
            </div>
          </div>

          <section className="panel">
            <h2>上传赛题</h2>
            <form id="upload-form">
              <div className="upload-choices">
                <label className="drop-zone" htmlFor="file-input">
                  <span id="file-label">选择 zip、pdf、docx、xlsx 或 csv</span>
                  <input id="file-input" name="file" type="file" />
                </label>
                <label className="drop-zone" htmlFor="folder-input">
                  <span id="folder-label">选择包含全部赛题材料的文件夹</span>
                  <input id="folder-input" name="files" type="file" webkitdirectory="" directory="" multiple />
                </label>
              </div>
              <label className="check-row">
                <input id="auto-run-after-upload" type="checkbox" />
                <span>上传后跳过手动确认，直接按当前推荐题目运行一键流程</span>
              </label>
              <button className="primary" type="submit">开始分析</button>
            </form>
            <p id="upload-status" className="status"></p>
            <div id="upload-analysis-progress" className="workflow-progress hidden"></div>
          </section>

          <section className="panel">
            <h2>AI 设置</h2>
            <form id="llm-settings-form" className="settings-form">
              <label>
                <span className="label">OpenAI API Key</span>
                <input id="api-key-input" className="text-input" type="password" autoComplete="off" placeholder="sk-..." />
              </label>
              <label>
                <span className="label">Base URL</span>
                <input id="base-url-input" className="text-input" type="url" autoComplete="off" />
              </label>
              <label>
                <span className="label">模型</span>
                <input id="model-input" className="text-input" type="text" autoComplete="off" />
              </label>
              <div className="inline-actions">
                <button id="save-llm-settings" className="primary compact" type="submit">保存</button>
                <button id="clear-llm-settings" className="ghost" type="button">清除</button>
              </div>
            </form>
            <p id="llm-settings-status" className="status"></p>
          </section>

          <section className="panel">
            <div className="section-title">
              <h2>项目</h2>
              <button id="refresh-projects" className="ghost" type="button">刷新</button>
            </div>
            <div id="project-list" className="project-list"></div>
          </section>
        </aside>

        <section className="workspace">
          <header className="topbar">
            <div>
              <p className="eyebrow">Modeling Workbench</p>
              <h2 id="project-title">等待上传赛题</h2>
              <p id="environment-status" className="environment-status">检测执行环境中</p>
            </div>
            <div id="health" className="health">连接中</div>
          </header>

          <div id="empty-state" className="empty-state">
            <h3>上传一个赛题包后，这里会显示自动分析结果。</h3>
            <p>系统会识别赛题、附件、格式规范，生成推荐选题、任务工作流和 LaTeX 论文骨架。</p>
          </div>

          <div id="analysis-view" className="analysis hidden">
            <nav className="module-tabs" aria-label="工作台模块">
              <button className="module-tab is-active" type="button" data-module-tab="overview">概览</button>
              <button className="module-tab" type="button" data-module-tab="problems">选题</button>
              <button className="module-tab" type="button" data-module-tab="materials">材料</button>
              <button className="module-tab" type="button" data-module-tab="paper">论文</button>
              <button className="module-tab" type="button" data-module-tab="outputs">输出</button>
            </nav>

            <section className="module-panel is-active" data-module-panel="overview">
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
            </section>

            <section className="module-panel" data-module-panel="problems">
              <section className="panel wide">
                <div className="section-title">
                  <h2>选题分析</h2>
                </div>
                <p id="problem-selection-status" className="status"></p>
                <div id="problem-cards" className="problem-grid"></div>
              </section>
            </section>

            <section className="module-panel" data-module-panel="materials">
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

            <section className="module-panel" data-module-panel="paper">
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
                <p id="paper-options-status" className="status"></p>
                <p id="template-status" className="status"></p>
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
                <p id="model-assistant-status" className="status"></p>
                <div id="model-assistant-progress" className="workflow-progress hidden"></div>
              </section>
            </section>

            <section className="module-panel" data-module-panel="outputs">
              <section className="panel wide">
                <div className="section-title">
                  <h2>执行操作</h2>
                  <div className="action-row">
                    <button id="run-modeling" className="ghost hidden" type="button">运行基线建模</button>
                    <button id="run-specialized" className="ghost hidden" type="button">运行专项建模</button>
                    <button id="run-auto-workflow" className="primary compact" type="button">LLM+代码一键完成</button>
                    <button id="generate-skill-report" className="ghost" type="button">生成技能库/诚信门禁</button>
                    <button id="generate-code-graph" className="ghost" type="button">生成代码图谱</button>
                    <button id="fill-paper" className="ghost hidden" type="button">回填论文</button>
                    <button id="compile-latex" className="ghost" type="button">编译 LaTeX</button>
                    <button id="review-paper" className="ghost" type="button">审查论文</button>
                    <button id="run-llm-analysis" className="ghost hidden" type="button">LLM 分析</button>
                  </div>
                </div>
                <div className="status-stack">
                  <p id="modeling-status" className="status"></p>
                  <p id="specialized-status" className="status"></p>
                  <p id="auto-workflow-status" className="status"></p>
                  <div id="auto-workflow-progress" className="workflow-progress hidden"></div>
                  <p id="skill-report-status" className="status"></p>
                  <p id="code-graph-status" className="status"></p>
                  <p id="paper-fill-status" className="status"></p>
                  <p id="compile-status" className="status"></p>
                  <p id="paper-review-status" className="status"></p>
                  <p id="llm-analysis-status" className="status"></p>
                </div>
              </section>

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
      <LegacyRuntime />
    </>
  );
}
