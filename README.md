# Math Modeling Workbench

## Rust 后端重构

项目已新增 `rust-backend/`，作为 Rust 主后端的迁移入口。当前 Rust 服务已承接静态资源服务、健康检查、环境检测、LLM 设置、模板管理、项目列表、项目详情、单文件/文件夹上传、项目下载、支撑材料打包和 LaTeX 编译等稳定接口；自动解题、LLM 分析、结果回填和论文审查等复杂流程先通过受控 Python 兼容桥接保留既有能力，后续可逐步把内部实现迁移为 Rust 模块。

运行 Rust 后端：

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench
.\start-rust-server.ps1
```

打开 Rust 客户端模式：

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench
.\start-rust-client.ps1
```

或直接运行：

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench
cargo run --manifest-path .\rust-backend\Cargo.toml
```

默认地址仍为：

```text
http://127.0.0.1:8765
```

如需更换端口：

```powershell
$env:MODELING_WORKBENCH_PORT="8876"
cargo run --manifest-path .\rust-backend\Cargo.toml
```

迁移原则：

- Rust 负责 HTTP API、文件系统安全边界、设置、项目元数据、上传下载、编译与打包等基础设施。
- Python 兼容层只用于尚未迁移的重型算法流程，入口由 Rust 统一调度。
- 前端 `/api/...` 路径保持兼容，因此现有页面无需改动即可访问 Rust 后端。
- `rust-backend/target/` 已加入 `.gitignore`，只保留源码和 `Cargo.lock`。

Rust 后端优化参考：

- 参考 `tokio-rs/axum` 官方示例中的静态文件服务、multipart 上传、请求体限制与 tracing 组织方式，后端已把路由构建拆为 `build_router`，并补充 `TraceLayer`、`RequestBodyLimitLayer`、`DefaultBodyLimit::disable()` 与 gzip 压缩层。
- 参考 `tower-http` 的服务中间件设计，静态资源、JSON API 和下载接口统一经过可组合 HTTP 层处理，便于后续继续加入鉴权、CORS、限流或桌面客户端专用头。
- 结合 Tauri 类本地客户端项目的“Rust 管基础设施、Web 管交互界面”思路，当前仍保持轻量本地 Web UI，不引入额外桌面框架；后续若需要安装包、系统托盘、自动更新，可再迁移到 Tauri。
- 上传与解压流程增加了 550 MB 请求体上限、500 MB 单文件/文件夹/Zip 解压上限、Zip 文件数量上限和路径穿越检查；下载响应补充 UTF-8 文件名兼容的 `Content-Disposition` 与 `X-Content-Type-Options: nosniff`。
- 项目元数据和设置 JSON 改为先写临时文件再替换目标文件，减少运行中断造成半写入文件的概率。

本项目是一个数学建模竞赛智能工作台 MVP。它把赛题包上传、赛题解析、选题分析、工作流生成和论文骨架生成串成一个本地可运行应用。

## 运行

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765
```

## 前端

前端源码已迁移到 `frontend/`，使用 Next.js 静态导出。构建后产物会同步到 `app/static/`，仍由 FastAPI 或 Rust 后端通过 `/` 与 `/static/...` 托管，因此桌面客户端和本地 Web 入口保持兼容，不需要额外启动 Node 服务。

开发或重新生成静态前端：

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench\frontend
npm install
npm run build
```

Windows 安装包构建脚本会自动执行 Next.js 前端构建。构建机器需要安装 Node.js/npm；最终用户运行已打包的 `.exe` 不需要安装 Node.js。

## 桌面客户端

如果希望像普通 Windows 客户端一样启动，可以运行：

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench
.\start-client.ps1
```

也可以直接双击项目根目录下的 `start-client.bat`。

该脚本会自动寻找可用端口、启动 FastAPI 后端，并打开桌面窗口。首次使用原生窗口前可安装客户端依赖：

```powershell
python -m pip install -r requirements-client.txt
```

若未安装 `pywebview`，启动器会自动退回到浏览器打开，但后端仍由客户端脚本托管。需要打包为 exe 时运行：

```powershell
.\build-client.ps1
```

生成文件位于 `dist\MathModelingWorkbench\MathModelingWorkbench.exe`。
打包后的客户端会在 exe 同级目录使用 `data/` 保存项目、模板和本地设置，不会把当前开发目录中的历史项目打进安装包。

## 当前能力

