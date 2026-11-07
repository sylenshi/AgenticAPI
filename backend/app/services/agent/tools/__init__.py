"""工具域聚合：import 即触发全部注册（registry 框架不反向依赖本包，无循环导入）
v0.11.0 精简后 23 个工具（渠道 6 / 上游 1 / 模型 6 / 运营 3 / 技能 4 / 沙箱 2 / 搜索 1）；
会话域不再有独立工具（模型切换走前端选择器），数据治理域仅保留巡检用的 _table_stats 内部函数（data_tools.py）。
"""

from app.services.agent.tools.channel_tools import register_channel_tools
from app.services.agent.tools.usage_tools import register_usage_tools
from app.services.agent.tools.model_tools import register_model_tools
from app.services.agent.tools.ops_tools import register_ops_tools
from app.services.agent.tools.skill_tools import register_skill_tools
from app.services.agent.tools.sandbox_tools import register_sandbox_tools
from app.services.agent.tools.web_tools import register_web_tools

register_channel_tools()
register_usage_tools()
register_model_tools()
register_ops_tools()
register_skill_tools()
register_sandbox_tools()
register_web_tools()
