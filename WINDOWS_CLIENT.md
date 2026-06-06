# 数模方舟 ModelArk Windows 客户端安装与使用说明

数模方舟 ModelArk 已经支持打包为 Windows 桌面客户端。用户下载或复制安装包后，可以直接运行安装程序，安装完成后通过桌面快捷方式或开始菜单打开 `.exe` 使用。

## 交付文件

构建完成后会生成以下文件：

- 安装包：`release/MathModelingWorkbench-Setup.exe`
- 绿色便携版：`release/MathModelingWorkbench-Windows-x64.zip`
- 本地调试版 exe：`dist/MathModelingWorkbench/MathModelingWorkbench.exe`

推荐向普通用户分发 `MathModelingWorkbench-Setup.exe`。如果用户不希望安装，也可以解压便携版 zip 后双击其中的 `MathModelingWorkbench.exe`。

## 用户安装方式

1. 双击 `MathModelingWorkbench-Setup.exe`。
2. 安装程序会把客户端解压到 `%LOCALAPPDATA%/MathModelingWorkbench`。
3. 安装完成后会创建桌面快捷方式和开始菜单快捷方式。
4. 双击快捷方式即可启动软件。

客户端启动时会自动完成两件事：先在本机启动内置后端服务，再打开桌面窗口访问本地界面。用户不需要手动运行 Python、FastAPI 或命令行脚本。

首次启动时客户端还会在后台检测外部文档工具依赖：

- `Pandoc`：用于 Word 导出和旧版 DOC 文本解析。
- `XeLaTeX` / `MiKTeX`：用于 PDF 编译。

如果检测到缺失依赖，并且系统可用 `winget`，客户端会后台尝试下载安装对应组件；安装过程不会阻塞主界面。状态和日志保存在：

```text
%LOCALAPPDATA%/MathModelingWorkbench/data/client/dependency_status.json
%LOCALAPPDATA%/MathModelingWorkbench/data/client/dependency_install.log
```

如果用户不希望自动安装外部依赖，可在启动前设置环境变量：

```powershell
$env:MODELING_WORKBENCH_SKIP_DEP_INSTALL = "1"
```

## 数据保存位置

安装版默认把项目、模板、API 设置和日志保存在：

```text
%LOCALAPPDATA%/MathModelingWorkbench/data
```

升级安装时会保留已有 `data` 目录，因此用户原来的项目和 API 设置不会被覆盖。卸载脚本会删除安装目录，如果需要长期保留历史项目，应先备份该目录。

## 重新构建安装包

开发者在项目根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows-installer.ps1
```

脚本会自动安装桌面端构建依赖，使用 PyInstaller 打包客户端，并生成安装包和便携版压缩包。

从 Next.js 前端版本开始，构建安装包的机器还需要安装 Node.js/npm。打包脚本会自动进入 `frontend/` 安装前端依赖、构建静态页面，并把产物同步到 `app/static/`；最终安装后的用户电脑不需要 Node.js。

## 当前边界

客户端已经内置 Python 后端、前端页面、常用数据分析库、自动解题脚本执行入口以及 Word 导出所用的 Pandoc reference docx 模板。PDF 编译、Word 转换等能力仍依赖本机可用的 LaTeX、Pandoc 或相关办公文档工具；客户端会尝试自动检测并用 `winget` 安装缺失依赖，但若目标用户电脑没有 `winget`、网络受限或安装器需要人工确认，仍可能需要手动安装。

安装包目前未进行代码签名，首次运行时 Windows 可能出现安全提示。正式分发前建议申请代码签名证书，或后续迁移到 Inno Setup、NSIS、MSIX 等更标准的安装器方案。
