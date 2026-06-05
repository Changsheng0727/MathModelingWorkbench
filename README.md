# Math Modeling Workbench

Math Modeling Workbench 是一个面向数学建模竞赛的本地智能工作台。它的目标不是替你“凭空写答案”，而是把赛题材料整理、选题分析、代码求解、结果回填、论文生成、论文审查和文件导出串成一条可追踪的工作流。

一句话概括：

```text
上传赛题包 -> 分析题目和附件 -> 选择赛题 -> 生成并运行求解代码 -> 回填图表和数值 -> 生成论文与支撑材料
```

## 适合谁使用

- 正在参加数学建模竞赛，希望快速完成赛题拆解、建模方案设计和论文初稿的队伍。
- 需要把多个题目、附件数据、代码结果和论文文件统一管理的个人或小组。
- 希望让大模型参与建模，但又要求关键数值来自实际代码运行结果的用户。
- 希望生成 PDF、Word、LaTeX、代码、图表和支撑材料包的一体化工具使用者。

## 主要功能

### 赛题材料整理

软件支持上传 `.zip/.pdf/.docx/.xlsx/.csv` 文件，也支持直接选择包含题面、附件、数据和格式说明的文件夹。上传后会自动整理原始材料，识别题目文档、数据附件、表格结构和文件清单。

### 赛题分析与选题

系统会分析 A/B/C 等候选题，尽量识别每道题的子问题、附件数据、建模难度、可计算性和论文可写性。配置 API Key 后，大模型会参与读取题目相关文件，辅助判断哪个题目更适合继续求解。

### LLM+代码自动求解

自动流程会先让大模型根据当前赛题和附件生成求解方案，再生成项目内的 Python 求解脚本并运行。代码不是预先写死的专题模板，而是根据当前赛题当场生成、当场执行。

运行过程中会保留求解规范、运行日志、自动修复记录、结果表、图像和 manifest，方便复核每个子问题是否真正完成。

### 论文生成与结果回填

论文不会只写笼统模板。系统会把代码跑出的具体数值、表格和图片回填到正文对应位置，并在正文完成后再生成摘要。摘要会尽量写清楚每一问使用的具体模型、算法和得到的核心结果。

论文标题也会根据解题方法和正文内容生成，而不是固定模板标题。

### 模型检验与审查

模型检验部分需要基于代码运行结果回填，包含具体指标、表格、图像和解释。软件会审查论文结构、图表、公式、编译日志、结果来源和明显模板化内容，帮助减少“看起来完整但没有真实计算支撑”的问题。

### 流程进度与断点继续

长流程会显示当前阶段、运行进度、LLM 生成内容、错误日志和可查看的输出文件。自动论文生成支持中断与继续：主动中断后可以继续生成，意外中断后也可以尝试从上次阶段恢复。

### 文件管理

生成文件会集中显示在“输出”区域。用户可以点击下载文件，也可以点击“打开位置”直接打开对应文件夹；当前项目也可以一键打开项目文件夹。

## 一键流程会做什么

点击“LLM+代码一键完成”后，软件通常会依次完成：

1. 读取赛题材料和附件数据。
2. 分析题目结构、子问题和可用数据。
3. 确认当前选择的题目。
4. 生成解题方案和代码求解规范。
5. 生成并运行 Python 求解脚本。
6. 检查每个子问题是否有结果、表格和图像。
7. 将计算结果回填到论文。
8. 根据正文生成标题、摘要、关键词和结论。
9. 编译 LaTeX，导出 PDF；可用时导出 Word。
10. 生成论文审查报告和支撑材料包。

## 主要输出文件

每个项目都会保存在自己的项目文件夹中。常见输出包括：

