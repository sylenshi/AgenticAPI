"""维护 Agent 容器沙箱服务（全站共享单容器：懒启动 + 空闲自停）

设计要点（v0.10.0 决策，突破维护 Agent「无 shell」红线 → 修订为「无未审批的 shell」）：
- 共享而非每会话一容器：服务器单 VM，避免容器数量随会话膨胀；会话间以
  /workspace/s{session_id} 工作目录隔离，容器停止即清空（无持久化诉求）；
- 懒启动：首个获批命令触发镜像懒构建（指纹防重复构建）→ 网络懒建 → 容器三态复用；
- 空闲自停：idle_watchdog_loop 由 main.py lifespan 挂载，超时 docker stop；
- 驱动方式：docker CLI 子进程（asyncio.create_subprocess_exec），不引入 docker SDK，
  本机 Windows（Docker Desktop）与云端 Linux 行为一致；服务器运行用户不在 docker 组
  时可配 SANDBOX_DOCKER_CMD="sudo -n docker"；
- 加固：独立网桥、非 root、--cap-drop ALL、no-new-privileges、只读 rootfs + tmpfs
  工作区、内存/CPU/pids 三重限额；不挂载任何宿主路径与 .env，不注入渠道密钥；
- v0.11.0 MySQL 桥接（可选）：SANDBOX_MYSQL_HOST 配置后向容器注入站内 MySQL 连接
  环境变量（data-governance 技能在沙箱内跑 pymysql 统计/治理脚本）。"host" 模式经
  host-gateway 访问宿主机；"container:<名称>" 模式把沙箱接入该容器网络以容器名直连
  （生产 MySQL 只绑宿主回环也能通）。凭证来自 MysqlSettings 或 SANDBOX_MYSQL_USER/
  PASSWORD 覆盖值，仅以 docker env 注入（不出现在 .env 挂载与工具返回值中）；
- 每条命令是否弹审批由会话档位决定（registry 阀门），全程审计。

密钥红线：本服务不接触渠道密钥；MySQL 连接凭证仅存在于容器环境变量；命令输出经
registry 现有 redact + 8KB 截断管线回传模型与前端，嵌入命令中的密钥形态值
（含 mysql://user:pass@ 连接串）同样会被掩码。
"""

import asyncio
import hashlib
import shlex
import time

from app.core.config import BASE_DIR, sandbox_setting, setting as mysql_setting

# Dockerfile 所在目录（docker build 上下文，目录内仅此一个文件）
SANDBOX_DIR = BASE_DIR / "sandbox"
CONTAINER_NAME = "agenticapi-sandbox"
NETWORK_NAME = "agenticapi-sandbox-net"
FINGERPRINT_LABEL = "agenticapi.sandbox.fingerprint"

# 输出限额：单流累计上限（超出保尾部）；实时推送总上限（超出停止推送只累计）
STREAM_ACCUM_CAP = 64 * 1024
EMIT_TOTAL_CAP = 64 * 1024
# docker 子进程通用超时 / 首次镜像构建超时 / stop 超时
DOCKER_TIMEOUT = 30
BUILD_TIMEOUT = 420
STOP_TIMEOUT = 30

# ─── 进程内状态（单 uvicorn worker，无需跨进程协调） ───
_ready_lock = asyncio.Lock()                      # ensure_ready 串行化（防并发懒构建/竞态）
_exec_sem = asyncio.Semaphore(sandbox_setting.SANDBOX_MAX_CONCURRENT)
_last_used: float = 0.0                           # 最近一次使用（exec / ensure）时间戳
_running_flag = False                             # 内存态运行标记（watchdog 与 status 用）
_docker_ok: bool | None = None                    # docker 可用性缓存（只缓存成功结果）


def _docker_cmd() -> list[str]:
    """docker 命令前缀（支持 "sudo -n docker" 等多词配置）"""
    return shlex.split(sandbox_setting.SANDBOX_DOCKER_CMD, posix="/\\" not in sandbox_setting.SANDBOX_DOCKER_CMD)


def _now() -> float:
    return time.time()


