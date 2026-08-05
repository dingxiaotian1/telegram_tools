import asyncio
import difflib
import logging
import logging.handlers
import os
import json
import time
from datetime import datetime

import opencc
import aiomysql
import requests
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

load_dotenv()

# ================== 配置区 ==================
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv("API_HASH")
CHANNEL_USERNAME = os.getenv("CHANNEL_NAME")

# PicGo 路径
PICGO_PATH = os.getenv('PICGO_PATH')

# 日志路径
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log', CHANNEL_USERNAME)
os.makedirs(LOG_DIR, exist_ok=True)

# V2Ray 代理配置
PROXY = {
    'proxy_type': 'socks5',
    'addr': os.getenv('PROXY_HOST'),
    'port': int(os.getenv('PROXY_PORT')),
}

# 数据库配置
db_config = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'db': os.getenv('DB_DB'),
    'charset': 'utf8mb4',
}

# 数据表命名
TABLE_NAME = CHANNEL_USERNAME
TABLE_TAG_NAME = f'{CHANNEL_USERNAME}_tags'

# 初始化 Telegram 客户端
client = TelegramClient(
    'tg_channel_session',
    API_ID,
    API_HASH,
    proxy=PROXY,
)

# 创建保存图片的文件夹
BASE_DIR = f'./channel_data/{CHANNEL_USERNAME}/'
os.makedirs(BASE_DIR, exist_ok=True)

# 已处理的消息ID（防止重复）
processed_ids = set()
PROCESSED_IDS_FILE = os.path.join(BASE_DIR, f'{CHANNEL_USERNAME}_processed_ids.json')

# 不入库的标签
EXCLUDE_TAGS = ['#标签', '#tags', '#标签4', '#标签2']

# 繁体转简体工具
cc = opencc.OpenCC('t2s')

#  日志配置
def _build_file_handler(filename: str, level=logging.INFO) -> logging.handlers.RotatingFileHandler:
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, filename),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    return handler


info_logger = logging.getLogger('quark_info')
info_logger.setLevel(logging.INFO)
info_logger.addHandler(_build_file_handler('info.log'))

title_logger = logging.getLogger('quark_title')
title_logger.setLevel(logging.INFO)
title_logger.addHandler(_build_file_handler('title.log'))

pic_logger = logging.getLogger('quark_pic')
pic_logger.setLevel(logging.INFO)
pic_logger.addHandler(_build_file_handler('pic.log'))

# ================== 数据库建表语句 ==================
create_table_sql = f"""
CREATE TABLE IF NOT EXISTS `{TABLE_NAME}` (
  `message_id` VARCHAR(64) NOT NULL COMMENT '主键，唯一，不自增',
  `title` VARCHAR(255) NOT NULL COMMENT '标题',
  `publish_time` DATETIME NULL COMMENT '发布时间',
  `image_info` TEXT NULL COMMENT '图片（多图存JSON数组）',
  `resource_desc` TEXT NULL COMMENT '资源简介',
  `link_url` VARCHAR(768) NOT NULL COMMENT '资源外部链接',
  `tags` VARCHAR(512) NULL COMMENT '标签，多标签逗号分隔',
  `original_content` LONGTEXT NULL COMMENT '原始完整内容',
  PRIMARY KEY (`message_id`),
  UNIQUE KEY `uk_link_url` (`link_url`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='夸克资源';
"""
create_table_tag_sql = f"""
CREATE TABLE IF NOT EXISTS {TABLE_TAG_NAME} (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    message_id VARCHAR(64) NOT NULL COMMENT '关联 quarkF 表的 message_id',
    tag_name VARCHAR(100) NOT NULL COMMENT '标签名称（含 # 号，如 #科幻）',
    INDEX idx_message_id (message_id) COMMENT '按消息ID查询索引',
    INDEX idx_tag_name (tag_name) COMMENT '按标签名查询索引'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='quarkF 频道标签关联表';
"""

# ================== 数据库插入语句 ==================
insert_sql = f"""
insert ignore into {TABLE_NAME} (message_id, title, image_info, publish_time, resource_desc, link_url, tags, original_content)
values (%s, %s, %s, %s, %s, %s, %s, %s)
"""

# 向标签关联表写入数据的 SQL 语句
insert_tag_sql = f"""
INSERT IGNORE INTO {TABLE_TAG_NAME} (message_id, tag_name)
VALUES (%s, %s)
"""


# 创建连接池
async def create_db_pool():
    pool = await aiomysql.create_pool(
        host=db_config["host"],
        user=db_config["user"],
        password=db_config["password"],
        db=db_config["db"],
        charset=db_config["charset"],
        autocommit=True,
        minsize=1,
        maxsize=5,
    )
    return pool


