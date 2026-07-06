# 数模方舟 ModelArk

<p align="center">
  <img src="frontend/app/icon.svg" alt="ModelArk logo" width="96" height="96">
</p>

<p align="center">
  <strong>面向数学建模竞赛的本地智能工作台</strong>
</p>

<p align="center">
  上传赛题材料，确认选题，让大模型规划代码求解，运行结果回填论文，最后导出 PDF、Word 和支撑材料包。
</p>

<p align="center">
  <a href="https://github.com/Changsheng0727/MathModelingWorkbench/releases">下载客户端</a>
  ·
  <a href="docs/user_manual.pdf">使用手册 PDF</a>
  ·
  <a href="docs/user_manual.tex">使用手册 LaTeX</a>
  ·
  <a href="WINDOWS_CLIENT.md">Windows 客户端说明</a>
  ·
  <a href="https://github.com/Changsheng0727/MathModelingWorkbench/issues">反馈问题</a>
</p>

<p align="center">
  <img alt="Windows" src="https://img.shields.io/badge/Windows-client-blue">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12+-3776AB">
  <img alt="Next.js" src="https://img.shields.io/badge/Frontend-Next.js-black">
  <img alt="Local first" src="https://img.shields.io/badge/Local--first-workflow-0f766e">
</p>

## 目录

