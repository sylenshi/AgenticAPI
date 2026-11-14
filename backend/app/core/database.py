"""数据库引擎、会话工厂与初始化"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import setting
from app.models import BaseModel  # 导入 app.models 包会触发所有表定义注册到 BaseModel.metadata

engine = create_async_engine(
    setting.MYSQL_URL,  # 数据库连接字符串
    # 连接级固定会话时区为东八区：库内 CURRENT_TIMESTAMP 默认列与应用 datetime.now() 写入列
    # 统一为 +08:00 口径（服务器系统时区为 UTC，不改这里两种口径会差 8 小时）
    connect_args={"init_command": "SET time_zone='+08:00'"},
    echo=setting.DEBUG,  # 输出数据库语句
    # NullPool：不维护连接池，连接随请求新建、用完即关。
    # 2026-11-14 生产事故复盘：asyncmy 死连接抛 RuntimeError（handler is closed），
    # 不在 pre_ping 可识别的断连错误内，池化连接闲置被服务端掐断后整个连接池逐渐坏死且无法自愈，
    # 所有 DB 接口持续 500。本站低流量，本机新建连接开销毫秒级，
    # NullPool 从根上消灭「死连接池」这一类故障，故不再需要池参数与预 ping。
    poolclass=NullPool,
)

asyncSessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,  # 绑定异步引擎
    expire_on_commit=False,  # 禁用会话过期，保持连接打开
)


async def init_database():
    """
    初始化数据库表结构
    - 如果表不存在，则自动创建
    - 如果表已存在，则跳过（不会重复创建或修改现有表）

    【工作原理】
    1. BaseModel.metadata 中存储了所有继承 BaseModel 的表定义（如 ModelsTable、ChannelsTable）
    2. create_all() 会遍历 metadata 中的所有表，执行 CREATE TABLE IF NOT EXISTS
    3. 新增表只需在 app/models/ 下定义新类并继承 BaseModel，并在 app/models/__init__.py 中导入即可
    """
    try:
        # 使用 run_sync() 在异步引擎上执行同步的 create_all
        async with engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
        print("数据库表初始化完成（已存在的表会被跳过）")
    except Exception as e:
        print(f"数据库表初始化失败：{e}")
        raise


async def get_db():
    """依赖项，获取数据库会话"""
    async with asyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
# 不需要手动 finally + session.close
# async with 上下文管理器退出时自动关闭 AsyncSession
