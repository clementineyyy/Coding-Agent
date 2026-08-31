from __future__ import annotations

from harness.registry import Tool, ToolResult


def spec() -> Tool:
    def handler(args: dict, ctx) -> ToolResult:
        command = args["command"]
        command = _inject_curl_timeout(command, ctx.config.tool_timeout)
        result = ctx.sandbox.run(command, ctx.config.tool_timeout)
        if result.exit_code == -1 and "timeout" in (result.stderr or "").lower():
            status = "timeout"
        else:
            status = "success" if result.exit_code == 0 else "error"
        output = result.stdout
        if not ctx.sandbox.network_enabled:
            output = (f"{output}\n[network_enabled=False]").strip()
        return ToolResult(
            status=status,
            output=output,
            error=result.stderr or None,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            truncated=result.truncated,
        )

    tool = Tool(
        name="bash",
        description="执行任意 shell 命令：查询系统（which/where/ps/注册表）、运行程序、文件操作、构建 / 测试 / lint 等",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
        requires_approval=True,
        needs_sandbox=True,
        uses_workspace=True,
    )
    tool.handler = handler
    return tool


def _inject_curl_timeout(command: str, timeout: int) -> str:
    """为 curl 命令自动注入 --connect-timeout 和 --max-time，防止长时间挂起。"""
    import re
    if not re.search(r'\bcurl\b', command):
        return command
    if '--connect-timeout' in command or '--max-time' in command:
        return command
    ct = max(5, timeout // 3)
    mt = max(10, timeout)
    return command.replace("curl", f"curl --connect-timeout {ct} --max-time {mt}", 1)
