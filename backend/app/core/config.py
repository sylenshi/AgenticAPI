"""应用配置：基于 pydantic-settings 从 backend/.env 读取"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BASE_DIR / '.env'
DATA_DIR = BASE_DIR / 'data'  # 运行期数据目录（敏感凭证 / 调试快照），已加入 .gitignore


class MysqlSettings(BaseSettings):
    """配置类"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding='utf-8',
        extra='ignore', # 忽略 .env 中未定义的变量
    )

    MYSQL_HOST: str
    MYSQL_PORT: int
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DATABASE: str

    DEBUG: bool

    @property
    def MYSQL_URL(self) -> str:
        return f"mysql+asyncmy://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"


class ServerSettings(BaseSettings):
    """服务运行配置：监听地址 / 端口 / 对外公开地址"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding='utf-8',
        extra='ignore', # 忽略 .env 中未定义的变量
    )

    # 后端监听地址与端口（python -m app.main 启动时生效）
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 2027
    # 对外公开访问地址（部署到公网时改为真实 URL）：
    # 模型拨测自调用、GET /site/info 下发给前端展示的中转接口地址都用它
    PUBLIC_BASE_URL: str = "http://localhost:2027"

    @property
    def RELAY_BASE_URL(self) -> str:
        """对外中转接口基地址（OpenAI 兼容），已去掉尾部斜杠便于拼接路径"""
        return self.PUBLIC_BASE_URL.rstrip('/') + '/v1'


class AgentSettings(BaseSettings):
    """Agent 能力专用配置：直连 StepFun，不经渠道/模型表，不计费不记日志"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding='utf-8',
        extra='ignore', # 忽略 .env 中未定义的变量
    )

    # StepFun OpenAI 兼容对话端点
    AGENT_BASE_URL: str = ""
    # StepFun ASR 兼容端点
    ASR_BASE_URL: str = ""
    # StepFun 密钥（与工坊语音 ASR 共用同一把，不另配一份）
    STEPFUN_API_KEY: str = ""
    # Agent 标题模型（默认使用 StepFun 模型）
    AGENT_TITLE_MODEL: str = ""
    # 站点维护 Agent 默认大脑模型（站内出站模型名；system_config 的 agent_default_model 优先于此值）
    AGENT_MAINTENANCE_MODEL: str = ""


class ZaiOpsSettings(BaseSettings):
    """智谱 Coding Plan 用量监控专用配置

    API key 长期有效。控制台"运营-设置凭证"上传的 key 存 operations_config.json，
    优先于此处的 .env 兜底值（换号只上传、无需改文件）。
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding='utf-8',
        extra='ignore', # 忽略 .env 中未定义的变量
    )

    # v2 套餐账号的 Coding Plan API key（.env 兜底值）
    ZAI_API_KEY_2: str = ""


class AntigravityOpsSettings(BaseSettings):
    """Antigravity（Gemini PRO）限额监控专用配置

    数据源是同机回环的 Antigravity-Manager 容器管理 API，密钥即管理界面访问令牌（长期有效）。
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding='utf-8',
        extra='ignore', # 忽略 .env 中未定义的变量
    )

    # 容器管理 API 地址（同机部署用默认回环地址即可）
    ANTIGRAVITY_BASE_URL: str = "http://127.0.0.1:8045"
    # 管理界面的访问令牌（WEB_PASSWORD），以 Authorization: Bearer 头鉴权
    ANTIGRAVITY_API_KEY: str = ""


class SandboxSettings(BaseSettings):
    """维护 Agent 容器沙箱配置

    沙箱为全站共享单容器（懒启动 + 空闲自停），经 docker CLI 子进程驱动，
    Windows 本机（Docker Desktop）与 Linux 云端行为一致。
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding='utf-8',
        extra='ignore', # 忽略 .env 中未定义的变量
    )

    # 沙箱总开关（关闭后 sandbox_exec 返回不可用提示，其余工具不受影响）
    SANDBOX_ENABLED: bool = True
    # docker 命令前缀：默认直接 docker；服务器运行用户不在 docker 组时可配 "sudo -n docker"
    SANDBOX_DOCKER_CMD: str = "docker"
    # 沙箱镜像名（懒构建产物）
    SANDBOX_IMAGE: str = "agenticapi-sandbox:latest"
    # 基础镜像（Docker Hub 拉取慢时换国内镜像源；改动会触发镜像重建）
    SANDBOX_BASE_IMAGE: str = "python:3.12-slim"
    # 镜像构建时的 pip 源（pypi.org 不可达的内网环境换国内镜像，如
    # https://mirrors.tencentyun.com/pypi/simple；改动会触发镜像重建）
    SANDBOX_PIP_INDEX_URL: str = "https://pypi.org/simple"
    # 镜像构建时的 Debian apt 源主机（deb.debian.org 海外下载慢时换国内源，如
    # mirrors.cloud.tencent.com；改动会触发镜像重建）
    SANDBOX_APT_MIRROR: str = "deb.debian.org"
    # 容器空闲多少秒后自动停止（懒启动对偶：用完即停，降低常驻开销）
    SANDBOX_IDLE_STOP_SECONDS: int = 900
    # 同一时刻允许并发执行的沙箱命令数（共享容器，串行化避免输出交叉）
    SANDBOX_MAX_CONCURRENT: int = 2
    # 单条命令超时上限（秒）
    SANDBOX_CMD_TIMEOUT_MAX: int = 120

    # ── 沙箱-MySQL 桥接（v0.11.0：数据治理技能在沙箱内跑 pymysql 脚本）──
    # SANDBOX_MYSQL_HOST 留空 = 不注入（容器与数据库隔离，行为同 v0.10.0）；配置后按三种取值接入：
    #   "host"            经 host-gateway 访问宿主机（Docker Desktop 可达宿主回环服务，本地开发用）
    #   "container:<名称>" 把沙箱接入该 MySQL 容器所在网络并以容器名直连（服务器 MySQL 只绑回环也能通）
    #   其他值             当作主机名/IP 直连（同时注入 host-gateway 解析，可写 host.docker.internal）
    # 连接凭证默认复用 MysqlSettings（MYSQL_USER/MYSQL_PASSWORD/MYSQL_PORT/MYSQL_DATABASE），
    # 可用以下两项覆盖（如为沙箱单独建最小权限账号）：
    SANDBOX_MYSQL_HOST: str = ""
    SANDBOX_MYSQL_USER: str = ""
    SANDBOX_MYSQL_PASSWORD: str = ""


agent_setting = AgentSettings()
setting = MysqlSettings()
server_setting = ServerSettings()
zai_ops_setting = ZaiOpsSettings()
antigravity_ops_setting = AntigravityOpsSettings()
sandbox_setting = SandboxSettings()
