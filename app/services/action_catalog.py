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


def action_outcome(action_id: str) -> str:
    return ACTION_OUTCOMES.get(str(action_id or ""), "")
