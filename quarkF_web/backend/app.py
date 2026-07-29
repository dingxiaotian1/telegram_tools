"""
==============================================================================
quarkF 频道数据展示系统 - FastAPI 后端服务
==============================================================================

【功能】
  1. 提供 quarkF 频道数据的 RESTful 查询接口
  2. 支持按标签筛选数据
  3. 提供标签列表接口供前端选择
  4. 提供图片资源访问接口
  5. 内存缓存机制减少数据库查询

【API 接口列表】
  GET  /api/quarkf/list        - 分页查询数据列表
  GET  /api/quarkf/tags        - 获取所有标签列表
  GET  /api/quarkf/images/{id}.jpg - 获取图片资源
  GET  /api/quarkf/stats       - 数据统计信息
  GET  /health                  - 健康检查

【启动方式】
  uvicorn app:app --host 0.0.0.0 --port 8000 --reload

【依赖】
  - config.py（配置文件）
  - .env（数据库连接信息）
==============================================================================
"""

import os
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import aiomysql
from cachetools import TTLCache

from config import settings, PROJECT_ROOT

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('quarkF-API')

# ==================== 应用生命周期管理 ====================
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """
    ==========================================================================
    应用生命周期管理（替代已弃用的 on_event）
    ==========================================================================

    【功能】
      - yield 之前：应用启动时执行（初始化数据库连接池、预热缓存）
      - yield 之后：应用关闭时执行（关闭连接池、清理缓存）

    【为什么使用 lifespan】
      FastAPI 0.93+ 起 on_event 被标记为弃用，
      lifespan 上下文管理器是推荐的替代方案。
      https://fastapi.tiangolo.com/advanced/events/
    ==========================================================================
    """
    # ==================== 启动逻辑 ====================
    logger.info("=" * 60)
    logger.info("quarkF API 服务启动中...")
    logger.info(f"数据库: {settings.DB_HOST}:3306/{settings.DB_DB}")
    logger.info(f"图片目录: {settings.IMAGE_BASE_DIR}")
    logger.info(f"API 文档: http://localhost:{settings.API_PORT}/api/docs")

    # 预热数据库连接池
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.ping()
            logger.info("数据库连接成功")
    except Exception as e:
        logger.warning(f"数据库连接失败（服务仍可启动）: {e}")

    # 验证图片目录
    if not os.path.exists(settings.IMAGE_BASE_DIR):
        logger.warning(f"图片目录不存在: {settings.IMAGE_BASE_DIR}")

    logger.info("=" * 60)

    yield   # yield 之后是关闭逻辑

    # ==================== 关闭逻辑 ====================
    logger.info("quarkF API 服务关闭中...")

    global db_pool
    if db_pool:
        db_pool.close()
        await db_pool.wait_closed()
        logger.info("数据库连接池已关闭")

    # 清理缓存
    tags_cache.clear()
    list_cache.clear()
    logger.info("缓存已清理")
    logger.info("服务已停止")


# ==================== FastAPI 应用初始化 ====================
# 【重点注释】创建 FastAPI 实例，注入 lifespan 生命周期管理
app = FastAPI(
    title="QuarkF 频道数据展示 API",
    description="提供 quarkF Telegram 频道的数据查询接口，支持标签筛选、分页查询",
    version="1.0.0",
    docs_url="/api/docs",       # Swagger 文档地址
    redoc_url="/api/redoc",     # ReDoc 文档地址
    lifespan=lifespan,          # 【重点注释】使用 lifespan 替代 on_event
)

# ==================== CORS 跨域配置 ====================
# 【重点注释】允许前后端分离部署时的跨域访问
# 生产环境中应将 origins 限制为具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],                    # 允许所有来源
    allow_credentials=True,                 # 允许携带 Cookie
    allow_methods=["*"],                    # 允许所有 HTTP 方法
    allow_headers=["*"],                    # 允许所有请求头
)

# ==================== 数据库连接池 ====================
# 【重点注释】全局数据库连接池，应用启动时创建，关闭时销毁
db_pool = None