async def _run_docker(args: list[str], timeout: int = DOCKER_TIMEOUT) -> tuple[int, str, str]:
    """执行一条 docker 子进程命令，返回 (rc, stdout, stderr)。绝不抛异常——
    docker 不可用 / 命令失败本身就是需要反馈给模型的数据。"""
    cmd = _docker_cmd() + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, "", f"docker 命令超时（{timeout}s）：{' '.join(args[:3])}"
        return (proc.returncode or 0,
                out.decode("utf-8", errors="replace").strip(),
                err.decode("utf-8", errors="replace").strip())
    except FileNotFoundError:
        return 127, "", "未找到 docker 命令（宿主机未安装或不在 PATH）"
    except Exception as exc:  # 兜底：任何子进程异常都转为数据
        return 1, "", f"{exc.__class__.__name__}: {exc}"


async def docker_available() -> bool:
    """docker 是否可用（docker version 探测，成功才缓存——Docker Desktop 可能稍后启动）"""
    global _docker_ok
    if _docker_ok:
        return True
    rc, _, _ = await _run_docker(["version", "--format", "{{.Server.Version}}"], timeout=10)
    if rc == 0:
        _docker_ok = True
    return _docker_ok


def fingerprint() -> str:
    """镜像指纹 = sha256(Dockerfile 内容 + 基础镜像 + pip 源 + apt 源)，任一变化即触发重建"""
    content = SANDBOX_DIR.joinpath("Dockerfile").read_bytes()
    raw = (content
           + sandbox_setting.SANDBOX_BASE_IMAGE.encode()
           + sandbox_setting.SANDBOX_PIP_INDEX_URL.encode()
           + sandbox_setting.SANDBOX_APT_MIRROR.encode())
    return hashlib.sha256(raw).hexdigest()[:16]


async def _ensure_image() -> bool:
    """镜像就绪：不存在或指纹不匹配则懒构建。返回是否发生了重建。"""
    fp = fingerprint()
    rc, current, _ = await _run_docker(
        ["inspect", "--format", f"{{{{index .Config.Labels \"{FINGERPRINT_LABEL}\"}}}}",
         sandbox_setting.SANDBOX_IMAGE])
    if rc == 0 and current == fp:
        return False

    rc, out, err = await _run_docker(
        ["build",
         "--build-arg", f"BASE_IMAGE={sandbox_setting.SANDBOX_BASE_IMAGE}",
         "--build-arg", f"PIP_INDEX_URL={sandbox_setting.SANDBOX_PIP_INDEX_URL}",
         "--build-arg", f"APT_MIRROR={sandbox_setting.SANDBOX_APT_MIRROR}",
         "--label", f"{FINGERPRINT_LABEL}={fp}",
         "-t", sandbox_setting.SANDBOX_IMAGE,
         str(SANDBOX_DIR)],
        timeout=BUILD_TIMEOUT)
    if rc != 0:
        raise RuntimeError(f"沙箱镜像构建失败（首次构建需拉取基础镜像，超时/网络失败时可预拉基础镜像后重试）："
                           f"{(err or out)[-500:]}")
    return True


async def _ensure_network() -> None:
    """独立网桥网络就绪（沙箱默认与默认网桥上的 MySQL 容器隔离；桥接见 _ensure_container）"""
    rc, out, _ = await _run_docker(
        ["network", "ls", "--filter", f"name=^{NETWORK_NAME}$", "--format", "{{.Name}}"])
    if rc == 0 and out == NETWORK_NAME:
        return
    rc, _, err = await _run_docker(["network", "create", NETWORK_NAME])
    if rc != 0 and "already exists" not in err:
        raise RuntimeError(f"沙箱网络创建失败：{err[:300]}")