- `artifacts/analysis_report.md`：赛题分析报告。
- `artifacts/llm_problem_analysis.md`：大模型赛题分析记录。
- `artifacts/llm_full_solution.md`：完整题解与建模方案记录。
- `artifacts/computed_solver_spec.md`：代码求解规范。
- `code/run_computed_solution.py`：自动生成的求解脚本。
- `results/computed_manifest.json`：结果清单，记录表格、图像、指标和分问题结果。
- `results/computed_summary.md`：计算结果摘要。
- `paper/main.tex`：论文 LaTeX 源文件。
- `paper/main.pdf`：论文 PDF。
- `paper/main.docx`：论文 Word，依赖本机 Pandoc 可用。
- `artifacts/auto_workflow_report.md`：自动流程运行报告。
- `artifacts/paper_review.md`：论文审查报告。
- `artifacts/support_materials.zip`：支撑材料包。

## Windows 用户如何使用

推荐下载 Release 中的安装包：

```text
MathModelingWorkbench-Setup.exe
```

安装后可以从桌面快捷方式或开始菜单启动。软件会在本机打开一个桌面窗口，并自动启动内置后端服务，普通用户不需要手动运行命令行。

如果不想安装，也可以下载绿色版：

```text
MathModelingWorkbench-Windows-x64.zip
```

解压后双击其中的 `MathModelingWorkbench.exe` 即可使用。

详细安装说明见 [WINDOWS_CLIENT.md](WINDOWS_CLIENT.md)。

## 需要准备什么

### API Key

自动解题、LLM 分析、论文生成和模型辅助需要用户在软件左侧“AI 设置”中填写自己的 API Key、Base URL 和模型名称。没有配置 API Key 时，软件不会运行 LLM 自动解题流程。

### 文档工具

PDF 和 Word 导出可能依赖本机已有的文档工具：

- Pandoc：用于 Word 导出和部分文档转换。
- XeLaTeX / MiKTeX / TeX Live：用于 PDF 编译。

客户端会尝试检测缺失依赖；在支持 `winget` 的 Windows 环境中，可尝试后台下载安装。若网络受限或安装器需要人工确认，仍可能需要用户手动安装。

### 数据保存位置

安装版默认把项目、模板、API 设置和日志保存到：

```text
%LOCALAPPDATA%/MathModelingWorkbench/data
```

升级安装通常会保留该目录，因此历史项目和 API 设置不会被覆盖。

## 项目工作区说明

每次上传赛题都会生成一个独立项目。项目内通常包含：

- `raw/`：原始赛题材料。
- `artifacts/`：分析报告、LLM 记录、审查报告和支撑文件。
- `code/`：自动生成或辅助生成的求解代码。
- `results/`：程序运行得到的表格、图像和结果清单。
- `paper/`：论文源文件、PDF 和 Word。

在界面中打开项目后，可以在“生成文件”区域查看这些文件，也可以直接打开所在文件夹。

## 当前边界

- 软件能提升赛题理解、建模组织和论文生成效率，但不能保证每道题都一次性求解成功。
- 所有自动生成的模型、代码、论文和结论都建议人工复核，尤其是约束条件、公式、图表解释和最终数值。
- 如果题目附件格式特殊、数据缺失严重，可能需要先手动整理数据。
- 代码求解会尝试自动修复失败脚本，但复杂优化、仿真或专用求解器问题仍可能需要人工介入。
- 未做代码签名的安装包首次运行时，Windows 可能出现安全提示。

## 开发者快速启动

如果你想从源码运行本地 Web 版本：

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

然后打开：

```text
http://127.0.0.1:8765
```

如果修改了前端，需要重新构建静态页面：

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench\frontend
npm install
npm run build
```

重新生成 Windows 安装包：

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows-installer.ps1
```

## 交流与贡献

欢迎在 GitHub 仓库提交 Issue 或 Pull Request。你可以反馈 Bug、提出新功能建议、补充数学建模流程、改进论文模板、优化前端体验或完善打包方式。

联系方式：

```text
2821452633@qq.com
```

提交 Issue 时建议附上软件版本、系统版本、复现步骤、错误截图或日志路径。提交 PR 时建议说明改动目标、影响范围和已完成的验证。