- 上传 `.zip/.pdf/.docx/.xlsx/.csv` 赛题材料，或直接选择包含题面、附件、数据和格式说明的整个文件夹。
- 自动解压或保留文件夹相对路径，并盘点文档、附件、字段和表结构。
- 提取 PDF、Word 文本，识别 A/B/C 赛题与子问题。
- 生成选题分析、推荐题目和任务工作流。
- 上传后可由大模型当场完成赛题分析、选题、建模求解方案和论文撰写；未配置 API Key 时禁止运行自动流程。
- 可勾选“上传后由大模型自动选题、生成并运行代码、回填结果、撰写论文并审查”，系统会串联 LLM 全流程题解、代码求解规范、项目内 Python 脚本执行、结果 manifest、论文回填、PDF 编译、论文审查和支撑材料打包。
- 输出 `analysis_report.md`、`outline.md`、`model_plan.md` 和 `paper/main.tex`。
- 自动流程不会运行旧的本地基线模型或专项建模脚本，而是由 LLM 当场生成求解规范，后端根据规范生成并运行项目内求解脚本，输出 `results/computed_manifest.json`、`results/computed_summary.md` 与回填后的 `paper/main.tex`。
- 后端已集成 GitHub 数学建模与论文写作技能库摘要，自动流程会输出 `artifacts/backend_skill_research.md`，并把精选工作流规则注入 LLM 解题上下文。
- 打包支撑材料。
- 一键编译 LaTeX 论文骨架，输出 `paper/main.pdf`。
- 一键自动完成完整题解流程，输出 `artifacts/auto_workflow_report.md` 作为自动运行报告。
- 在左侧 AI 设置中填写 OpenAI API Key、Base URL 和模型名；后端只向前端返回脱敏后的 Key 状态。

## 建模执行模块

当前版本默认采用“LLM 当场分析 + 代码求解执行 + 结果回填论文”的自动解题流程。系统先要求用户配置 API Key，再由大模型根据赛题、附件清单和论文方案生成结构化求解规范；后端根据该规范生成受控 Python 脚本 `code/run_computed_solution.py`，脚本只读取项目 `raw/`，只写入 `results/` 和 `artifacts/`，运行后生成 `results/computed_manifest.json`、`results/computed_summary.md`、结果表和图片。论文回填模块只引用这些可追溯结果，避免在正文和摘要中编造未计算数值。

旧的本地基线模型和专项建模接口仍作为隐藏调试能力保留，但不参与一键自动完成，也不会作为默认产品路径展示。

## AI 设置

前端左侧栏可以保存用户自己的 OpenAI API Key。默认 Base URL 为 `https://api.chshapi.org/v1`，默认模型为 `gpt-5.5`。设置会写入本地 `data/settings/llm.json`，不会进入项目目录、论文支撑材料包或 `/api/projects` 元数据。`GET /api/settings/llm` 只返回是否已配置、脱敏 Key、Base URL 和模型名；清除按钮会删除本地设置文件。

LLM 参与节点会生成以下文件：

- `artifacts/llm_problem_analysis.md`：上传赛题后的选题、建模路线和 workflow 建议。
- `artifacts/llm_full_solution.md`：LLM 自动流程生成的完整题解、模型方案和论文写作依据。
- `artifacts/computed_solver_spec.md`：LLM 生成的代码求解规范。
- `results/computed_manifest.json`：程序计算得到的表格、图片、指标和分问题结果清单。
- `results/computed_summary.md`：可直接用于论文回填核对的计算结果摘要。
- `artifacts/llm_paper_latex.md`：LLM 生成 LaTeX 论文的记录。

默认模型为 `gpt-5.5`。前端“LLM+代码一键完成”必须在补填 API Key 后使用。

## GitHub 技能库集成

后端提供一个只读技能库，用于吸收公开 GitHub 项目和竞赛官方规则中的数学建模、论文写作与审稿工作流思想。当前集成来源包括 COMAP 官方提交规则、MathModelAgent、LLM-MM-Agent、ModelingAgent、CUMCMThesis、mcmthesis、分文件 LaTeX 模板工作流、Datawhale 数学建模算法体系、MathModeling-skills 关卡化交付流程、优秀论文/资源索引、research-writing-skill 和 awesome-ai-research-writing-skill。系统只记录来源、许可证提示、集成理由和后端执行规则，不复制第三方代码、模板、优秀论文或大段文本。

后端还内置了题型-模型-结果-检验路由表，覆盖预测与时间序列、资源配置与调度优化、综合评价、多指标决策、分类聚类、机理仿真、小样本灰色系统、网络图论等常见赛题类型。上传题包后，分析器会给每道题附加 `method_routes`，LLM 选题、代码求解规范和论文审查会共同参考这些路由，要求每个子问题明确候选模型、程序输出表图和检验方式。