def _mysql_bridge() -> dict | None:
    """解析沙箱-MySQL 桥接配置（v0.11.0）。未配置返回 None（容器保持与数据库隔离）。

    SANDBOX_MYSQL_HOST 三种取值：
    - "host"：经 host.docker.internal(host-gateway) 访问宿主机端口（本地开发 / Docker Desktop）；
    - "container:<名称>"：MySQL 以容器运行时，把沙箱接入其所在网络，env 直接写容器名
      （生产 MySQL 只发布在宿主回环时，跨容器经共享网络直连是唯一可靠路径）；
    - 其他值：当作主机名/IP 直连（仍注入 host-gateway 解析以便写 host.docker.internal）。
    连接凭证：SANDBOX_MYSQL_USER/PASSWORD 覆盖值优先，否则复用 MysqlSettings。
    """
    raw = (sandbox_setting.SANDBOX_MYSQL_HOST or "").strip()
    if not raw:
        return None
    host = raw
    if raw.lower().startswith("container:"):
        host = raw.split(":", 1)[1].strip()
    if not host:
        return None
    return {
        "host": host,
        "container_mode": raw.lower().startswith("container:"),
        "env": {
            "MYSQL_HOST": host,
            "MYSQL_PORT": str(mysql_setting.MYSQL_PORT),
            "MYSQL_USER": sandbox_setting.SANDBOX_MYSQL_USER or mysql_setting.MYSQL_USER,
            "MYSQL_PASSWORD": sandbox_setting.SANDBOX_MYSQL_PASSWORD or mysql_setting.MYSQL_PASSWORD,
            "MYSQL_DATABASE": mysql_setting.MYSQL_DATABASE,
        },
    }


async def _connect_mysql_network(bridge_container: str) -> None:
    """container:<名称> 模式：把沙箱容器接入目标容器所在的第一个用户自定义网络。
    失败不阻断沙箱启动——连接问题会在脚本执行时以错误数据回传，由模型向管理员反馈。"""
    rc, nets, err = await _run_docker(
        ["inspect", "--format",
         "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}", bridge_container])
    if rc != 0 or not nets.strip():
        print(f"[sandbox] 检测 MySQL 容器 {bridge_container} 网络失败：{(err or nets)[:200]}")
        return
    for net in nets.split():
        rc2, _, err2 = await _run_docker(["network", "connect", net, CONTAINER_NAME])
        if rc2 == 0 or "already exists" in (err2 or "").lower():
            print(f"[sandbox] 沙箱已接入网络 {net}（MySQL 容器 {bridge_container}）")
            return
    print(f"[sandbox] 沙箱接入 MySQL 网络失败：{(err2 or '')[:200]}")


async def _container_state() -> str:
    """容器状态：running / exited / created / ''（不存在）"""
    rc, out, _ = await _run_docker(
        ["inspect", "--format", "{{.State.Status}}", CONTAINER_NAME])
    return out if rc == 0 and out else ""


async def _ensure_container(rebuilt: bool) -> None:
    """容器三态复用：运行中直接用 / 已存在则 start / 不存在则 run（加固参数）。
    镜像重建后旧容器作废，先删再起。配置了 MySQL 桥接时追加 host-gateway 解析、
    连接环境变量注入；container:<名称> 模式再接入 MySQL 容器网络。"""
    global _running_flag
    state = await _container_state()

    if state == "running" and not rebuilt:
        _running_flag = True
        return

    if state:  # 存在但未运行，或镜像已重建
        await _run_docker(["rm", "-f", CONTAINER_NAME], timeout=STOP_TIMEOUT)

    bridge = _mysql_bridge()
    run_args = ["run", "-d",
                "--name", CONTAINER_NAME,
                "--network", NETWORK_NAME,
                "--restart", "no",
                "--memory", "512m", "--cpus", "1", "--pids-limit", "256",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--read-only",
                "--tmpfs", "/tmp:rw,size=64m",
                "--tmpfs", "/workspace:rw,size=256m,uid=1000,gid=1000",
                "-u", "1000:1000"]
    if bridge:
        run_args += ["--add-host", "host.docker.internal:host-gateway"]
        for key, value in bridge["env"].items():
            run_args += ["-e", f"{key}={value}"]
    run_args.append(sandbox_setting.SANDBOX_IMAGE)

    rc, out, err = await _run_docker(run_args, timeout=DOCKER_TIMEOUT)
    if rc != 0:
        raise RuntimeError(f"沙箱容器启动失败：{(err or out)[:300]}")
    if bridge and bridge["container_mode"]:
        await _connect_mysql_network(bridge["host"])
    _running_flag = True