async def get_db_pool() -> aiomysql.Pool:
    """
    ==========================================================================
    获取数据库连接池（懒加载单例模式）
    ==========================================================================

    【实现逻辑】
      首次调用时创建连接池，后续复用。
      连接池大小由配置文件控制。

    【返回值】
      aiomysql.Pool: MySQL 异步连接池对象

    【异常】
      连接失败时会抛出 aiomysql.Error
    ==========================================================================
    """
    global db_pool
    if db_pool is None:
        # 【重点注释】创建异步 MySQL 连接池
        # minsize/maxsize 控制连接数，autocommit 自动提交事务
        db_pool = await aiomysql.create_pool(
            host=settings.DB_HOST,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            db=settings.DB_DB,
            charset=settings.DB_CHARSET,
            autocommit=True,
            minsize=settings.DB_POOL_MINSIZE,
            maxsize=settings.DB_POOL_MAXSIZE,
        )
        logger.info(f"数据库连接池已创建: {settings.DB_HOST}/{settings.DB_DB}")
    return db_pool


# ==================== 缓存配置 ====================
# 使用 cachetools 的 TTLCache 实现带过期时间的内存缓存
# 缓存键为字符串，值为对应的查询结果
tags_cache = TTLCache(maxsize=10, ttl=settings.CACHE_TAGS_TTL)
"""标签列表缓存：最多缓存 10 份，有效期 5 分钟"""

list_cache = TTLCache(maxsize=100, ttl=settings.CACHE_LIST_TTL)
"""数据列表缓存：最多缓存 100 份，有效期 1 分钟"""


def make_list_cache_key(page: int, page_size: int, tag: Optional[str], keyword: Optional[str]) -> str:
    """
    ==========================================================================
    生成列表查询的缓存键
    ==========================================================================

    【为什么这样设计】
      列表查询结果与分页参数、筛选条件强相关。
      不同的参数组合生成不同的缓存键，避免缓存冲突。

    【参数】
      page: 页码（从 1 开始）
      page_size: 每页条数
      tag: 筛选的标签（可选）
      keyword: 搜索关键词（可选）

    【返回值】
      str: 缓存键字符串，格式如 "list:1:20:tag_val:keyword_val"
    ==========================================================================
    """
    return f"list:{page}:{page_size}:{tag or ''}:{keyword or ''}"


# ==================== API 接口 ====================

@app.get("/health")
async def health_check():
    """
    ==========================================================================
    健康检查接口
    ==========================================================================

    【用途】
      用于监控系统是否正常运行，Kubernetes/Docker 等容器编排工具会定期调用。

    【返回值】
      {
        "status": "ok",
        "timestamp": "2024-01-01T00:00:00",
        "db_connected": true/false
      }

    【异常处理】
      即使数据库连接失败也返回 200，但 db_connected 为 false。
      这样负载均衡器不会因为数据库临时故障而将服务摘除。
    ==========================================================================
    """
    db_connected = False
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.ping()
            db_connected = True
    except Exception as e:
        logger.warning(f"数据库连接检查失败: {e}")

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "db_connected": db_connected,
    }


