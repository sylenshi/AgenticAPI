"""工具域聚合：import 即触发全部注册（registry 框架不反向依赖本包，无循环导入）"""

from app.services.agent.tools.channel_tools import register_channel_tools
from app.services.agent.tools.usage_tools import register_usage_tools
from app.services.agent.tools.model_tools import register_model_tools
from app.services.agent.tools.data_tools import register_data_tools
from app.services.agent.tools.ops_tools import register_ops_tools
from app.services.agent.tools.session_tools import register_session_tools
from app.services.agent.tools.skill_tools import register_skill_tools

register_channel_tools()
register_usage_tools()
register_model_tools()
register_data_tools()
register_ops_tools()
register_session_tools()
register_skill_tools()
