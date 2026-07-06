from __future__ import annotations


ACTION_OUTCOMES: dict[str, str] = {
    "focus_llm": "保存并测试通过后，系统会开放一键求解。",
    "test_llm": "连接成功后，可以回到当前项目继续自动流程。",
    "focus_upload": "上传完成后，会自动分析题目、附件和推荐选题。",
    "focus_projects": "打开优先级最高的项目后，会显示当前下一步。",
    "open_problems": "确认题号后，后续代码求解和论文都会以该题为准。",
    "confirm_recommended_problem": "会保存为最终选题，并刷新下一步。",
    "start_auto": "会进入代码求解、图表生成、论文回填和审查流程。",
    "watch_auto": "会打开输出页，查看流式进度、日志和生成文件。",
    "resume_auto": "会读取上次错误和上下文，从中断处继续修复。",
    "cancel_auto": "会请求当前自动流程在安全点中断。",
    "open_outputs": "会切到输出页，集中查看论文、日志和结果文件。",
    "compile": "会尝试生成 PDF，并同步导出 Word。",
    "review": "会检查论文结构、图表、编译日志和结果一致性。",
    "refresh_delivery": "会重新检查论文、结果和支撑材料是否可交付。",
    "build_delivery_package": "会生成正式提交压缩包和清单。",
    "open_project_root": "会在系统文件管理器里打开项目目录。",
    "open_primary_output": "会打开最新输出文件所在文件夹。",
    "select_analyzed": "会批量勾选已分析项目，方便继续自动求解。",
    "batch_packages": "会为已就绪项目生成正式提交压缩包。",
    "autotune_capacity": "会按当前排队压力调整并发配置。",
    "repair_campaign": "会刷新失败诊断，并推动可续跑项目恢复生成。",
    "refresh_all": "会重新计算当前产品状态和后台任务。",
}


ACTION_PROGRESS: dict[str, str] = {
    "focus_llm": "正在定位大模型接口设置。",
    "test_llm": "正在测试大模型连接。",
    "focus_upload": "正在定位赛题上传入口。",
    "focus_projects": "正在定位项目列表。",
    "open_problems": "正在打开选题分析页。",
    "confirm_recommended_problem": "正在保存最终选题。",
    "start_auto": "正在启动自动求解流程。",
    "watch_auto": "正在打开输出页和流式进度。",
    "resume_auto": "正在从上次中断处继续生成。",
    "cancel_auto": "正在请求安全中断。",
    "open_outputs": "正在打开生成文件和日志。",
    "compile": "正在启动论文编译。",
    "review": "正在启动论文审查。",
    "refresh_delivery": "正在刷新交付检查。",
    "build_delivery_package": "正在生成交付压缩包。",
    "open_project_root": "正在打开项目文件夹。",
    "open_primary_output": "正在打开最新输出所在位置。",
    "select_analyzed": "正在选择已分析项目。",
    "batch_packages": "正在启动批量交付打包。",
    "autotune_capacity": "正在根据队列压力调整并发。",
    "repair_campaign": "正在刷新失败诊断并启动修复。",
    "refresh_all": "正在刷新项目、任务和交付状态。",
}


ACTION_SUCCESS: dict[str, str] = {
    "focus_llm": "已定位到大模型接口设置。",
    "test_llm": "已提交连接测试，请查看设置状态。",
    "focus_upload": "已定位到赛题上传入口。",
    "focus_projects": "已定位到项目列表。",
    "open_problems": "已打开选题分析页。",
    "confirm_recommended_problem": "已保存最终选题，后续流程会以该题为准。",
    "start_auto": "已触发自动求解，请在输出页查看进度。",
    "watch_auto": "已打开输出页，可查看流式进度。",
    "resume_auto": "已触发继续生成，请查看输出页进度。",
    "cancel_auto": "已请求中断，请等待当前阶段安全结束。",
    "open_outputs": "已打开生成文件和日志。",
    "compile": "已触发论文编译，请查看输出页状态。",
    "review": "已触发论文审查，请查看输出页状态。",
    "refresh_delivery": "已刷新交付检查。",
    "build_delivery_package": "已触发交付打包，请查看生成文件。",
    "open_project_root": "已打开项目文件夹。",
    "open_primary_output": "已打开最新输出所在位置。",
    "select_analyzed": "已选择已分析项目，可批量入队。",
    "batch_packages": "已触发批量交付打包。",
    "autotune_capacity": "已触发并发调优。",
    "repair_campaign": "已触发修复行动。",
    "refresh_all": "已刷新项目、任务和交付状态。",
}


def action_outcome(action_id: str) -> str:
    return ACTION_OUTCOMES.get(str(action_id or ""), "")


def action_progress(action_id: str) -> str:
    return ACTION_PROGRESS.get(str(action_id or ""), "")


def action_success(action_id: str) -> str:
    return ACTION_SUCCESS.get(str(action_id or ""), "")