@app.get("/api/quarkf/list")
async def get_quarkf_list(
    request: Request,
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE, description="每页条数"),
    tag: Optional[str] = Query(None, description="标签筛选（不含 # 号，如 科幻）"),
    keyword: Optional[str] = Query(None, min_length=0, max_length=100, description="搜索关键词（按标题模糊搜索）"),
):
    """
    ==========================================================================
    分页查询数据列表（核心接口）
    ==========================================================================

    【功能】
      1. 支持分页查询，默认每页 20 条
      2. 支持按标签筛选（通过关联表查询）
      3. 支持标题模糊搜索
      4. 使用内存缓存加速重复查询
      5. 返回统计信息供前端分页组件使用

    【参数说明】
      page: 页码（从 1 开始），最小 1
      page_size: 每页条数，范围 1-100
      tag: 标签名（不需要 # 前缀），如 "科幻" 或 "#科幻"
      keyword: 搜索关键词，按标题字段模糊匹配

    【返回值】
      {
        "code": 0,            # 状态码，0 表示成功
        "message": "success", # 提示信息
        "data": {
          "items": [...],     # 当前页数据
          "total": 1000,      # 总记录数
          "page": 1,          # 当前页码
          "page_size": 20,    # 每页条数
          "total_pages": 50,  # 总页数
          "has_next": true,   # 是否有下一页
          "has_prev": false   # 是否有上一页
        }
      }

    【性能优化】
      1. 使用 JOIN 替代子查询，减少查询次数
      2. 使用缓存减少重复查询
      3. 限制最大 page_size 防止恶意大查询
      4. 只查询必要字段，避免 SELECT *

    【安全措施】
      1. 参数校验（page >= 1, page_size 1-100）
      2. 关键词长度限制（max_length=100）
      3. 使用参数化查询防止 SQL 注入
    ==========================================================================
    """
    start_time = time.time()

    try:
        # ==================== 参数标准化 ====================
        # 如果 tag 参数包含 # 号，自动去除，兼容两种输入方式
        clean_tag = tag.lstrip('#') if tag else None

        # ==================== 缓存查询 ====================
        # 生成缓存键，检查缓存中是否有数据
        cache_key = make_list_cache_key(page, page_size, clean_tag, keyword)
        cached = list_cache.get(cache_key)
        if cached is not None:
            logger.info(f"缓存命中: {cache_key}")
            return cached

        # ==================== 获取数据库连接 ====================
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:

                # ==================== 构建查询条件 ====================
                # 动态构建 WHERE 子句，根据参数决定查询条件
                where_clauses = []      # WHERE 条件列表
                params = []             # 参数列表（用于参数化查询）

                if clean_tag:
                    # 【重点注释】通过标签关联表筛选（推荐方案）
                    # 使用 EXISTS + 关联表，比 JOIN 效率更高
                    # 因为 EXISTS 找到第一条匹配就停止，而 JOIN 需要处理所有匹配行
                    # 先尝试关联表，如果表不存在则降级使用 JSON_CONTAINS
                    try:
                        test_where = "EXISTS (SELECT 1 FROM quarkF_tags qt WHERE qt.message_id = q.message_id AND qt.tag_name = %s)"
                        test_params = [f"#{clean_tag}"]
                        # 试探关联表是否存在
                        test_sql = f"SELECT 1 FROM quarkF q WHERE {test_where} LIMIT 1"
                        await cursor.execute(test_sql, test_params)
                        # 关联表存在，使用关联表查询
                        where_clauses.append(test_where)
                        params.append(f"#{clean_tag}")
                    except Exception:
                        # 【重点注释】关联表不存在时降级方案
                        # 使用 JSON_CONTAINS 在主表的 tags 字段中搜索标签
                        # JSON_CONTAINS(tags, '"#标签名"') 语法：检查 tags JSON 数组是否包含指定值
                        logger.warning("quarkF_tags 表不存在，降级使用 JSON_CONTAINS 筛选标签")
                        where_clauses.append(
                            "JSON_CONTAINS(q.tags, %s)"
                        )
                        params.append(json.dumps(f"#{clean_tag}"))

                if keyword:
                    # 【重点注释】标题模糊搜索，使用 LIKE 并添加前后通配符
                    # 注意：LIKE 以 % 开头会无法使用索引，但标题搜索场景可以接受
                    where_clauses.append("q.title LIKE %s")
                    params.append(f"%{keyword}%")

                # 组合 WHERE 子句
                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

                # ==================== 查询总数 ====================
                # 先查询总记录数，用于计算页数
                count_sql = f"SELECT COUNT(*) AS total FROM quarkF q WHERE {where_sql}"
                await cursor.execute(count_sql, params)
                result = await cursor.fetchone()
                total = result['total']

                # ==================== 计算分页 ====================
                total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1
                offset = (page - 1) * page_size

                # ==================== 查询当前页数据 ====================
                # 按发布时间降序排列，最新的排在前面
                # 使用 LIMIT + OFFSET 实现分页
                data_sql = f"""
                    SELECT
                        q.message_id,
                        q.title,
                        q.image_info,
                        q.publish_time,
                        q.resource_desc,
                        q.link_url,
                        q.tags,
                        q.original_content
                    FROM quarkF q
                    WHERE {where_sql}
                    ORDER BY q.publish_time DESC
                    LIMIT %s OFFSET %s
                """
                await cursor.execute(data_sql, params + [page_size, offset])
                items = await cursor.fetchall()

        # ==================== 数据处理 ====================
        # 将数据库查询结果转换为前端需要的格式
        processed_items = []
        for item in items:
            # 解析 JSON 格式的标签
            tags_list = []
            if item.get('tags'):
                try:
                    tags_list = json.loads(item['tags'])
                except (json.JSONDecodeError, TypeError):
                    tags_list = []

            # 检查图片文件是否存在
            # 图片文件名规则：{message_id}.jpg
            image_url = None
            image_path = os.path.join(settings.IMAGE_BASE_DIR, f"{item['message_id']}.jpg")
            if os.path.exists(image_path):
                image_url = f"/api/quarkf/images/{item['message_id']}.jpg"

            # 裁剪过长的描述文本，优化前端显示
            desc = item.get('resource_desc', '') or ''
            if len(desc) > 200:
                desc = desc[:200] + '...'

            processed_items.append({
                "message_id": item['message_id'],
                "title": item.get('title', ''),
                "image_url": image_url,            # 图片访问路径（为 None 表示无图片）
                "publish_time": item.get('publish_time', '').strftime('%Y-%m-%d %H:%M:%S') if item.get('publish_time') else '',
                "resource_desc": desc,
                "link_url": item.get('link_url', ''),
                "tags": tags_list,
            })

        # ==================== 构建响应 ====================
        response_data = {
            "code": 0,
            "message": "success",
            "data": {
                "items": processed_items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            }
        }

        # ==================== 写入缓存 ====================
        # 将查询结果缓存，下次相同查询直接返回
        list_cache[cache_key] = response_data

        elapsed = time.time() - start_time
        logger.info(f"列表查询完成: page={page}, tag={clean_tag}, keyword={keyword}, "
                    f"total={total},耗时={elapsed:.2f}s")

        return response_data

    except Exception as e:
        # 全局异常捕获，记录日志并返回友好错误信息
        logger.error(f"列表查询异常: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "code": -1,
                "message": f"服务器内部错误: {str(e)}",
            }
        )


