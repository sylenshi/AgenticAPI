"""维护 Agent 沙箱与 CRUD 工具冒烟测试（进程内直测，无需起服务、无需真实模型）

覆盖（v0.10.0 新增面）：
- redact 子串级掩码（命令内嵌 sk-/Bearer、键名命中、长文件名不误伤）
- 工具注册表：36 个工具、enable_l2 关闭时 L2 裁剪不注入
- 沙箱服务：docker 可用性 → ensure_ready（首次含懒构建）→ exec/持久化/会话隔离/
  非 root + 只读 rootfs 加固 / 容器内超时（exit 124）
- 渠道/模型 CRUD 工具 handler（真实 DB）：create_channel → create_model →
  update_model → delete_model(dry-run→真删) → delete_channel(dry-run→真删)，
  断言返回值全程无 api_key 明文
- 可选：--with-search 时真实调 web_search（0.04 元/次，默认跳过）

用法：cd backend && python _smoke_sandbox.py [--with-search]
前置：本机 Docker Desktop 运行中、backend/.env 指向可用的 MySQL。
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

results = []


def report(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (" | " + detail if detail else ""))


class CtxStub:
    """ToolContext 桩：直调工具 handler（绕过审批门，只测业务逻辑）"""

    def __init__(self, db, session_id=9001):
        self.db = db
        self.user = SimpleNamespace(id=0, username="smoke", is_admin=1)
        self.session = {"id": session_id, "model_name": "smoke",
                        "auto_approve_l1": True, "enable_l2": True}
        self.events = []

    async def emit(self, ev):
        self.events.append(ev)


async def smoke_redact():
    from app.services.agent.maintain_loop import _redact_arguments
    from app.services.agent.redact import redact

    r = _redact_arguments('{"command": "curl -H \'Authorization: Bearer sk-abcdef1234567890\' https://x.com"}')
    report("redact: 命令内嵌 Bearer sk- 被掩码", "sk-abcdef1234567890" not in r and "Bea****" in r, r[:120])

    r = _redact_arguments('{"api_key": "sk-verylongsecretkey1234567890", "base_url": "https://x/v1"}')
    report("redact: api_key 键名命中掩码", "sk-verylongsecretkey1234567890" not in r, r)

    r = _redact_arguments('{"command": "cat abcdefghijklmnopqrstuvwxyz012345.py"}')
    report("redact: 长文件名不误伤", "abcdefghijklmnopqrstuvwxyz012345.py" in r, r)

    r = redact({"token": "gHP_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"})
    report("redact: 整值形态掩码", "gHP_xxxxxxxxxxxxxxxxxxxxxxxxxxxx" not in str(r), str(r))


async def smoke_registry():
    from app.services.agent.registry import TOOL_REGISTRY, tools_payload_for, _ensure_tools_loaded
    _ensure_tools_loaded()
    report("注册表：共 36 个工具", len(TOOL_REGISTRY) == 36, f"实际 {len(TOOL_REGISTRY)}")
    names = {t.name for t in TOOL_REGISTRY.values() if t.risk == "L2"}
    report("注册表：L2 共 5 个（含 delete_channel/delete_model）",
           names == {"cleanup_chat_records", "cleanup_logs", "cleanup_aggregate_stats",
                     "delete_channel", "delete_model"}, str(sorted(names)))
    payload = tools_payload_for({"enable_l2": False})
    payload_names = {p["function"]["name"] for p in payload}
    report("注册表：enable_l2=false 时 L2 不注入",
           "delete_channel" not in payload_names and "sandbox_exec" in payload_names,
           f"{len(payload_names)} 个注入")


async def smoke_sandbox_service():
    from app.services import sandbox_service

    if not await sandbox_service.docker_available():
        report("沙箱：docker 可用", False, "Docker 不可用（Docker Desktop 未启动？）后续沙箱用例跳过")
        return
    report("沙箱：docker 可用", True)

    await sandbox_service.ensure_ready()
    info = await sandbox_service.status()
    report("沙箱：ensure_ready（懒构建+网络+容器）",
           info.get("imageReady") and info.get("containerState") == "running", str(info))

    r = await sandbox_service.exec_command(9001, "echo smoke-hello", 20)
    report("沙箱：echo 执行成功", r["ok"] and "smoke-hello" in r["stdout"], str(r)[:200])

    r = await sandbox_service.exec_command(9001, "echo v1 > t.txt && cat t.txt", 20)
    ok_persist = r["ok"] and "v1" in r["stdout"]
    r2 = await sandbox_service.exec_command(9001, "cat t.txt", 20)
    report("沙箱：工作区跨命令持久", ok_persist and "v1" in r2["stdout"], r2["stdout"][:80])

    await sandbox_service.exec_command(9001, "echo s1 > same.txt", 20)
    await sandbox_service.exec_command(9002, "echo s2 > same.txt", 20)
    a = await sandbox_service.exec_command(9001, "cat same.txt", 20)
    b = await sandbox_service.exec_command(9002, "cat same.txt", 20)
    report("沙箱：会话目录隔离", a["stdout"].strip() == "s1" and b["stdout"].strip() == "s2",
           f"s9001={a['stdout'].strip()} s9002={b['stdout'].strip()}")

    r = await sandbox_service.exec_command(9001, "id -u", 20)
    report("沙箱：非 root（uid 1000）", r["ok"] and r["stdout"].strip() == "1000", r["stdout"].strip())

    r = await sandbox_service.exec_command(9001, "touch /should_fail_ro", 20)
    report("沙箱：rootfs 只读", not r["ok"], r["stderr"][:100])

    r = await sandbox_service.exec_command(9001, "sleep 30", 5)
    report("沙箱：容器内超时被杀（exit 124）", r["timedOut"] and not r["ok"], str(r)[:160])

    await sandbox_service.stop()
    state = await sandbox_service.status()
    report("沙箱：手动停止", state.get("containerState") != "running", str(state.get("containerState")))

    # 停止后再执行 → 三态复用应秒级拉起
    r = await sandbox_service.exec_command(9001, "echo revived", 30)
    report("沙箱：停止后再执行自动拉起", r["ok"] and "revived" in r["stdout"], r["stdout"][:80])


async def smoke_crud_tools():
    from app.core.database import asyncSessionLocal
    from app.crud import channel as channel_crud
    from app.crud import model as model_crud
    from app.services.agent.tools import channel_tools, model_tools

    async with asyncSessionLocal() as db:
        # 清理残留（上次中断的冒烟数据）
        await channel_crud.delete_by_name(db, "smoke_sb_channel")
        await model_crud.delete_by_name(db, "smoke_sb_model")
        await db.commit()

        ctx = CtxStub(db)
        key_plain = "sk-smoke-fake-key-1234567890abcdef"

        # create_channel（status=false：冒烟数据保持停用态，不进公开渠道名列表）
        r = await channel_tools.create_channel(ctx, {
            "channel_name": "smoke_sb_channel",
            "base_url": "http://127.0.0.1:9/v1/chat/completions",
            "api_key": key_plain, "support_models": ["smoke-upstream-model"],
            "timeout": 15, "status": False, "description": "沙箱冒烟临时渠道"})
        leaked = key_plain in str(r)
        report("CRUD：create_channel", r.get("ok") and not leaked, str(r)[:160])
        report("CRUD：create_channel 返回无密钥明文", not leaked)

        # create_model（status=false：停用模型不进 /v1/models 与模型广场）
        r = await model_tools.create_model(ctx, {
            "name": "smoke_sb_model", "model_group": "free",
            "channels": ["smoke_sb_channel"],
            "input_price": 1.5, "output_price": 6, "cache_price": 0.3,
            "context_length": 128000, "max_tokens": 4096, "status": False})
        report("CRUD：create_model", r.get("ok"), str(r)[:160])

        # update_model
        r = await model_tools.update_model(ctx, {"name": "smoke_sb_model", "output_price": 7})
        report("CRUD：update_model", r.get("ok") and "output_price" in r.get("updatedFields", []),
               str(r)[:160])

        # delete_model 两阶段
        r = await model_tools.delete_model(ctx, {"name": "smoke_sb_model", "dry_run": True})
        report("CRUD：delete_model dry-run", r.get("dryRun"), str(r)[:160])
        r = await model_tools.delete_model(ctx, {"name": "smoke_sb_model", "dry_run": False})
        report("CRUD：delete_model 真删", r.get("ok"), str(r)[:160])

        # delete_channel 两阶段（模型已删，无绑定影响）
        r = await channel_tools.delete_channel(ctx, {"channel_name": "smoke_sb_channel", "dry_run": True})
        report("CRUD：delete_channel dry-run", r.get("dryRun"), str(r)[:160])
        r = await channel_tools.delete_channel(ctx, {"channel_name": "smoke_sb_channel", "dry_run": False})
        report("CRUD：delete_channel 真删", r.get("ok"), str(r)[:160])

        # 落库校验
        assert await channel_crud.get_by_name(db, "smoke_sb_channel") is None
        assert await model_crud.get_by_name(db, "smoke_sb_model") is None
        report("CRUD：数据已清理（表内无残留）", True)


async def smoke_web_search(with_search: bool):
    from app.services import search_service
    from app.services.agent.tools import web_tools

    if not search_service.search_available():
        report("web_search：未配置 STEPFUN_API_KEY（跳过）", True)
        return
    if not with_search:
        report("web_search：已配置可用（真实调用需 --with-search，跳过计费）", True)
        return
    ctx = CtxStub(None)
    r = await web_tools.web_search_tool(ctx, {"query": "AgenticAPI"})
    report("web_search：真实调用", bool(r.get("result")), str(r)[:160])


async def main():
    with_search = "--with-search" in sys.argv
    print("== 维护 Agent 沙箱冒烟 ==\n")
    await smoke_redact()
    await smoke_registry()
    await smoke_sandbox_service()
    await smoke_crud_tools()
    await smoke_web_search(with_search)
    failed = sum(1 for _, ok in results if not ok)
    print(f"\n== 结果：{len(results) - failed} PASS / {failed} FAIL ==")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
