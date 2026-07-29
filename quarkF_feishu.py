# pip install telethon PySocks python-socks
import asyncio
import os
import re
from datetime import datetime, timedelta
import requests
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

load_dotenv()
# ================== 配置区 ==================
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv("API_HASH")
CHANNEL_USERNAME = 'quarkF'

# V2Ray 代理配置
PROXY = {
    'proxy_type': 'socks5',
    'addr': os.getenv('PROXY_HOST'),
    'port': int(os.getenv('PROXY_PORT')),
}

# 飞书配置  - https://open.feishu.cn/app
FEISHU_APP_ID = os.getenv('FEISHU_APP_ID')
FEISHU_APP_SECRET = os.getenv('FEISHU_APP_SECRET')
APP_TOKEN = os.getenv('APP_TOKEN')
TABLE_ID = os.getenv('TABLE_ID')

# 初始化 Telegram 客户端
client = TelegramClient(
    'tg_channel_session',
    API_ID,
    API_HASH,
    proxy=PROXY,
)

# 已处理的消息ID（防止重复）
processed_ids = set()

# Token 缓存
token_cache = {"token": None, "expire_time": None}


# 获取飞书 token
def get_feishu_token():
    if token_cache["token"] and token_cache["expire_time"] > datetime.now():
        return token_cache["token"]
    try:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        data = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
        resp = requests.post(url, json=data).json()
        token = resp.get("tenant_access_token")
        token_cache["token"] = token
        token_cache["expire_time"] = datetime.now() + timedelta(seconds=7000)  # 提前刷新
        print("🔄 Token 已刷新")
        return token
    except Exception as e:
        print(f"Token 获取失败: {e}")
        return None


def extract_info(text):
    """智能提取标题、链接、标签 + 干净的资源简介"""
    advertising = "Telegram必备的搜索引擎，极搜JISOU帮你精准找到，想要的群组、频道、视频、音乐"
    if not text:
        return {}, text

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    title = lines[0] if lines else ""
    if advertising in title:
        return {}, ""

    # 提取下载链接
    links = re.findall(r'https?://[^\s]+', text)
    download_links = '\n'.join(links)

    # 提取标签
    tags = re.findall(r'#\w+', text)
    tags = list(set(tags))

    # 去掉标题行
    description = re.sub(r'^.*?\n', '', text, count=1).strip()

    # 去掉标签行、下载链接行、‼️ 行
    description = re.sub(r'🏷️.*?#.*?\n', '', description, flags=re.DOTALL)
    description = re.sub(r'🔗.*?(https?://[^\s]+)', '', description, flags=re.DOTALL)
    description = re.sub(r'‼️.*?(\n|$)', '', description, flags=re.DOTALL)
    description = re.sub(r'📝 资源介绍：\s*', '', description)

    # 清理多余空行
    description = re.sub(r'\n\s*\n', '\n\n', description).strip()

    record = {
        "标题": title,
        "资源简介": description,
        "链接": download_links,
        "标签": tags,
        "原始内容": text,
    }
    return record, title


# 写入飞书多维表格
def write_to_feishu(record):
    token = get_feishu_token()
    if not token:
        return False
    try:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        fields = {
            # "Message_ID": record.get("message_id"),
            "标题": record.get("标题"),
            "发布时间": datetime.fromisoformat(record.get("date").replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M:%S"),
            "资源简介": record.get("资源简介"),
            "链接": record.get("链接"),
            "标签": record.get("标签"),
            "原始内容": record.get("原始内容"),
        }
        resp = requests.post(url, json={"fields": fields}, headers=headers, timeout=15)

        if resp.status_code == 200:
            print("✅ 飞书写入成功！")
            return True
        else:
            print(f"❌ 飞书错误: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"飞书异常: {e}")
        return False


async def fetch_history(entity, limit=300):
    """抓取历史消息"""
    print(f"📜 开始抓取最近 {limit} 条历史消息...")
    count = 0
    async for message in client.iter_messages(entity, limit=limit):
        if message.id in processed_ids:
            continue
        processed_ids.add(message.id)

        text = message.message or ""
        extra, title = extract_info(text)

        record = {
            "message_id": str(message.id),
            "date": message.date.isoformat(),
            **extra
        }
        if not title:
            continue

        write_to_feishu(record)
        print(f"📜 [历史] {title[:50]}...")

        await asyncio.sleep(0.1)  # 避免太快触发限制

    print(f"✅ 历史消息抓取完成，共处理 {count} 条")


@client.on(events.NewMessage(chats=CHANNEL_USERNAME))
async def handler(event):
    msg = event.message
    if msg.id in processed_ids:
        return
    processed_ids.add(msg.id)

    text = msg.message or ""
    extra, title = extract_info(text)
    if not title:
        return

    record = {
        "message_id": str(msg.id),
        "date": msg.date.isoformat(),
        **extra
    }

    write_to_feishu(record)

    print(f"🟢 [新] {title[:60]}...")


async def main():
    print("🚀 Telegram Channel Agent 启动中...")
    print(f"目标频道: {CHANNEL_USERNAME}")
    print(f"代理端口: {PROXY['port']}")

    try:
        await client.start()
        entity = await client.get_entity(CHANNEL_USERNAME)
        print(f"✅ 已连接频道: {getattr(entity, 'title', CHANNEL_USERNAME)}")

        # 先抓历史
        await fetch_history(entity, limit=300)  # 可改大一点

        print("🔴 开始实时监听新消息...（按 Ctrl+C 停止）")

    except FloodWaitError as e:
        print(f"⏳ 被 Telegram 限制，请等待 {e.seconds} 秒...")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return

    await client.run_until_disconnected()


"""
部署命令

# 1. 安装 docker-compose
# 2. 把所有文件放好
docker-compose up -d --build
docker logs -f tg-feishu-agent
"""
if __name__ == '__main__':
    asyncio.run(main())