async def ensure_ready() -> None:
    """沙箱就绪总入口（镜像 → 网络 → 容器），锁内串行防并发懒初始化竞态。"""
    global _last_used
    if not sandbox_setting.SANDBOX_ENABLED:
        raise ValueError("沙箱未启用（SANDBOX_ENABLED=false），如需使用请在后端 .env 打开")
    if not await docker_available():
        raise ValueError("沙箱不可用：未检测到 Docker（未安装 / daemon 未启动 / 无权限，"
                         "服务器可检查 docker 组或配置 SANDBOX_DOCKER_CMD=sudo -n docker）")
    async with _ready_lock:
        rebuilt = await _ensure_image()
        await _ensure_network()
        await _ensure_container(rebuilt)
        _last_used = _now()


def _keep_tail(text: str, cap: int) -> str:
    """超长输出保尾部（报错结论通常在末尾）"""
    if len(text) <= cap:
        return text
    return f"[…前 {len(text) - cap} 字符已截断…]\n" + text[-cap:]


async def exec_command(session_id: int, command: str, timeout: int,
                       emit=None) -> dict:
    """在共享沙箱容器内执行一条命令（工作目录 /workspace/s{session_id} 隔离）。

    命令经容器内 coreutils timeout 包裹（SIGTERM→SIGKILL），客户端侧再以
    timeout+30s 兜底杀 docker CLI；输出流式经 emit 推送（{"type":"sandbox_output"}）。
    返回 {ok, exitCode, stdout, stderr, durationMs}，绝不抛异常。
    """
    timeout = max(5, min(int(timeout), sandbox_setting.SANDBOX_CMD_TIMEOUT_MAX))
    workdir = f"/workspace/s{session_id}"
    # stdin 传命令体（sh -s 读 stdin），避免双层引号转义；容器内 timeout 负责真正杀命令
    outer = f"mkdir -p {workdir} && cd {workdir} && exec timeout -k 10 {timeout}s sh -s"
    started = _now()

    async def _run() -> dict:
        global _last_used
        await ensure_ready()
        _last_used = _now()
        cmd = _docker_cmd() + ["exec", "-i", CONTAINER_NAME, "sh", "-c", outer]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return {"ok": False, "exitCode": 127, "stdout": "", "stderr": "未找到 docker 命令",
                    "durationMs": 0}
        except Exception as exc:
            return {"ok": False, "exitCode": 1, "stdout": "",
                    "stderr": f"{exc.__class__.__name__}: {exc}", "durationMs": 0}

        stdout_buf: list[str] = []
        stderr_buf: list[str] = []
        emit_state = {"len": 0, "stopped": False}

        async def _pump(stream, buf: list):
            """单流泵：累计（保尾部截断）+ 节流实时推送（0.25s 或 2KB 一批）"""
            own_pending: list[str] = []
            own_len = 0
            last_flush = _now()
            total = 0
            while True:
                chunk = await stream.read(2048)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                total += len(text)
                if total <= STREAM_ACCUM_CAP:
                    buf.append(text)
                elif not buf or not buf[-1].startswith("\n[…输出超长"):
                    buf.append("\n[…输出超长，已停止累计，仅保留前面内容…]")
                if not emit_state["stopped"]:
                    emit_state["len"] += len(text)
                    if emit_state["len"] > EMIT_TOTAL_CAP:
                        emit_state["stopped"] = True
                        own_pending.append("\n[…实时输出已达上限，后续仅计入最终结果…]")
                    else:
                        own_pending.append(text)
                        own_len += len(text)
                # 节流：攒够 2KB 或距上次推送超 0.25s 才发
                if own_pending and (own_len >= 2048 or _now() - last_flush >= 0.25):
                    batch = "".join(own_pending)
                    own_pending.clear()
                    own_len = 0
                    last_flush = _now()
                    if emit:
                        try:
                            await emit({"type": "sandbox_output", "tool": "sandbox_exec",
                                        "chunk": batch})
                        except Exception:
                            pass
            if own_pending and emit and not emit_state["stopped"]:
                try:
                    await emit({"type": "sandbox_output", "tool": "sandbox_exec",
                                "chunk": "".join(own_pending)})
                except Exception:
                    pass

        pump_out = asyncio.create_task(_pump(proc.stdout, stdout_buf))
        pump_err = asyncio.create_task(_pump(proc.stderr, stderr_buf))

        async def _feed_stdin():
            if proc.stdin:
                try:
                    proc.stdin.write(command.encode("utf-8"))
                    await proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # 容器内进程已退出（如命令秒错），写入失败无碍
                finally:
                    proc.stdin.close()

        feeder = asyncio.create_task(_feed_stdin())

        client_timed_out = False
        try:
            await asyncio.wait_for(
                asyncio.gather(pump_out, pump_err, proc.wait()),
                timeout=timeout + 30)
        except asyncio.TimeoutError:
            client_timed_out = True
            proc.kill()  # 兜底：杀 docker CLI（容器内命令已由 coreutils timeout 处理）
            await proc.wait()
        finally:
            for task in (pump_out, pump_err, feeder):
                if not task.done():
                    task.cancel()

        duration = int((_now() - started) * 1000)
        stdout = _keep_tail("".join(stdout_buf), 6000)
        stderr = _keep_tail("".join(stderr_buf), 2000)
        code = proc.returncode if proc.returncode is not None else 1
        timed_out = client_timed_out or code == 124  # 124 = 容器内 timeout 杀掉命令
        first_err = next((line for line in stderr.splitlines() if line.strip()), "")
        return {
            "ok": code == 0 and not client_timed_out,
            "exitCode": code,
            "timedOut": timed_out,
            "stdout": stdout,
            "stderr": stderr,
            "durationMs": duration,
            "_summary": (f"命令{'成功' if code == 0 and not client_timed_out else '失败'}（exit {code}"
                         f"{'，超时被杀' if timed_out else ''}，{duration}ms）"
                         + (f"：{first_err[:80]}" if first_err and code != 0 else "")),
        }

    async with _exec_sem:
        return await _run()