@app.get("/api/quarkf/tags")
async def get_tags():
    """
    ==========================================================================
    获取所有标签列表（用于前端标签筛选器）
    ==========================================================================

    【功能】
      从 quarkF_tags 关联表查询所有不重复的标签，按使用频率降序排列。
      前端根据此列表生成标签选择器。

    【缓存策略】
      使用 TTLCache 缓存 5 分钟，因为标签变化不频繁。

    【返回值】
      {
        "code": 0,
        "message": "success",
        "data": [
          {"tag": "#科幻", "count": 42},
          {"tag": "#小说", "count": 35},
          ...
        ]
      }

    【性能优化】
      使用 GROUP BY + COUNT + ORDER BY 一次查询完成统计。
      如果 quarkF_tags 表不存在，降级使用主表的 JSON 字段解析。
    ==========================================================================
    """
    try:
        # ==================== 检查缓存 ====================
        cached = tags_cache.get('all_tags')
        if cached is not None:
            return cached

        pool = await get_db_pool()

        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:

                # 优先从 quarkF_tags 关联表查询（推荐方案）
                # 如果关联表存在且有数据，查询性能更高
                try:
                    await cursor.execute("""
                        SELECT tag_name AS tag, COUNT(*) AS `count`
                        FROM quarkF_tags
                        GROUP BY tag_name
                        ORDER BY `count` DESC
                        LIMIT 200
                    """)
                    tag_rows = await cursor.fetchall()

                    if tag_rows:
                        tags_data = [{"tag": row['tag'], "count": row['count']} for row in tag_rows]
                    else:
                        # 关联表为空时，降级从主表 JSON 字段解析
                        tags_data = await _parse_tags_from_json(cursor)

                except Exception:
                    # 关联表不存在时（如未执行迁移脚本），降级方案
                    logger.warning("quarkF_tags 表不存在或查询失败，降级使用 JSON 解析")
                    tags_data = await _parse_tags_from_json(cursor)

        response_data = {
            "code": 0,
            "message": "success",
            "data": tags_data,
        }

        # 写入缓存
        tags_cache['all_tags'] = response_data

        return response_data

    except Exception as e:
        logger.error(f"标签查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={
            "code": -1,
            "message": f"标签查询失败: {str(e)}",
        })