- [项目定位](#项目定位)
- [功能一览](#功能一览)
- [快速开始](#快速开始)
- [典型工作流](#典型工作流)
- [界面导览](#界面导览)
- [输出文件](#输出文件)
- [安装与依赖](#安装与依赖)
- [从源码运行](#从源码运行)
- [项目结构](#项目结构)
- [常见问题](#常见问题)
- [路线图](#路线图)
- [贡献](#贡献)
- [联系方式](#联系方式)
- [许可证](#许可证)
- [致谢](#致谢)

## 项目定位

数模方舟 ModelArk 不是一个“自动交卷机器”，而是一个把数学建模竞赛中的材料整理、题目分析、代码求解、论文生成和交付检查串起来的本地工作台。

它适合以下用户：

- 正在参加数学建模竞赛，需要快速整理题面、附件和论文材料的队伍。
- 希望大模型参与建模，但要求论文中的关键数值来自实际代码运行结果的用户。
- 需要统一管理赛题、代码、图表、论文、日志和支撑材料包的个人或小组。
- 希望减少重复操作，把“选题、求解、回填、编译、审查”连成一条清晰流程的用户。

核心流程：

```text
上传赛题材料 -> 分析题目和附件 -> 确认选题 -> 自动求解 -> 生成论文 -> 导出交付文件
```

## 功能一览

| 能力 | 说明 |
| --- | --- |
| 赛题材料整理 | 支持上传压缩包、题面文档、Excel/CSV 数据，也支持文件夹上传。 |
| 选题分析 | 识别候选题、子问题、附件数据、建模难度、计算可行性和论文可写性。 |
| 大模型规划 | 根据当前赛题和附件生成求解方案、代码规范和论文思路。 |
| 代码求解 | 让大模型当场生成 Python 求解脚本，在本地运行并保存表格、图像、指标和日志。 |
| 自动修复 | 代码运行失败时读取错误日志和上下文，尝试让大模型修复后继续运行。 |
| 结果回填 | 将代码输出的具体数值、表格和图片回填到论文对应位置。 |
| 论文生成 | 生成标题、摘要、正文、模型检验、结论、LaTeX、PDF 和可选 Word。 |
| 断点继续 | 主动中断或意外失败后，可以从已有阶段继续生成。 |
| 交付检查 | 汇总论文、代码、结果、审查报告和支撑材料包。 |
| 简化界面 | 默认只保留上传、配置、选题、一键生成和生成文件，高级功能折叠收纳。 |

## 快速开始

### 1. 下载 Windows 客户端

从 [GitHub Releases](https://github.com/Changsheng0727/MathModelingWorkbench/releases) 下载：

```text
MathModelingWorkbench-Setup.exe
```

双击安装后，从桌面快捷方式或开始菜单启动。

如果不想安装，可以下载绿色版：

```text
MathModelingWorkbench-Windows-x64.zip
```

解压后双击 `MathModelingWorkbench.exe`。

### 2. 配置大模型接口

打开软件后，在左侧 `大模型设置` 中填写 API Key，然后点击：

```text
保存 -> 测试连接
```

接口地址、模型名称和求解策略位于 `高级模型设置`。普通用户保持默认即可。

### 3. 上传赛题

在左侧 `上传赛题` 中点击：

```text
选择赛题文件或压缩包 -> 开始分析
```

推荐上传官方赛题压缩包，或把题面、附件、格式说明放进同一个文件夹后上传。

### 4. 跟随下一步

主界面的 `下一步` 面板会提示你当前应该做什么：

```text
确认选题 -> 开始一键生成 -> 查看生成文件
```

大多数情况下，只需要按这个提示走。

## 典型工作流

点击输出页的 `开始一键生成` 后，软件会按顺序尝试：

1. 读取赛题材料和附件数据。
2. 分析题目结构、子问题和可用数据。
3. 确认当前选择的题目。
4. 生成解题方案和代码求解规范。
5. 生成并运行 Python 求解脚本。
6. 检查每个子问题是否有结果、表格和图像。
7. 将计算结果回填到论文。
8. 根据正文生成标题、摘要、关键词和结论。
9. 编译 LaTeX，导出 PDF。
10. 在 Pandoc 可用时导出 Word。
11. 生成论文审查报告和支撑材料包。

重要原则：

- 先完成代码求解，再撰写论文。
- 每个子问题都应有对应结果、表格或图像。
- 摘要在正文完成后生成，并尽量写明每一问的模型、算法和核心结果。
- 模型检验部分需要基于代码运行结果，而不是模板化说明。
- 自动生成内容需要人工复核，尤其是约束、公式、图表解释和最终结论。

## 界面导览

| 区域 | 普通用户需要关注什么 |
| --- | --- |
| 上传赛题 | 选择赛题文件或压缩包，点击开始分析。 |
| 大模型设置 | 填写 API Key，保存并测试连接。 |
| 项目 | 打开历史项目，或搜索项目。 |
| 概览 | 查看下一步、当前选题、材料数量和流程状态。 |
| 选题 | 查看候选题，确认最终题目。 |
| 输出 | 开始一键生成、继续中断流程、查看生成文件。 |
| 更多 | 进入材料盘点、论文设置、模型辅助等进阶功能。 |

高级功能不会消失，只是默认折叠在 `高级上传选项`、`高级模型设置`、`高级操作`、`高级检查` 等入口中。

## 输出文件

每个项目都有独立目录。常见输出如下：

| 文件 | 用途 |
| --- | --- |
| `artifacts/analysis_report.md` | 赛题分析报告。 |
| `artifacts/llm_problem_analysis.md` | 大模型赛题分析记录。 |
| `artifacts/llm_full_solution.md` | 完整题解与建模方案记录。 |
| `artifacts/computed_solver_spec.md` | 代码求解规范。 |
| `code/run_computed_solution.py` | 自动生成的求解脚本。 |
| `results/computed_manifest.json` | 结果清单，记录表格、图像、指标和分问题结果。 |
| `results/computed_summary.md` | 计算结果摘要。 |
| `paper/main.tex` | 论文 LaTeX 源文件。 |
| `paper/main.pdf` | 论文 PDF。 |
| `paper/main.docx` | 论文 Word，依赖 Pandoc。 |
| `artifacts/auto_workflow_report.md` | 自动流程运行报告。 |
| `artifacts/paper_review.md` | 论文审查报告。 |
| `artifacts/support_materials.zip` | 支撑材料包。 |

界面中的 `生成文件` 区域可以直接查看这些文件，也可以打开对应文件夹。

## 安装与依赖

### 用户侧

安装版默认数据目录：

```text
%LOCALAPPDATA%\MathModelingWorkbench\data
```

升级安装通常会保留该目录，因此历史项目和 API 设置不会被覆盖。

PDF 和 Word 导出可能依赖本机已有文档工具：

- Pandoc：用于 Word 导出和部分文档转换。
- XeLaTeX、MiKTeX 或 TeX Live：用于 PDF 编译。

客户端会尝试检测缺失依赖。在支持 `winget` 的 Windows 环境中，软件可尝试后台下载安装。若网络受限、权限不足或安装器需要人工确认，仍可能需要用户手动安装。

### 打包产物

| 文件 | 说明 |
| --- | --- |
| `release/MathModelingWorkbench-Setup.exe` | Windows 安装包。 |
| `release/MathModelingWorkbench-Windows-x64.zip` | 绿色便携版。 |
| `dist/MathModelingWorkbench/MathModelingWorkbench.exe` | 本地调试版可执行文件。 |

详细说明见 [WINDOWS_CLIENT.md](WINDOWS_CLIENT.md)。

## 从源码运行

### 后端

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765
```

### 前端

修改 `frontend/` 后需要重新构建静态页面：

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench\frontend
npm install
npm run build
```

### Windows 打包

```powershell
cd E:\AI_MATHMODELING\ModelingWorkbench
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows-installer.ps1
```

脚本会构建 Next.js 前端、复制静态资源、打包 Python 桌面客户端，并生成安装包和绿色版压缩包。

## 项目结构

```text
ModelingWorkbench/
  app/                      FastAPI 后端、服务逻辑、静态前端产物
  client/                   Windows 桌面客户端入口
  frontend/                 Next.js 前端源码
  docs/                     使用说明 LaTeX 与 PDF
  data/                     本地项目、设置和模板，默认不提交
  release/                  打包产物，默认不提交
  build-windows-installer.ps1
  WINDOWS_CLIENT.md
  README.md
```

单个赛题项目通常包含：

```text
project/
  raw/        原始赛题材料
  artifacts/ 分析报告、LLM 记录、审查报告
  code/       自动生成或辅助生成的代码
  results/    表格、图像、指标和 manifest
  paper/      LaTeX、PDF、Word 论文文件
```

## 常见问题

### 为什么一键生成失败？

常见原因包括 API Key 不可用、网络连接失败、题面无法解析、附件数据格式特殊、生成的求解脚本报错，或本机缺少 LaTeX/Pandoc。优先点击 `继续`，让软件读取错误日志并尝试自动修复。

### 为什么 Word 没有生成？

Word 导出通常依赖 Pandoc。请检查 Pandoc 是否安装、论文 LaTeX 是否已生成、导出日志是否有错误。

### 为什么 PDF 没有生成？

PDF 编译通常依赖 XeLaTeX、MiKTeX 或 TeX Live。请查看编译日志中是否存在 `LaTeX Error`、`Undefined control sequence`、图片路径缺失等问题。

### 自动生成的论文可以直接提交吗？

不建议直接提交。软件可以生成结构化初稿、代码结果和支撑材料，但正式提交前应人工复核模型假设、约束条件、公式、图表解释、摘要和最终结论。

## 路线图

- 更稳定的 LLM 断点续跑和错误上下文回读。
- 更细粒度的子问题完成度检查。
- 更丰富的论文模板与竞赛格式预设。
- 更清晰的图表回填和模型检验结果展示。
- 安装包代码签名和更标准的安装器方案。

欢迎通过 [Issues](https://github.com/Changsheng0727/MathModelingWorkbench/issues) 提出建议。

## 贡献

欢迎提交 Issue 或 Pull Request。你可以帮助改进：

- 赛题解析和附件识别；
- 自动求解和代码修复逻辑；
- 论文生成、摘要生成和公式排版；
- 前端体验和客户端打包；
- 文档、模板和示例项目。

建议提交 Issue 时附上：

- 软件版本；
- Windows 系统版本；
- 复现步骤；
- 错误截图；
- 项目中的错误日志路径。

建议提交 PR 时说明：

- 改动目标；
- 影响范围；
- 已完成的验证；
- 是否会影响既有项目数据。

## 联系方式

维护者邮箱：

```text
2821452633@qq.com
```

也欢迎直接在 GitHub 提交 Issue 或 PR。

## 许可证

当前仓库尚未附加明确的开源许可证。若需要复制、分发或用于商业场景，请先联系维护者确认授权方式。

## 致谢

README 结构参考了优秀开源项目常见写法，并借鉴了以下项目对首屏信息、快速开始、目录和贡献说明的组织方式：

- [Best-README-Template](https://github.com/othneildrew/Best-README-Template)
- [awesome-readme](https://github.com/matiassingers/awesome-readme)

感谢所有愿意反馈问题、提交 PR 和改进数学建模工作流的用户。
