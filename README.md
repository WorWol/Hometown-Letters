# 🏠 故乡来信 (Hometown Letters)

一封写给过去的信，生成一张像素风明信片。

"故乡来信" 是一款复古像素风格的书信应用。你写信给过去的自己，AI 会分析你的文字，搜索故乡的影像，生成一首小诗，最终绘制成一张 16-bit 像素风的明信片。你也可以将信件邮寄给其他用户，传递温情。

---

## 🎮 功能

### 核心流程
- **写信** — 写下你想对过去自己说的话，附上地点和心情
- **AI 分析** — DeepSeek 理解信件内容，提取场景、情绪、视觉主题
- **图片搜索** — 根据地点关键词搜索故乡的参考图片
- **诗歌生成** — 生成 4-8 行温暖怀旧风格的小诗、标题和正文
- **像素风明信片生成** — 火山引擎将参考图转为 SNES/GBA 风格的像素画
- **记忆系统** — 每 5 封信自动生成记忆摘要，逐步建立"过去的自己"画像

### 社交功能
- **信件邮寄** — 将信件或明信片邮寄给其他用户
- **收件箱/发件箱** — 管理收到的和发出的信件
- **用户查找** — 按用户名搜索其他用户

---

## 🛠 技术栈

| 层 | 技术 |
|---|------|
| **后端框架** | FastAPI (Python 3.12+) |
| **数据库** | SQLite + SQLAlchemy 2.0 (async) + Alembic |
| **认证** | JWT (python-jose) + bcrypt (passlib) |
| **LLM** | DeepSeek Chat API (OpenAI 兼容) |
| **图片搜索** | Serper (Google 搜索) |
| **图片生成** | 火山引擎 (Volc Ark) |
| **图片存储** | 本地文件系统 / 阿里云 OSS |
| **前端** | 原生 JS SPA（无框架）+ 像素风 CSS |
| **部署** | Docker + Docker Compose |

---

## 📁 项目结构

```
Hometown-Letters/
├── backend/
│   ├── main.py                  # FastAPI 入口，启动事件，路由注册
│   ├── config.py                # 统一配置（环境变量 / .env）
│   ├── logger.py                # 日志系统
│   ├── requirements.txt         # Python 依赖
│   ├── alembic.ini              # Alembic 配置
│   ├── api/
│   │   └── routes.py            # 所有业务 API 端点
│   ├── auth/
│   │   ├── routes.py            # 认证端点（注册/登录）
│   │   ├── security.py          # JWT + bcrypt
│   │   └── dependencies.py      # get_current_user 依赖注入
│   ├── db/
│   │   ├── database.py          # 异步引擎 + 会话
│   │   ├── models.py            # ORM 模型（11 张表）
│   │   └── migrations/          # Alembic 迁移
│   ├── services/
│   │   ├── pipeline_service.py  # 9 阶段信件处理管道
│   │   ├── letter_analysis_service.py  # LLM 信件分析
│   │   ├── llm_service.py       # DeepSeek 封装
│   │   ├── search_service.py    # Serper 图片/文字搜索
│   │   ├── image_service.py     # 火山引擎图片生成
│   │   ├── image_storage.py     # 本地/OSS 双后端存储
│   │   ├── poem_service.py      # 诗歌 + 标题 + 正文生成
│   │   ├── selection_service.py # 图片去重/筛选
│   │   └── memory_service.py    # 记忆摘要 + 人格画像
│   └── tests/
├── frontend/
│   ├── index.html               # SPA 外壳 + 认证门
│   ├── css/style.css            # 像素风样式
│   ├── assets/
│   │   ├── icons/               # 导航图标
│   │   ├── letters/             # 信纸、信封、邮票素材
│   │   ├── postcards/           # 明信片素材
│   │   ├── ui/                  # 通用界面素材
│   │   └── workbench/           # Warm Workbench 主题场景图
│   └── js/
│       ├── core/                # API、认证、应用状态与路由
│       ├── pages/               # 页面模块
│       └── ui/workbench.js      # Warm Workbench 视觉壳层
├── .env.example                 # 环境变量模板
├── Dockerfile                   # Docker 镜像
└── docker-compose.yml           # 开发环境（热重载）
```

---

## 🚀 快速开始

### 线上存储与开发者后台

