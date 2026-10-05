"""ORM 模型统一入口

导入此包即触发所有表定义注册到 BaseModel.metadata，
init_database() 依赖此机制自动建表。
新增表时：在 app/models/ 下新建模块，并在此处导入。
"""

from app.models.base import BaseModel
from app.models.llm_model import ModelsTable
from app.models.llm_channel import ChannelsTable
from app.models.user import UserTabel, UserTokenTabel
from app.models.api_key import ApiKeyTable
from app.models.redeem_code import RedeemCodeTable
from app.models.log import LogsTable
from app.models.chat_record import ChatRecordTable
from app.models.usage_stats import UsageStatsTable
from app.models.usage_summary import UsageSummaryTable
from app.models.system_config import SystemConfigTable
from app.models.agent_session import AgentSessionTable
from app.models.agent_message import AgentMessageTable


__all__ = [
    "BaseModel", "ModelsTable", "ChannelsTable",
    "UserTabel", "UserTokenTabel", "ApiKeyTable", "RedeemCodeTable", "LogsTable",
    "ChatRecordTable", "UsageStatsTable", "UsageSummaryTable", "SystemConfigTable",
    "AgentSessionTable", "AgentMessageTable",
]