# 初始化数据库
async def init_database(pool):
    """检查并创建数据库表（如果不存在）"""
    print("🗄️  检查数据库表结构...")
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            # 检查并创建主表
            await cursor.execute(create_table_sql)
            print(f"✅ 数据表 `{TABLE_NAME}` 已就绪")

            # 检查并创建标签关联表
            await cursor.execute(create_table_tag_sql)
            print(f"✅ 数据表 `{TABLE_TAG_NAME}` 已就绪")

    info_logger.info(f"数据库表初始化完成: {TABLE_NAME}, {TABLE_TAG_NAME}")


# 加载历史记录
def load_processed_ids():
    global processed_ids
    if os.path.exists(PROCESSED_IDS_FILE):
        with open(PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f:
            processed_ids = set(json.load(f))
        print(f"📂 已加载 {len(processed_ids)} 条历史记录ID")
        info_logger.info(f"已加载 {len(processed_ids)} 条历史记录ID")
    else:
        info_logger.info("历史记录ID文件不存在，使用空集合")


# 保存历史记录
def save_processed_ids():
    with open(PROCESSED_IDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(processed_ids), f)


# ================== 进度回调 ==================
def progress_callback(current, total, start_time=None):
    if total == 0:
        return
    percent = current / total * 100
    elapsed = time.time() - (start_time or time.time())
    speed = current / elapsed / 1024 if elapsed > 0 else 0

    bar = '█' * int(percent // 5) + '░' * (20 - int(percent // 5))
    print(f"\r[{bar}] {percent:6.2f}% | {current / 1024 / 1024:.2f}/{total / 1024 / 1024:.2f} MB | {speed:.1f} KB/s",
          end='', flush=True)


def extract_info(text):
    """智能提取标题、链接、标签 + 干净的资源简介"""
    record, title, download_links = {}, text, ""

    if CHANNEL_USERNAME in ["quarkF", "FLMdongtianfudi"]:
        from extract_info import quarkF_info
        record, title, download_links = quarkF_info(text)
    elif CHANNEL_USERNAME in ["BooksRealm"]:
        from extract_info import BooksRealm_info
        text = cc.convert(text)
        record, title, download_links = BooksRealm_info(text)

    return record, title, download_links


# ================== PicGo 上传函数 ==================
def upload_with_picgo(local_path: str) -> str:
    """
    通过 PicGo HTTP 接口上传。注意：需本地安装 PicGo 并配置好参数
    参考：https://docs.picgo.app/zh/gui/guide/advance#PicGo-Server%E7%9A%84%E4%BD%BF%E7%94%A8
    """
    filename = os.path.basename(local_path) if local_path else "unknown"
    try:
        url = "http://127.0.0.1:36677/upload"  # PicGo Server 默认地址

        with open(local_path, 'rb') as f:
            filename = os.path.basename(local_path)
            files = {'files': (filename, f, 'image/jpeg')}

            response = requests.post(url, files=files, timeout=80)

        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('result'):
                image_info = data['result'][0] if isinstance(data['result'], list) else data['result']
                info_logger.info(f"PicGo 上传成功: {filename} -> {image_info}")
                return image_info
            else:
                msg = f"PicGo 返回失败: {data.get('message')}"
                print(f"⚠️ {msg}")
                pic_logger.warning(f"{msg} | file={filename}")
        else:
            msg = f"HTTP 错误 {response.status_code}: {response.text}"
            print(f"❌ {msg}")
            pic_logger.error(f"{msg} | file={filename}")

        result = f"failed:{filename}"
        pic_logger.error(f"上传失败返回 {result}")
        return result

    except requests.exceptions.ConnectionError:
        print("❌ PicGo Server 未启动，请在 PicGo 设置中开启 Server")
        pic_logger.critical(f"PicGo Server 未启动 (ConnectionError) | file={filename}")
        return "server_off"
    except Exception as e:
        print(f"❌ 异常: {e}")
        pic_logger.exception(f"PicGo 上传异常: {e} | file={filename}")
        return f"error:{filename}"


# ================== 比较标题 ==================
def get_quark_title(link):
    pwd_id = link.split("/")[-1]
    title = ""
    session = requests.Session()

    token_url = "https://drive-h.quark.cn/1/clouddrive/share/sharepage/token"
    params = {
        "pr": "ucpro",
        "fr": "pc",
        "uc_param_str": "",
    }
    payload = {
        "pwd_id": pwd_id,
        "passcode": "",
        "support_visit_limit_private_share": True,
    }

    res = session.post(token_url, params=params, json=payload)
    try:
        data = res.json()
        if data.get("data") and data["data"].get("title"):
            title = data["data"]["title"]
    except Exception as e:
        print(f"解析 JSON 失败: {e}")
        print(res.text)
        info_logger.error(f"解析 JSON 失败: {e}")
        info_logger.error(res.text)
    finally:
        return title


def compare_title(title1, title2, ):
    """
    比较两个标题/文本的相似度。

    参数:
        title1 -- 夸克原本标题
        title2 -- 电报描述标题
    返回:
        True: 标题一致
        False: 标题不一致
    """
    if not title1 or not title2:
        title_logger.info(f"标题不一致(空值): title1={title1!r} | title2={title2!r}")
        return False
    if title1 == title2:
        return True
    title1_l = title1.lower()
    title2_l = title2.lower()
    similarity = difflib.SequenceMatcher(None, title1_l, title2_l).quick_ratio()
    result = similarity > 0.2
    if not result:
        title_logger.info(
            f"标题不一致(相似度 {similarity:.3f}): "
            f"[夸克]{title1!r} vs [电报]{title2!r}"
        )
    return result


async def download_media_with_progress(message, save_path):
    """带进度的下载"""
    if not message.media:
        return None
    # print(f"📥 下载: {message.id} → {os.path.basename(save_path)}")
    print(f"📥 下载临时文件: {message.id}")
    start_time = time.time()
    try:
        await message.download_media(
            file=save_path,
            progress_callback=lambda c, t: progress_callback(c, t, start_time)
        )
        print(f"\n✅ 下载完成 → 正在上传图床...")

        # # === 上传到 PicGo 图床 ===
        # image_info = upload_with_picgo(save_path)
        image_info = ""

        # if os.path.exists(save_path):
        #     os.remove(save_path)
        return image_info
    except Exception as e:
        print(f"\n❌ 失败 {message.id}: {e}")
        return None


# 写入数据库
async def write_to_sql(record, pool):
    """
    将数据写入 MySQL 数据库（主表 + 标签关联表）

    【写入策略】
      1. 先写入主表 quarkF（原有的 INSERT SQL）
      2. 再写入标签关联表 quarkF_tags（新增优化）
      3. 标签关联表使用 INSERT IGNORE，避免重复写入

    【为什么需要两步写入】
      主表保留 JSON 格式的 tags 字段作为冗余备份，
      关联表提供索引支持的快速标签筛选。
      双写策略确保新旧查询方式都能正常工作。
    """
    fields = [
        record.get("message_id"),
        record.get("标题"),
        record.get("image_info"),
        datetime.fromisoformat(record.get("date").replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M:%S"),
        record.get("资源简介"),
        record.get("链接"),
        json.dumps(record.get("标签"), ensure_ascii=False),
        record.get("原始内容"),
    ]
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(insert_sql, fields)

                tags = record.get("标签", [])
                if tags and isinstance(tags, list):
                    for tag_name in tags:
                        if tag_name in EXCLUDE_TAGS:
                            continue
                        try:
                            await cursor.execute(insert_tag_sql, (record.get("message_id"), tag_name))
                        except Exception as e:
                            print(f"⚠️ 标签关联表写入失败 (message_id={record.get('message_id')}, tag={tag_name}): {e}")
                            info_logger.warning(
                                f"标签关联表写入失败 (message_id={record.get('message_id')}, "
                                f"tag={tag_name}): {e}"
                            )

        info_logger.info(
            f"写入数据库成功: message_id={record.get('message_id')} | "
            f"title={record.get('标题')!r} | tags={record.get('标签')}"
        )
    except Exception as e:
        info_logger.exception(
            f"写入数据库失败: message_id={record.get('message_id')} | "
            f"title={record.get('标题')!r} | err={e}"
        )
        raise


async def fetch_history(entity, pool, limit=300):
    """抓取历史消息"""
    print(f"📜 开始抓取最近 {limit} 条历史消息...")
    info_logger.info(f"开始抓取最近 {limit} 条历史消息")
    count = 0
    async for message in client.iter_messages(entity, limit=limit):
        if message.id in processed_ids:
            continue
        processed_ids.add(message.id)

        text = message.message or ""
        extra, title, link = extract_info(text)

        if not title or not link:
            info_logger.info(f"[历史] message_id={message.id} 被跳过：缺少标题或链接 (title={title!r}, link={link!r})")
            continue

        if "quark" in link and CHANNEL_USERNAME == "quarkF":
            quark_title = get_quark_title(link)
            info_logger.info(
                f"[历史] message_id={message.id} 夸克标题对比: "
                f"quark={quark_title!r} vs tg={title!r}"
            )
            if not compare_title(quark_title, title):
                continue

        image_info = ""
        if message.photo:
            path = os.path.join(BASE_DIR, f"{message.id}.jpg")
            image_info = await download_media_with_progress(message, path)

        record = {
            "message_id": str(message.id),
            "date": message.date.isoformat(),
            "image_info": image_info,
            **extra
        }
        await write_to_sql(record, pool)
        save_processed_ids()
        count += 1
        print(f"📜 [历史] {title[:50]}...")

        await asyncio.sleep(0.6)  # 避免太快触发限制

    print(f"✅ 历史消息抓取完成，共存入数据库 {count} 条")
    info_logger.info(f"✅ 历史消息抓取完成，共存入数据库 {count} 条")


# 全局变量存储连接池
db_pool = None


@client.on(events.NewMessage(chats=CHANNEL_USERNAME))
async def handler(event):
    global db_pool
    msg = event.message
    if msg.id in processed_ids:
        return
    processed_ids.add(msg.id)

    text = msg.message or ""
    extra, title, link = extract_info(text)
    if not title or not link:
        info_logger.info(f"[新消息] message_id={msg.id} 被跳过：缺少标题或链接 (title={title!r}, link={link!r})")
        return

    if "quark" in link and CHANNEL_USERNAME == "quarkF":
        quark_title = get_quark_title(link)
        info_logger.info(
            f"[新消息] message_id={msg.id} 夸克标题对比: "
            f"quark={quark_title!r} vs tg={title!r}"
        )
        if not compare_title(quark_title, title):
            return

    image_info = ""
    if msg.photo:
        path = os.path.join(BASE_DIR, f"{msg.id}.jpg")
        image_info = await download_media_with_progress(msg, path)
    record = {
        "message_id": str(msg.id),
        "date": msg.date.isoformat(),
        "image_info": image_info,
        **extra
    }

    await write_to_sql(record, db_pool)
    save_processed_ids()

    print(f"🟢 [新] {title[:60]}...")
    info_logger.info(f"[新消息] 处理完成: message_id={msg.id} | title={title!r}")


async def main():
    global db_pool
    print("🚀 Telegram Channel Agent 启动中...")
    info_logger.info("=" * 60)
    info_logger.info("Telegram Channel Agent 启动中")
    info_logger.info(f"目标频道: {CHANNEL_USERNAME}")
    info_logger.info(f"代理端口: {PROXY['port']}")
    print(f"目标频道: {CHANNEL_USERNAME}")
    print(f"代理端口: {PROXY['port']}")

    try:
        load_processed_ids()
        db_pool = await create_db_pool()
        print("✅ 数据库连接池已创建")
        info_logger.info("数据库连接池已创建")

        # 自动检查并创建数据库表
        await init_database(db_pool)

        await client.start()
        info_logger.info("Telegram 客户端登录成功")
        entity = await client.get_entity(CHANNEL_USERNAME)
        print(f"✅ 已连接频道: {getattr(entity, 'title', CHANNEL_USERNAME)}")
        info_logger.info(f"已连接频道: {getattr(entity, 'title', CHANNEL_USERNAME)}")

        # 先抓历史
        await fetch_history(entity, db_pool, limit=1000)  # 可改大一点

        print("🔴 开始实时监听新消息...（按 Ctrl+C 停止）")
        info_logger.info("开始实时监听新消息")

    except FloodWaitError as e:
        print(f"⏳ 被 Telegram 限制，请等待 {e.seconds} 秒...")
        info_logger.warning(f"被 Telegram 限制，等待 {e.seconds} 秒: {e}")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        info_logger.exception(f"启动失败: {e}")
        if db_pool:
            db_pool.close()
            await db_pool.wait_closed()
        return

    try:
        await client.run_until_disconnected()
    finally:
        if db_pool:
            db_pool.close()
            await db_pool.wait_closed()
            print("✅ 数据库连接池已关闭")
            info_logger.info("数据库连接池已关闭，程序结束")
        info_logger.info("=" * 60)


"""
部署命令

# 1. 安装 docker-compose
# 2. 把所有文件放好
docker-compose up -d --build
docker logs -f tg-feishu-agent

-- 删除重复，只保留最小 message_id 那条 SQL 语句
START TRANSACTION;
DELETE t1 FROM quarkF t1
JOIN quarkF t2
  ON t1.link_url = t2.link_url
  AND t1.message_id > t2.message_id;
COMMIT;
"""
if __name__ == '__main__':
    asyncio.run(main())