生产环境使用 `STORAGE_BACKEND=oss`。用户生成图片会保存为三个 WebP object key：

```text
{OSS_OBJECT_PREFIX}/{user_id}/{postcard_id}/thumb.webp
{OSS_OBJECT_PREFIX}/{user_id}/{postcard_id}/card.webp
{OSS_OBJECT_PREFIX}/{user_id}/{postcard_id}/original.webp
```

数据库只保存 key，后端返回 OSS 短期签名 URL，浏览器直接从 OSS 加载图片。ECS 上传使用 `OSS_UPLOAD_ENDPOINT`，浏览器签名下载使用 `OSS_PUBLIC_ENDPOINT`。未配置 OSS 时使用本地 `/media`，方便开发。

每个新用户默认最多生成 5 张明信片，`DEFAULT_POSTCARD_LIMIT` 可在服务器环境配置中调整。开发者后台地址为 `/admin.html`，通过服务器 `.env` 中的 `ADMIN_TOKEN` 认证，可查看本地 SQLite 的用户、信件、明信片、磁盘和运行事件。

日志不上传 OSS，全部保存在服务器本地：结构化关键事件写入 SQLite 的 `system_events` 表，默认保留 30 天；完整运行日志写入 `backend/logs/hometown.log`，每天轮转，默认保留 7 天。Docker 部署使用 `app-data` 和 `app-logs` 卷持久化数据库与日志，应用启动时清理过期事件，并每 6 小时自动执行一次。后台还可通过认证接口 `/api/admin/logs` 查看当前文本日志末尾内容，最多返回 `ADMIN_LOG_LINES` 行。

生产启动会执行 `alembic upgrade head`。这是新数据结构，不保留旧 `image_path` 兼容字段；没有 Alembic 版本记录的旧数据库不能直接升级，部署前必须备份并按当前结构重建数据库。

### 前置条件