相关接口：

- `GET /api/skills/backend`：查看已集成的后端技能库、标准论文工作流和标准论文审查清单。
- `POST /api/projects/{project_id}/skills/report`：为当前项目生成 `artifacts/backend_skill_research.md` 与 JSON 报告。

一键自动完成时会先生成技能库报告，再把“标准数学建模论文生成规则”注入 `llm_solution` 上下文，用于强化选题、模型链、摘要固定格式、分问题重述/分析、模型建立与模型求解边界、图表描述分析结论、正文页数和审查边界。审稿器也会检查摘要是否包含“首先/随后/再/最后”的方法链、逐问题固定句式、模型建立分问题组织、模型求解图表同位展示、参考文献与附录支撑材料。

## 论文模板与正文页数

项目详情页提供“论文设置”区域。用户可以上传 `.tex` 格式模板，也可以上传官方只提供的 `.docx/.pdf/.txt/.md` 格式说明文档，并设置论文正文目标页数。正文页数只统计正文主体，不包含摘要页、目录页和附录；系统通过 LaTeX 标签 `page:body-start` 与 `page:appendix-start` 在编译后的 `paper/main.aux` 中计算正文页数。

自定义 LaTeX 模板推荐使用 `__BODY__` 占位符，系统会把“问题重述—问题分析—模型建立—模型求解—模型检验—附录”的完整内容插入该位置。模板也可使用细粒度占位符：`__TITLE__`、`__ABSTRACT__`、`__KEYWORDS__`、`__MODEL_TYPES__`、`__BODY_START__`、`__APPENDIX_START__`、`__RESTATEMENT__`、`__PROBLEM_ANALYSIS__`、`__SOLVING__`、`__VALIDATION__`、`__APPENDIX__`。若选择目标正文页数为 25，则论文审查会要求正文检测页数不少于 25 页，否则审查结果判为未通过并提示扩写方向。

当官方只提供 Word 模板、PDF 模板说明或纯文字格式要求时，系统不会把它们强制转换成可编译的 LaTeX 模板，而是作为“格式说明文档”处理：先提取其中的页边距、字体、标题层级、摘要、正文、图表公式、参考文献、附录、匿名提交等规则摘要，论文生成时继续使用内置 LaTeX 模板，并把规则写入 `artifacts/paper_fill_summary.md`、`artifacts/format_rules_summary.md` 与 `paper/main.tex` 顶部注释，便于后续人工核对或 LLM 审查。若需要完全复刻官方 Word 外观，可以先按这些规则手工制作一个带占位符的 `.tex` 模板再上传。

模板文件存放在本地 `data/settings/templates/`，不会进入项目目录或支撑材料包；项目自身只记录 `paper_options.template_id` 与 `paper_options.target_body_pages`。

## 指定模型辅助

项目详情页新增“模型辅助”模块。用户可以选择推荐题的整体问题或某个子问题，填写希望引入的模型或算法名称，例如 `LSTM`、`GM(1,1)`、`TOPSIS`、`整数规划`，并补充使用目标。后端会先通过公开学术接口检索该模型相关资料，再把检索摘要、赛题分析和 LLM 题解上下文一起发送给 LLM。

生成结果写入 `artifacts/llm_model_assistant.md` 和 `artifacts/llm_model_assistant.json`。报告会包含模型原理、数学形式、与指定问题的适配性、伪代码、Python 实现建议、应生成的图表、模型检验方案和论文写作落点。若没有配置 API Key，系统会保留检索结果并提示 LLM 未启用；若检索资料不足，报告会要求人工补充文献，避免伪造引用。

## 交流与贡献

如果你在使用过程中遇到问题、发现 Bug，或希望增加新的数学建模流程、模型算法、论文模板、打包方式和前端交互，欢迎在 GitHub 仓库提交 Issue 或 Pull Request。

也可以通过邮箱联系维护者：

```text
2821452633@qq.com
```

提交 Issue 时建议附上软件版本、运行系统、复现步骤、错误截图或日志路径；提交 PR 时建议说明改动目标、影响范围和已完成的验证。

## 后续扩展

- 扩展面向具体题型的模型代码生成，例如整数规划、聚类评价、多指标评价和仿真模型。
- 继续增强 LaTeX 回填质量，例如自动生成摘要最终版、图表交叉引用审查和更细的敏感性分析。
- 增加人工确认节点、联网数据源确认和多 Agent 并发任务。