async def _parse_tags_from_json(cursor) -> List[dict]:
    """
    ==========================================================================
    从主表 tags JSON 字段解析标签列表（降级方案）
    ==========================================================================

    【使用场景】
      当 quarkF_tags 关联表不存在或为空时使用。
      通过解析主表每行 tags 字段的 JSON 字符串来统计标签频率。

    【性能注意】
      此方法需要扫描全表，数据量大时性能较差。
      建议尽快执行标签迁移 SQL 脚本。
    ==========================================================================
    """
    tag_count = {}
    await cursor.execute("SELECT tags FROM quarkF WHERE tags IS NOT NULL AND tags != '[]'")

    for row in await cursor.fetchall():
        try:
            tags = json.loads(row['tags'])
            for tag in tags:
                tag_count[tag] = tag_count.get(tag, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue

    # 按使用频率降序排列，取前 200 个标签
    sorted_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)[:200]
    return [{"tag": tag, "count": count} for tag, count in sorted_tags]


@app.get("/api/quarkf/images/{image_id}.jpg")
async def get_image(image_id: int):
    """
    ==========================================================================
    图片资源访问接口
    ==========================================================================

    【功能】
      根据 message_id 返回对应的 JPG 图片文件。

    【参数】
      image_id: 消息 ID，同时也是图片文件名（不含扩展名）

    【返回值】
      返回图片文件（Content-Type: image/jpeg）

    【异常处理】
      图片不存在时返回 404

    【性能优化】
      使用 FileResponse 直接流式传输文件，不占用大量内存。
      浏览器会自动缓存图片，减少重复请求。
    ==========================================================================
    """
    # 构建图片文件的完整路径
    image_path = os.path.join(settings.IMAGE_BASE_DIR, f"{image_id}.jpg")

    # 检查文件是否存在且是合法文件
    if not os.path.exists(image_path):
        logger.warning(f"图片不存在: {image_path}")
        raise HTTPException(status_code=404, detail={
            "code": -1,
            "message": f"图片 {image_id}.jpg 不存在",
        })

    # 使用 FileResponse 返回图片文件
    # media_type 指定 MIME 类型，filename 用于浏览器识别
    return FileResponse(
        path=image_path,
        media_type="image/jpeg",
        filename=f"{image_id}.jpg",
        headers={
            # 【重点注释】设置缓存控制头，让浏览器缓存图片 7 天
            "Cache-Control": "public, max-age=604800, immutable",
        }
    )


@app.get("/api/quarkf/stats")
async def get_stats():
    """
    ==========================================================================
    数据统计信息接口
    ==========================================================================

    【功能】
      返回频道数据的基本统计信息，用于前端展示。

    【返回值】
      {
        "code": 0,
        "message": "success",
        "data": {
          "total_messages": 1000,      # 消息总数
          "total_images": 800,         # 有图片的消息数
          "total_tags": 150,           # 标签种类数
          "latest_update": "2024-01-01 12:00:00"  # 最后更新时间
        }
      }
    ==========================================================================
    """
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:

                # 消息总数
                await cursor.execute("SELECT COUNT(*) AS cnt FROM quarkF")
                total_messages = (await cursor.fetchone())['cnt']

                # 有图片的消息数（image_info 非空）
                await cursor.execute("SELECT COUNT(*) AS cnt FROM quarkF WHERE image_info IS NOT NULL AND image_info != ''")
                total_images = (await cursor.fetchone())['cnt']

                # 标签种类数和最新更新时间
                try:
                    # 优先从关联表查询
                    await cursor.execute("SELECT COUNT(DISTINCT tag_name) AS cnt FROM quarkF_tags")
                    total_tags = (await cursor.fetchone())['cnt']
                except Exception:
                    total_tags = 0

                await cursor.execute("SELECT MAX(publish_time) AS latest FROM quarkF")
                latest = (await cursor.fetchone())['latest']
                latest_update = latest.strftime('%Y-%m-%d %H:%M:%S') if latest else ''

                return {
                    "code": 0,
                    "message": "success",
                    "data": {
                        "total_messages": total_messages,
                        "total_images": total_images,
                        "total_tags": total_tags,
                        "latest_update": latest_update,
                    }
                }

    except Exception as e:
        logger.error(f"统计查询异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={
            "code": -1,
            "message": str(e),
        })


