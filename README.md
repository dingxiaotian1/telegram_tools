# Telegram 频道数据工具箱

[![Python](https://img.shields.io/badge/Python-3.9+-blue)](https://www.python.org/)
[![Telethon](https://img.shields.io/badge/Telethon-1.34+-green)](https://docs.telethon.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.4+-brightgreen)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 目录

- [项目概述](#项目概述)
- [三种使用模式](#三种使用模式)
  - [模式一：存储到 MySQL 数据库](#模式一存储到-mysql-数据库)
  - [模式二：存储到飞书多维表格](#模式二存储到飞书多维表格)
  - [模式三：下载媒体文件到本地](#模式三下载媒体文件到本地)
- [快速开始](#快速开始)
  - [环境要求](#环境要求)
  - [第一步：获取 Telegram API 凭证](#第一步获取-telegram-api-凭证)
  - [第二步：配置代理（SOCKS5）](#第二步配置代理socks5)
  - [第三步：配置飞书多维表格（可选）](#第三步配置飞书多维表格可选)
  - [第四步：配置 MySQL 数据库（可选）](#第四步配置-mysql-数据库可选)
  - [第五步：安装依赖](#第五步安装依赖)
  - [第六步：启动采集](#第六步启动采集)
- [数据展示系统](#数据展示系统)
  - [启动 Web 服务](#启动-web-服务)
  - [API 文档](#api-文档)
  - [标签存储优化](#标签存储优化)
- [项目结构](#项目结构)
- [完整 .env 配置参考](#完整-env-配置参考)
- [FAQ](#faq)
- [技术栈](#技术栈)
- [许可证](#许可证)

---

## 项目概述

本项目围绕 **Telegram 频道数据采集** 这个核心需求，提供了三种不同用途的采集脚本和一个 Web 展示系统：

| 脚本 | 用途 | 目标 |
|------|------|------|
| [quarkF_sql.py](quarkF_sql.py) | 结构化数据采集 → MySQL | 存储到数据库，供 Web 展示或数据分析 |
| [quarkF_feishu.py](quarkF_feishu.py) | 结构化数据采集 → 飞书 | 存储到飞书多维表格，协作共享 |
| [media_channel.py](media_channel.py) | 媒体文件下载 → 本地 | 下载图片/视频/文档到按 message_id 组织的文件夹 |
| [quarkF_web/](quarkF_web/) | Web 数据展示 | 浏览器中浏览、筛选、搜索、管理数据 |

> **注意**：`quarkF` 只是示例频道名。所有脚本均可通过修改 `CHANNEL_USERNAME` 变量指向任意 Telegram 频道。

---

## 三种使用模式

### 模式一：存储到 MySQL 数据库

**脚本**：[quarkF_sql.py](quarkF_sql.py)

从频道消息中提取标题、标签、链接、资源描述等结构化信息，写入 MySQL 数据库。

**数据流向**：
```
Telegram 频道 → Telethon 抓取 → 正则解析 → MySQL（主表 quarkF + 标签关联表 quarkF_tags）
```

**适用场景**：
- 需要长期积累频道资源库
- 需要对外提供 API 或 Web 展示
- 需要对数据做二次分析

**关键文件**：
- `.env` — 数据库连接信息
- `quarkF_web/backend/tag_migration.sql` — 数据库建表与优化 SQL

### 模式二：存储到飞书多维表格

**脚本**：[quarkF_feishu.py](quarkF_feishu.py)

将频道消息的结构化信息写入飞书多维表格，适合团队协作共享。

**数据流向**：
```
Telegram 频道 → Telethon 抓取 → 正则解析 → 飞书多维表格 API
```

**适用场景**：
- 团队需要协作查看频道资源
- 已有飞书工作流，希望整合数据
- 需要飞书的权限管理和分享能力

### 模式三：下载媒体文件到本地

**脚本**：[media_channel.py](media_channel.py)

将频道中的图片、视频、文档等媒体文件下载到本地文件夹，按消息 ID 组织目录结构。

**数据流向**：
```
Telegram 频道 → Telethon 抓取 → 本地文件系统（按 message_id 分文件夹）
```

**本地目录结构**：
```
channel_data/
  └── {CHANNEL_USERNAME}/
      └── {message_id}/            # 每条消息一个文件夹，以消息 ID 命名
          ├── photo/               # 照片/图片文件
          │   └── {msg_id}.jpg
          ├── media/               # 视频文件
          │   └── {msg_id}.mp4
          ├── others/              # 文档等其他文件
          │   └── {msg_id}_filename.pdf
          └── texts/               # 消息文本
              └── content_{msg_id}.txt
```

**适用场景**：
- 需要备份频道中的所有媒体资源
- 需要离线浏览频道内容
- 频道以图片/视频分享为主

**Album 处理**：自动识别相册消息（Album/grouped_id），将同一相册的消息合并到同一文件夹，以最小消息 ID 命名。

---

## 快速开始

### 环境要求

| 软件 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.9+（推荐 3.11） | 所有脚本的运行环境 |
| MySQL | 5.7+（可选） | 仅使用模式一需要 |
| 飞书 | 企业版（可选） | 仅使用模式二需要 |

### 第一步：获取 Telegram API 凭证

Telegram 要求通过 API 凭证才能访问其服务，获取方式如下：

1. 打开浏览器访问 **https://my.telegram.org**
2. 使用你的 Telegram 账号**手机号登录**（需要能接收短信验证码）
3. 点击上方的 **API development tools** 选项卡
4. 如果第一次使用，点击 **Create new application** 创建一个应用
   - **App title**：随便填，如 `channel_tool`
   - **Short name**：随便填，如 `channel_tool`
   - **URL**：可不填
   - **Platform**：Desktop
5. 提交后你会看到：
   - **`api_id`**：一串数字，如 `12345678`
   - **`api_hash`**：一串字母数字混合字符串，如 `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`

将这两个值填入 `.env` 文件：
```ini
API_ID=12345678
API_HASH=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

> **注意**：首次运行脚本时，Telegram 会要求输入手机号和验证码进行登录，session 会自动保存到 `tg_channel_session.session` 文件，后续运行无需重复登录。

### 第二步：配置代理（SOCKS5）

由于 Telegram 在中国大陆无法直连，需要通过 SOCKS5 代理访问。

#### 什么是 SOCKS5 代理？
SOCKS5 是一种网络代理协议，Telethon 通过它将请求转发到代理服务器，再由代理服务器访问 Telegram 的服务器。

#### 常见代理软件及端口

| 代理软件 | 默认 SOCKS5 端口 | 说明 |
|---------|-----------------|------|
| **V2RayN** | `10808`（或 `1080`） | Windows 客户端，需在设置中开启 SOCKS5 入站 |
| **Clash Verge** | `7897`（或 `7890`） | 跨平台代理客户端，设置中可查 |
| **Clash for Windows** | `7890` | 经典 Clash 客户端 |
| **Shadowsocks** | `1080` | 需配合 SSTap 或 tun2socks |
| **Hiddify** | `1080` | 需在设置中开启 "允许局域网连接" |
| **v2rayA** | `20170`（或 `1080`） | Linux/Windows 客户端 |

#### 如何找到你的代理端口？

以 **V2RayN** 为例：
1. 打开 V2RayN
2. 点击任务栏图标右键 → **参数设置**
3. 在 **Core 设置** 中查看 **本地监听端口**（SOCKS5 代理一般为 **10808**）

以 **Clash Verge** 为例：
1. 打开 Clash Verge
2. 点击左侧 **设置** → **系统代理**
3. 查看 **混合端口(Mixed Port)** 或 SOCKS5 端口

#### 填入 .env 文件

```ini
# 注意：addr 填代理软件所在机器的 IP
# 如果代理软件和脚本在同一台电脑，填 127.0.0.1
# 如果在其他机器（如路由器/服务器），填对应 IP
PROXY_HOST=127.0.0.1
PROXY_PORT=10808
```

> **验证代理是否生效**：在命令行执行 `curl --socks5 127.0.0.1:10808 https://api.telegram.org`，如果返回正常的 JSON 响应则说明代理可用。

### 第三步：配置飞书多维表格（可选）

如果使用模式二（存储到飞书），需要以下配置：

#### 1. 创建飞书应用

1. 打开 **https://open.feishu.cn/app** （飞书开放平台）
2. 点击 **创建应用** → 选择 **企业自建应用**
3. 填写应用名称和描述，创建完成后自动生成：
   - **`App ID`**（即 FEISHU_APP_ID）：应用的唯一标识
   - **`App Secret`**（即 FEISHU_APP_SECRET）：应用的密钥，仅创建时可见

#### 2. 添加应用权限

在飞书开放平台的应用配置页面：
1. 左侧 **权限管理** → 搜索并添加 **`bitable:app`** 相关权限
   - `bitable:app:readonly`（读取多维表格）
   - `bitable:app`（读写多维表格）
2. 左侧 **安全设置** → 添加 **IP 白名单**（你的服务器 IP）

#### 3. 获取 APP_TOKEN 和 TABLE_ID

1. 在飞书桌面端/网页端打开你要写入的**多维表格**
2. 从 URL 中获取：
   ```
   https://xxx.feishu.cn/base/{APP_TOKEN}?table={TABLE_ID}&view={VIEW_ID}
   ```
   - `APP_TOKEN`：base 后面的那段长字符串
   - `TABLE_ID`：table 参数的值

#### 4. 发布应用

1. 在飞书开放平台点击 **版本管理与发布** → **创建版本**
2. 填写版本号和说明，点击 **申请发布**
3. 由飞书管理员审核通过后，应用才能调用 API

#### 填入 .env

```ini
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
APP_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TABLE_ID=tblxxxxxxxxxxxxx
```

### 第四步：配置 MySQL 数据库（可选）

如果使用模式一（存储到数据库），需要准备 MySQL 环境。

#### 创建数据库

```sql
CREATE DATABASE IF NOT EXISTS telegram_channel DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

#### 创建数据表

执行项目中的建表 SQL：

```bash
mysql -h your_host -u root -p telegram_channel < quarkF_web/backend/tag_migration.sql
```

如果只想建主表，可以手动执行（示例表结构，具体根据频道内容自行实现表结构）：

```sql
CREATE TABLE IF NOT EXISTS quarkF (
    message_id BIGINT PRIMARY KEY COMMENT 'Telegram 消息 ID',
    title VARCHAR(500) COMMENT '消息标题',
    image_info TEXT COMMENT '图片信息/URL',
    publish_time DATETIME COMMENT '发布时间',
    resource_desc TEXT COMMENT '资源简介',
    link_url TEXT COMMENT '资源链接',
    tags TEXT COMMENT '标签（JSON数组）',
    original_content LONGTEXT COMMENT '原始消息内容'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 填入 .env

```ini
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password_here
DB_DB=telegram_channel
```

### 第五步：安装依赖

```bash
pip install telethon python-dotenv aiomysql PySocks requests
```

各脚本依赖说明：

| 脚本 | 必需依赖 | 可选依赖 |
|------|---------|---------|
| `quarkF_sql.py` | telethon, aiomysql, python-dotenv | PySocks（代理） |
| `quarkF_feishu.py` | telethon, requests, python-dotenv | PySocks（代理） |
| `media_channel.py` | telethon, python-dotenv | PySocks（代理） |

### 第六步：启动采集

```bash
# 模式一：存储到 MySQL
python quarkF_sql.py

# 模式二：存储到飞书
python quarkF_feishu.py

# 模式三：下载媒体到本地
python media_channel.py
```

首次启动会要求输入 Telegram 手机号和验证码，session 自动保存，后续免登录。

#### 修改目标频道

每个脚本头部都有一个 `CHANNEL_USERNAME` 变量，改为你需要的频道名即可：

```python
# quarkF、TAOSEWEIMI 都是示例，改为你自己的频道
CHANNEL_USERNAME = 'your_channel_username'   # 注意不要 @ 符号
```

---

## 数据展示系统

当使用模式一（MySQL）写入数据后，可以启动 Web 展示系统对数据进行可视化浏览。

### 启动 Web 服务

```bash
cd quarkF_web/backend
python -m uvicorn app:app --host 0.0.0.0 --port 8001
```

访问 **http://localhost:8001** 即可打开前端页面。

**功能一览**：

| 功能 | 说明 |
|------|------|
| 卡片网格 | 响应式布局，桌面 4 列 → 平板 3 列 → 手机 2/1 列 |
| 标签筛选 | 左侧面板按使用频率排序，支持多标签切换 |
| 关键词搜索 | 标题模糊匹配，300ms 防抖自动搜索 |
| 分页浏览 | 智能页码，首尾固定 + 中间省略号 |
| 图片懒加载 | IntersectionObserver 实现，提前 100px 预加载 |
| 复制链接 | 一键复制资源地址到剪贴板 |
| 删除管理 | 确认弹窗后从数据库和本地同步删除 |

### API 文档

启动后端后访问：

| 文档类型 | 地址 |
|---------|------|
| Swagger UI | http://localhost:8001/api/docs |
| ReDoc | http://localhost:8001/api/redoc |

**接口列表**：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/quarkf/list` | 分页查询（支持 tag、keyword 参数） |
| `GET` | `/api/quarkf/tags` | 获取标签列表及使用频率 |
| `GET` | `/api/quarkf/images/{id}.jpg` | 图片文件 |
| `GET` | `/api/quarkf/stats` | 数据统计 |
| `DELETE` | `/api/quarkf/{message_id}` | 删除数据 |

### 标签存储优化

主表的 `tags` 字段存储为 JSON 字符串形式（如 `["#教程","#AI"]`）。在数据量增大后，使用 `JSON_CONTAINS` 查询性能会下降。

推荐执行 `quarkF_web/backend/tag_migration.sql` 创建标签关联表：

```sql
-- 创建关联表
CREATE TABLE quarkF_tags (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    message_id BIGINT NOT NULL,
    tag_name VARCHAR(100) NOT NULL,
    INDEX idx_message_id (message_id),
    INDEX idx_tag_name (tag_name)
);

-- 迁移已有数据的标签
INSERT IGNORE INTO quarkF_tags (message_id, tag_name)
SELECT qt.message_id, jt.tag_name
FROM quarkF AS qt,
     JSON_TABLE(qt.tags, '$[*]' COLUMNS (tag_name VARCHAR(100) PATH '$')) AS jt;
```

写入脚本已实现**双写策略**（同时写入主表 `tags` 字段和关联表）。后端优先查询关联表（走索引），关联表不存在时自动降级为 `JSON_CONTAINS` 查询。

---

## 项目结构

```
telegram_code/
│
├── quarkF_sql.py                    # 模式一：结构化数据 → MySQL
├── quarkF_feishu.py                 # 模式二：结构化数据 → 飞书多维表格
├── media_channel.py                 # 模式三：媒体文件 → 本地文件夹
│
├── .env                             # 环境变量（已 gitignore，不提交）
├── .gitignore                       # Git 忽略规则
├── README.md                        # 本文件
├── DEPLOY.md                        # 部署说明文档
│
├── channel_data/                    # 媒体文件存储目录（自动生成）
│   └── {CHANNEL_USERNAME}/          # 以频道名命名的子目录
│       └── {message_id}/            # 以消息 ID 命名的文件夹
│           ├── photo/               # 图片文件
│           ├── media/               # 视频文件
│           ├── others/              # 文档等
│           └── texts/               # 消息文本
│
├── quarkF_web/                      # Web 展示模块
│   ├── backend/
│   │   ├── app.py                   # FastAPI 主应用
│   │   ├── config.py                # 配置管理
│   │   ├── requirements.txt         # Python 依赖
│   │   └── tag_migration.sql        # 标签优化 SQL
│   └── frontend/
│       └── index.html               # Vue 3 单页应用
│
└── *.session                        # Telegram 登录 session（自动生成，已 gitignore）
```

---

## 完整 .env 配置参考

```ini
# ==================== Telegram API 凭证（必填） ====================
# 从 https://my.telegram.org 获取
API_ID=12345678
API_HASH=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

# ==================== SOCKS5 代理（必填，中国大陆用户） ====================
# addr：代理软件所在机器的 IP（本机填 127.0.0.1）
# port：代理软件的 SOCKS5 监听端口
#   - V2RayN 默认 10808
#   - Clash Verge 默认 7897
#   - Clash for Windows 默认 7890
PROXY_HOST=127.0.0.1
PROXY_PORT=10808

# ==================== 飞书配置（可选，存储到飞书时需要） ====================
# 从 https://open.feishu.cn/app 创建应用获取
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# 从飞书多维表格 URL 中获取
APP_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TABLE_ID=tblxxxxxxxxxxxxx

# ==================== MySQL 数据库配置（可选，存储到数据库时需要） ====================
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=your_password
DB_DB=telegram_channel
```

---

## FAQ

### Q：首次运行提示输入手机号后没反应？

A：Telegram 的登录流程需要终端支持输入。在终端中直接输入手机号（国际格式，如 `+8613901234567`），然后输入短信验证码。如果验证码接收不到，检查代理是否正常工作。

### Q：提示 "FloodWait" 错误？

A：Telegram 对频繁请求有限制。脚本会自动等待指定时间后重试。如果频繁出现，可以减少 `limit` 参数或增大 `asyncio.sleep()` 的间隔时间。

### Q：如何更换目标频道？

A：在每个 `.py` 脚本头部找到 `CHANNEL_USERNAME` 变量，改为你需要的频道用户名（不带 `@` 符号）。

示例：`CHANNEL_USERNAME = 'doutubot'`

### Q：模式三下载的文件结构是怎样的？

A：文件按 `channel_data/{频道名}/{消息ID}/` 组织，消息 ID 用于文件夹命名。如果是相册消息（Album），所有相关消息合并到最小 ID 的文件夹中。

### Q：session 文件是做什么的？

A：`tg_channel_session.session` 文件保存了你的 Telegram 登录状态。首次登录后自动生成，后续启动脚本无需再次输入验证码。**请勿将此文件提交到 Git 仓库**（已在 .gitignore 中排除）。

### Q：代理连接失败怎么办？

A：按以下步骤排查：
1. 确认代理软件已启动并开启 SOCKS5 功能
2. 确认端口号是否正确（在代理软件设置中查找）
3. 如果脚本在其他机器上运行，确认代理监听地址为 `0.0.0.0` 且防火墙放行
4. 用 `curl --socks5 127.0.0.1:PORT https://api.telegram.org` 测试连通性

---

## 技术栈

### 数据采集
- **框架**：Telethon（Telegram MTProto 异步客户端）
- **协议**：SOCKS5 代理
- **数据库**：aiomysql（异步 MySQL 驱动）
- **API 集成**：飞书开放平台 RESTful API

### Web 展示
- **后端**：FastAPI + Uvicorn
- **前端**：Vue 3（CDN 引入，零构建）
- **缓存**：cachetools（内存缓存）
- **布局**：CSS Grid + Flexbox

---

## 许可证

本项目基于 MIT 许可证开源。详见 [LICENSE](LICENSE) 文件。

```
MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

> 如有问题或建议，请提交 [Issue](https://github.com/your-repo/issues) 。
