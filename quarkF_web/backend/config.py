"""
==============================================================================
quarkF 频道数据展示系统 - 配置文件
==============================================================================

【功能】
  集中管理所有配置项，包括数据库连接、服务器参数、缓存策略等。
  所有敏感信息通过环境变量加载，禁止硬编码。

【使用方式】
  from config import settings
  settings.DB_HOST, settings.API_PORT, etc.

【注意事项】
  1. .env 文件必须与 backend/ 目录同级（或在项目根目录）
  2. 修改配置后需要重启服务才能生效
  3. 生产环境中建议使用环境变量而非 .env 文件
==============================================================================
"""

import os
from dotenv import load_dotenv

# ==================== 项目根路径 ====================
# 【重点注释】根据文件位置计算项目根目录（telegram_code）
# 当前路径: telegram_code/quarkF_web/backend/config.py
# 向上 3 级: telegram_code/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==================== 加载 .env 文件 ====================
# 【重点注释】dotenv 会从项目根目录加载 .env 文件
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))


class Settings:
    """
    ==========================================================================
    配置类 - 使用单例模式管理所有配置项
    ==========================================================================

    【属性说明】
      DB_*        : MySQL 数据库连接参数
      API_*       : FastAPI 服务器参数
      CACHE_*     : 缓存策略参数
      IMAGE_*     : 图片资源路径参数
      CHANNEL_*   : Telegram 频道名称

    【注意事项】
      所有属性均为类属性，直接通过 Settings.xxx 访问。
      不要实例化此类，直接使用模块级 settings 对象。
    ==========================================================================
    """

    # ==================== 数据库配置 ====================
    # 【重点注释】数据库连接信息从 .env 文件读取
    DB_HOST: str = os.getenv('DB_HOST', 'localhost')
    """MySQL 主机地址，默认 localhost"""

    DB_USER: str = os.getenv('DB_USER', 'root')
    """MySQL 用户名，默认 root"""

    DB_PASSWORD: str = os.getenv('DB_PASSWORD', '')
    """MySQL 密码，默认空字符串"""

    DB_DB: str = os.getenv('DB_DB', 'telegram_channel')
    """数据库名称，默认 telegram_channel"""

    DB_CHARSET: str = 'utf8mb4'
    """数据库字符集，utf8mb4 支持完整 Unicode（含 emoji）"""

    DB_POOL_MINSIZE: int = 1
    """数据库连接池最小连接数"""

    DB_POOL_MAXSIZE: int = 10
    """数据库连接池最大连接数，根据并发量调整"""

    # ==================== API 服务器配置 ====================
    API_HOST: str = '0.0.0.0'
    """API 监听地址，0.0.0.0 表示监听所有网卡"""

    API_PORT: int = 8000
    """API 监听端口，默认 8000"""

    API_RELOAD: bool = True
    """开发模式自动重载，生产环境应设为 False"""

    # ==================== 缓存配置 ====================
    # 【重点注释】使用 cachetools 实现内存缓存
    CACHE_TAGS_TTL: int = 300
    """标签列表缓存时间（秒），默认 5 分钟"""

    CACHE_LIST_TTL: int = 60
    """数据列表缓存时间（秒），默认 1 分钟"""

    # ==================== 频道配置 ====================
    CHANNEL_NAME: str = os.getenv('CHANNEL_NAME', 'quarkF')
    """Telegram 频道用户名"""

    # ==================== 图片配置 ====================
    # 【重点注释】图片文件命名规则：{message_id}.jpg
    # 图片文件存储在 channel_data/quarkF/ 目录下
    IMAGE_BASE_DIR: str = os.path.join(
        PROJECT_ROOT,
        'channel_data',
        CHANNEL_NAME
    )
    """图片文件存储目录的绝对路径"""

    # ==================== 分页默认值 ====================
    DEFAULT_PAGE_SIZE: int = 20
    """默认每页显示条数"""

    MAX_PAGE_SIZE: int = 100
    """每页最大条数限制，防止恶意请求"""


# ==================== 导出单例 ====================
# 【重点注释】创建全局唯一的配置对象，供其他模块导入使用
settings = Settings()