async def stop() -> None:
    """停止沙箱容器（best-effort，保留容器与镜像供下次秒级 start）"""
    global _running_flag
    if not _running_flag:
        return
    await _run_docker(["stop", "-t", "5", CONTAINER_NAME], timeout=STOP_TIMEOUT)
    _running_flag = False


async def idle_watchdog_loop(interval: int = 60) -> None:
    """空闲自停看门狗（main.py lifespan 挂载）：超时未使用则 docker stop。
    从未启动过沙箱时零 docker 调用，不影响无 Docker 环境。"""
    while True:
        await asyncio.sleep(interval)
        try:
            if (_running_flag and _last_used
                    and _now() - _last_used > sandbox_setting.SANDBOX_IDLE_STOP_SECONDS):
                await stop()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # 看门狗异常不致命，下个周期重试


async def shutdown() -> None:
    """应用关闭时收尾（lifespan yield 之后调用，best-effort）"""
    try:
        await stop()
    except Exception:
        pass


async def status() -> dict:
    """沙箱状态总览（sandbox_status 工具用；不做任何变更）"""
    info: dict = {
        "enabled": sandbox_setting.SANDBOX_ENABLED,
        "image": sandbox_setting.SANDBOX_IMAGE,
        "baseImage": sandbox_setting.SANDBOX_BASE_IMAGE,
        "idleStopSeconds": sandbox_setting.SANDBOX_IDLE_STOP_SECONDS,
        "dockerAvailable": await docker_available(),
    }
    if info["dockerAvailable"] and sandbox_setting.SANDBOX_ENABLED:
        rc, current, _ = await _run_docker(
            ["inspect", "--format", f"{{{{index .Config.Labels \"{FINGERPRINT_LABEL}\"}}}}",
             sandbox_setting.SANDBOX_IMAGE])
        info["imageReady"] = rc == 0
        info["imageUpToDate"] = rc == 0 and current == fingerprint()
        info["containerState"] = await _container_state()
        info["idleSeconds"] = int(_now() - _last_used) if _last_used else None
    return info