- Python 3.12+
- API Keys: [DeepSeek](https://platform.deepseek.com/), [Serper](https://serper.dev/), [火山引擎](https://console.volcengine.com/ark/)
- （可选）代理工具（如 Clash/V2Ray）用于访问 Serper

### 1. 配置环境

```bash
cp .env.example .env
# 编辑 .env 填入 API Key
```

必需的环境变量：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `SERPER_API_KEY` | Serper 搜索 API 密钥 |
| `VOLC_API_KEY` | 火山引擎 API 密钥 |
| `VOLC_MODEL` | 火山引擎模型 endpoint ID |
| `SECRET_KEY` | JWT 签名密钥（生产环境务必修改） |

### 2. 启动（Docker Compose，推荐）

```bash
docker compose up        # 热重载，修改代码自动生效
docker compose up -d     # 后台运行
docker compose down      # 停止
```

访问 `http://localhost:8787` 即可使用。

### 3. 本地开发

```bash
cd backend
pip install -r requirements.txt
python main.py
```

服务启动在 `http://localhost:8787`，API 文档自动生成在 `/docs`。

---

## 🔌 API 文档

所有接口使用统一的响应格式：
```json
{"ok": true, "data": { ... }}
{"ok": false, "error": "错误描述"}
```

### 认证接口（无需 Token）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 注册 → 返回 JWT |
| `POST` | `/api/auth/login` | 登录 → 返回 JWT |
| `GET` | `/api/auth/me` | 获取当前用户信息 |

### 核心接口（需要 Bearer Token）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/state` | 获取完整游戏状态（明信片、信件、记忆、画像） |
| `POST` | `/api/hometown/init` | 初始化/更新故乡信息 |
| `POST` | `/api/letter/send` | 发送一封信（走 AI 管道生成明信片） |
| `POST` | `/api/memory/save` | 保存一段记忆（含 LLM 摘要） |
| `GET` | `/api/postcards` | 获取所有明信片 |
| `DELETE` | `/api/postcards/{postcard_id}` | 删除自己的明信片及其本地/OSS 图片 |
| `GET` | `/api/community-letters?limit=5` | 查看其他用户的公开信件（写作灵感） |
图片接口不单独代理文件；`/api/state`、`/api/postcards` 等接口会返回 `imageThumbUrl`、`imageUrl` 和 `imageOriginalUrl`，前端直接加载对应的本地 `/media/...` 或 OSS 签名 URL。

当前旧数据库和本地图片的一次性迁移：

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/migrate_existing_data.py
```

上面只执行检查，不会修改数据库或上传文件。确认 OSS 配置、RAM 权限和本地图片无误后，在服务器上显式执行：

```bash
STORAGE_BACKEND=oss PYTHONPATH=. .venv/bin/python scripts/migrate_existing_data.py --execute
```

执行前会备份 SQLite；只有数据库迁移和图片上传全部成功后才替换正式数据库。AccessKey 永远不返回给前端，前端只拿短期签名 URL。用户删除自己的明信片时，后端会先删除对应的 OSS 三个对象，再删除数据库记录。

### 邮件接口（需要 Bearer Token）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/mail/send` | 向其他用户邮寄信件 |
| `GET` | `/api/mail/inbox?page=1&page_size=20` | 收件箱（含未读数统计） |
| `GET` | `/api/mail/outbox?page=1&page_size=20` | 发件箱 |
| `GET` | `/api/mail/{mail_id}` | 信件详情 |
| `PUT` | `/api/mail/{mail_id}/read` | 标记已读 |
| `DELETE` | `/api/mail/{mail_id}` | 删除信件（软删除） |
| `GET` | `/api/users/lookup?q=username` | 按用户名搜索用户 |

#### 发送邮件示例

```bash
curl -X POST http://localhost:8787/api/mail/send \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient_username": "bob",
    "title": "你好！",
    "content": "这是一封问候信。",
    "attached_postcard_id": null,
    "attached_letter_id": null
  }'
```

---

## 🧠 信件处理管道

每封发往 AI 的信件经过 7 个阶段：

```
用户写信
  → 1. 信件分析（LLM 提取地点、情绪、视觉主题）
  → 2. 图片搜索（使用分析结果的第一条关键词）
  → 3. 图片筛选（去重 + Top 5）
  → 4. 诗歌生成（LLM 生成诗 + 标题 + 正文）
  → 5. 像素画生成（火山引擎 16-bit 风格）
  → 6. 图片存储（本地 / OSS）
  → 7. 数据库持久化 + 记忆系统更新
```

核心生成链路不自动切换模型、不自动重试、不吞掉外部错误，也不使用搜索图片冒充生成结果；任一步失败都会回滚本次信件和明信片。

### 记忆系统

每 5 封信触发一次记忆聚合：
- 生成 `LetterSummary`（批量摘要）
- 提取 `LetterMemory`（情绪信号、地点信号、主题信号、人物信号、感官信号）
- 更新 `PastSelfProfile`（长期人格画像）

---

## 🗄 数据库模型

| 表 | 说明 |
|----|------|
| `users` | 用户账号 |
| `hometowns` | 故乡地理信息 |
| `letters` | 原始信件 |
| `postcards` | 生成的明信片 |
| `landmarks` | 地标库 |
| `memories` | 用户保存的记忆 |
| `letter_summaries` | 每 5 封的批量摘要 |
| `letter_memories` | 记忆信号抽取 |
| `past_self_profiles` | 长期人格画像 |
| `mails` | 用户间邮寄的信件 |
| `profiles` | 通用用户配置 |

---

## 📝 数据库迁移

```bash
cd backend

# 生成新迁移（模型变更后）
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

---

## 🎨 前端页面

| 页面 | 路由 | 文件 |
|------|------|------|
| 登录/注册 | `#login` / `#register` | [auth.js](frontend/js/pages/auth.js) |
| 桌面主页 | `#game` | [game.js](frontend/js/pages/game.js) |
| 写信 | `#page-write_letter` | [write-letter.js](frontend/js/pages/write-letter.js) |
| 明信片收藏 | `#postcards` | [postcards.js](frontend/js/pages/postcards.js) |
| 记忆 | `#memories` | [memories.js](frontend/js/pages/memories.js) |
| 设置 | `#settings` | [settings.js](frontend/js/pages/settings.js) |

---

## 🔒 安全

- JWT Token 过期时间默认 7 天（`TOKEN_EXPIRE_MINUTES`）
- 密码使用 bcrypt 哈希存储
- 所有业务接口需要 Bearer Token 认证
- 数据按 `user_id` 隔离，用户只能访问自己的数据
- 生产环境务必修改 `SECRET_KEY`

---

## 📄 License

MIT
