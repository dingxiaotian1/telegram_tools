import asyncio
import os
import time
import re
import json

import telethon.tl.types
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import GetFullChannelRequest
from dotenv import load_dotenv

load_dotenv()

# ================== 配置区 ==================
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv("API_HASH")
# CHANNEL_USERNAME = 'weme_download'
CHANNEL_USERNAME = 'TAOSEWEIMI'  # 修改为你需要的频道

PROXY = {
    'proxy_type': 'socks5',
    'addr': os.getenv('PROXY_HOST'),
    'port': int(os.getenv('PROXY_PORT')),
}

client = TelegramClient(
    'tg_channel_session',
    API_ID,
    API_HASH,
    proxy=PROXY,
)

BASE_DIR = f'./channel_data/{CHANNEL_USERNAME}/'
os.makedirs(BASE_DIR, exist_ok=True)

# 已处理的消息ID（防止重复下载）
processed_ids = set()
PROCESSED_IDS_FILE = os.path.join(BASE_DIR, f'{CHANNEL_USERNAME}_processed_ids.json')


def load_processed_ids():
    global processed_ids
    if os.path.exists(PROCESSED_IDS_FILE):
        with open(PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f:
            processed_ids = set(json.load(f))
        print(f"📂 已加载 {len(processed_ids)} 条历史记录ID")


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


async def download_media_with_progress(message, save_path):
    """带进度的下载"""
    if not message.media:
        return None
    print(f"📥 下载: {message.id} → {os.path.basename(save_path)}")
    start_time = time.time()
    try:
        result = await message.download_media(
            file=save_path,
            progress_callback=lambda c, t: progress_callback(c, t, start_time)
        )
        print(f"\n✅ 完成: {os.path.basename(save_path)}")
        return result
    except Exception as e:
        print(f"\n❌ 失败 {message.id}: {e}")
        return None


def get_message_folder(message_id):
    """创建 message_id 文件夹结构"""
    folder = os.path.join(BASE_DIR, str(message_id))
    os.makedirs(os.path.join(folder, "photo"), exist_ok=True)
    os.makedirs(os.path.join(folder, "media"), exist_ok=True)
    os.makedirs(os.path.join(folder, "others"), exist_ok=True)
    os.makedirs(os.path.join(folder, "texts"), exist_ok=True)
    return folder


async def process_message(message):
    """处理单条消息（强化 Album 去重）"""
    if not message or message.id in processed_ids:
        return

    raw_text = message.message or ""
    print(f"\n🆔 消息ID: {message.id} | 时间: {message.date}")

    # ================== Album 处理 ==================
    if getattr(message, 'grouped_id', None) is not None:
        print(f"🎞️ Album 检测 (grouped_id: {message.grouped_id})")
        album_messages = []
        async for msg in client.iter_messages(
                message.chat_id,
                ids=range(message.id - 25, message.id + 25)
        ):
            if msg and getattr(msg, 'grouped_id', None) == message.grouped_id:
                album_messages.append(msg)

        unique_dict = {m.id: m for m in album_messages}
        messages = sorted(unique_dict.values(), key=lambda m: m.id)
    else:
        messages = [message]

    # 使用最小 ID 作为主文件夹
    main_id = min((m.id for m in messages), default=message.id)
    folder = get_message_folder(main_id)

    # ================== 文本 + 超链接 ==================
    formatted_text = raw_text
    links_info = []

    if message.entities:
        for entity in sorted(message.entities, key=lambda e: e.offset, reverse=True):
            if isinstance(entity, (telethon.tl.types.MessageEntityUrl,
                                   telethon.tl.types.MessageEntityTextUrl)):
                start = entity.offset
                end = start + entity.length
                url = getattr(entity, 'url', None) or raw_text[start:end]
                display_text = raw_text[start:end]
                markdown_link = f"[{display_text}]({url})"
                formatted_text = formatted_text[:start] + markdown_link + formatted_text[end:]
                links_info.append({"text": display_text, "url": url})

    # 保存文本
    if raw_text.strip() or links_info:
        text_file = os.path.join(folder, "texts", f"content_{message.id}.txt")
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(f"消息ID: {message.id}\n")
            f.write(f"时间: {message.date}\n\n")
            f.write("=== 正文 ===\n")
            f.write(formatted_text + "\n\n")
            if links_info:
                f.write("=== 提取链接 ===\n")
                for i, link in enumerate(links_info, 1):
                    f.write(f"{i}. [{link['text']}]({link['url']})\n")

    # ================== 下载媒体（关键去重） ==================
    for msg in messages:
        if not msg or not msg.media or msg.id in processed_ids:
            continue

        processed_ids.add(msg.id)  # 立即标记，防止重复

        if msg.photo:
            path = os.path.join(folder, "photo", f"{msg.id}.jpg")
            await download_media_with_progress(msg, path)

        elif msg.video or (getattr(msg.document, 'mime_type', '').startswith('video')):
            ext = ".mp4" if msg.video else os.path.splitext(getattr(msg.file, 'name', ''))[1] or ".mp4"
            path = os.path.join(folder, "media", f"{msg.id}{ext}")
            await download_media_with_progress(msg, path)

        elif msg.document:
            filename = getattr(msg.file, 'name', f"file_{msg.id}")
            path = os.path.join(folder, "others", f"{msg.id}_{filename}")
            await download_media_with_progress(msg, path)

    # 标记主消息
    processed_ids.add(message.id)
    save_processed_ids()  # 每处理完一条/一个 Album 就保存


@client.on(events.NewMessage(chats=CHANNEL_USERNAME))
async def handler(event):
    await process_message(event.message)


async def fetch_history(entity, limit=30):
    print(f"📜 抓取最近 {limit} 条历史消息...")
    async for message in client.iter_messages(entity, limit=limit, reverse=False):
        if message:  # 防止 None
            try:
                await process_message(message)
            except Exception as e:
                print(f"处理消息 {getattr(message, 'id', 'unknown')} 时出错: {e}")
        await asyncio.sleep(0.6)  # 防限流
    save_processed_ids()  # 结束时再保存一次


async def main():
    print("🚀 Telegram Channel Agent 启动中...")
    try:
        load_processed_ids()
        await client.start()
        entity = await client.get_entity(CHANNEL_USERNAME)
        title = getattr(entity, 'title', CHANNEL_USERNAME)

        try:
            if hasattr(entity, 'broadcast') and entity.broadcast:  # 是频道
                full = await client(GetFullChannelRequest(channel=entity))
                sub_count = getattr(full.full_chat, 'participants_count', None)
                if hasattr(full, 'chat') and hasattr(full.chat, 'title'):
                    title = full.chat.title
            else:
                sub_count = getattr(entity, 'participants_count', None)
        except Exception as e:
            print(f"⚠️ 获取订阅者数量失败: {e}")
            sub_count = None

        print(f"✅ 已连接频道: {title}")
        if sub_count is not None:
            print(f"👥 订阅者数量: {sub_count:,} 人")
        else:
            print("👥 订阅者数量: 获取失败或无权限查看")

        await fetch_history(entity, limit=20)

        print("🔴 实时监听中...（Ctrl+C 停止）")
        await client.run_until_disconnected()

    except FloodWaitError as e:
        print(f"⏳ FloodWait {e.seconds}秒...")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())