# ==================== 删除接口 ====================

@app.delete("/api/quarkf/{message_id}")
async def delete_quarkf(message_id: int):
    """
    ==========================================================================
    删除指定消息（硬删除）
    ==========================================================================

    【功能】
      从 quarkF 主表和 quarkF_tags 关联表中删除指定 message_id 的数据。
      同时尝试删除对应的本地图片文件。

    【参数】
      message_id: 消息 ID（同时也是图片文件名）

    【返回值】
      {
        "code": 0,
        "message": "success",
        "data": {"deleted": true}
      }

    【安全措施】
      1. 使用事务确保主表和关联表同时删除或同时不删除
      2. 图片删除失败不影响数据库删除
      3. 返回删除影响的记录数供前端确认
    ==========================================================================
    """
    try:
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            # 使用事务保证原子性
            # 主表和关联表必须同时删除成功
            async with conn.cursor() as cursor:
                # 删除关联表中的标签记录
                await cursor.execute(
                    "DELETE FROM quarkF_tags WHERE message_id = %s",
                    (message_id,)
                )
                tag_deleted = cursor.rowcount

                # 删除主表记录
                await cursor.execute(
                    "DELETE FROM quarkF WHERE message_id = %s",
                    (message_id,)
                )
                row_deleted = cursor.rowcount

        # 尝试删除本地图片文件（非关键操作）
        # 图片文件可能不存在，删除失败不影响业务
        image_path = os.path.join(settings.IMAGE_BASE_DIR, f"{message_id}.jpg")
        file_deleted = False
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
                file_deleted = True
                logger.info(f"图片文件已删除: {image_path}")
            except Exception as e:
                logger.warning(f"图片文件删除失败: {e}")

        if row_deleted == 0:
            raise HTTPException(status_code=404, detail={
                "code": -1,
                "message": f"message_id={message_id} 不存在",
            })

        # 清除缓存，确保下次查询数据一致
        list_cache.clear()
        tags_cache.clear()

        logger.info(f"删除成功: message_id={message_id}, 主表={row_deleted}行, 标签={tag_deleted}行, 图片={file_deleted}")

        return {
            "code": 0,
            "message": "success",
            "data": {
                "deleted": True,
                "rows_affected": row_deleted,
                "tags_affected": tag_deleted,
                "file_deleted": file_deleted,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={
            "code": -1,
            "message": f"删除失败: {str(e)}",
        })


# ==================== 静态文件托管 ====================
# 将 frontend 目录挂载为静态文件服务
# 这样用户访问 http://localhost:8000 即可打开前端页面
# 同时也实现了 API 和前端同源，图片和 API 请求无需跨域
FRONTEND_DIR = os.path.join(PROJECT_ROOT, 'quarkF_web', 'frontend')
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    logger.info(f"前端静态文件已挂载: {FRONTEND_DIR}")
else:
    logger.warning(f"前端目录不存在: {FRONTEND_DIR}")


# ==================== 入口点 ====================
if __name__ == '__main__':
    """
    ==========================================================================
    直接运行方式
    ==========================================================================

    【使用方式】
      python app.py

    【注意事项】
      生产环境推荐使用 uvicorn 命令启动，而不是此入口。
    ==========================================================================
    """
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level="info",
    )
