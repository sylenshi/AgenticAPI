"""沙箱域工具：S1 sandbox_exec（任意命令）/ S2 sandbox_status（状态查询）

v0.10.0 决策：突破「无 shell」红线 → 修订为「无未审批的 shell」。沙箱为全站
共享单容器（懒启动 + 空闲自停），审批卡展示完整命令；v0.11.0 起每条命令是否
弹卡由会话审批档位决定（confirm_all/confirm_critical 档必弹、full 档直行），
隔离与限额见 sandbox_service 模块注释。v0.11.0 镜像加装 pymysql 并可注入站内
MySQL 连接环境变量（SANDBOX_MYSQL_HOST 配置，data-governance 技能依赖）。
"""

from app.core.config import sandbox_setting
from app.services import sandbox_service
from app.services.agent.registry import ToolContext, ToolDef, register

# 命令长度上限（超长命令多为误生成，直接拒绝）
COMMAND_MAX_CHARS = 4000


async def _sandbox_exec_preview(ctx: ToolContext, args: dict) -> str:
    """审批卡必须展示待执行的完整命令（与 save_skill 展示完整草稿同一约束）"""
    command = args.get("command") or ""
    timeout = args.get("timeout_seconds") or 60
    return (f"将在共享沙箱容器（隔离 Linux 环境，非宿主机）内执行：\n"
            f"─────── 命令 ───────\n{command}\n"
            f"─────────────────────\n"
            f"超时 {timeout}s ｜ 工作目录 /workspace/s{ctx.session.get('id')}（会话隔离，容器空闲自停后清空）")


async def sandbox_exec(ctx: ToolContext, args: dict) -> dict:
    """S1 沙箱命令执行：docker CLI → 共享容器 → 流式回传"""
    command = (args.get("command") or "").strip()
    if not command:
        raise ValueError("command 不能为空")
    if len(command) > COMMAND_MAX_CHARS:
        raise ValueError(f"command 过长（{len(command)} 字符，上限 {COMMAND_MAX_CHARS}），请拆分执行")

    timeout = args.get("timeout_seconds")
    if timeout is None:
        timeout = 60
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        raise ValueError(f"timeout_seconds 需为整数，收到：{timeout!r}")
    if not 5 <= timeout <= sandbox_setting.SANDBOX_CMD_TIMEOUT_MAX:
        raise ValueError(f"timeout_seconds 需在 5~{sandbox_setting.SANDBOX_CMD_TIMEOUT_MAX} 秒之间，收到 {timeout}")

    return await sandbox_service.exec_command(
        session_id=int(ctx.session["id"]), command=command,
        timeout=timeout, emit=ctx.emit)


async def sandbox_status(ctx: ToolContext, args: dict) -> dict:
    """S2 沙箱状态查询（L0 只读，不做任何变更）"""
    info = await sandbox_service.status()
    info["_summary"] = (f"沙箱{'启用' if info['enabled'] else '未启用'}，"
                        + (f"Docker 可用，容器状态 {info.get('containerState', '未创建')}"
                           if info.get("dockerAvailable") else "Docker 不可用"))
    return info


def register_sandbox_tools() -> None:
    register(ToolDef(
        name="sandbox_exec",
        description=("在隔离的 Linux 容器沙箱内执行任意 shell 命令（审批卡展示完整命令，是否弹卡由会话审批档位决定）。"
                     "内置 curl / jq / python3(+httpx/pymysql)，可访问公网；已注入站内 MySQL 连接环境变量"
                     "（MYSQL_HOST/PORT/USER/PASSWORD/DATABASE，数据治理用，严禁查询凭证列）。适用场景：测试任意 API 端点"
                     "（如给定 base_url+key+model 直发请求验证可用性）、拉取上游 /v1/models 对比定价、"
                     "脚本化批量诊断、站内数据统计/治理脚本。文件在 /workspace/s{会话id} 下跨命令保留"
                     "（容器空闲自停后清空）。使用守则：优先使用站内定制工具（更快更安全），沙箱仅作兜底；"
                     "命令保持幂等可读；输出过大时用 head/tail/jq 截取。"),
        parameters={"type": "object", "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令（≤4000 字符）"},
            "timeout_seconds": {"type": "integer",
                                "description": f"命令超时秒数（5~{sandbox_setting.SANDBOX_CMD_TIMEOUT_MAX}，默认 60）"},
        }, "required": ["command"]},
        risk="L1", handler=sandbox_exec, always_confirm=True,
        preview=_sandbox_exec_preview, timeout=480,
    ))
    register(ToolDef(
        name="sandbox_status",
        description="查询沙箱状态：是否启用、Docker 可用性、镜像就绪/是否最新、容器运行状态、空闲时长。排障沙箱不可用时先用它。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=sandbox_status, timeout=60,
    ))
