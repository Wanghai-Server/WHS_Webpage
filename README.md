# WHS Webpage

望海服务器（WangHai Server）官方网站。支持中英文双语切换、深色/浅色主题，并内置完整的用户系统（注册 / 登录 / 头像 / 鉴权）。

## 项目结构

```
WHS_Webpage/
├── backend/                         # 后端 — FastAPI (Python)
│   ├── main.py                      # 主程序：生命周期、全局异常处理、辅助逻辑、路由注册
│   ├── ws_server.py                 # WS 命令服务（与 MCDR 插件通信，监听 127.0.0.1:ws_port）
│   ├── api/                         # 路由注册（按类拆分）
│   │   ├── site.py                  # 站点信息（/、/api/whs）
│   │   ├── auth.py                  # 用户认证（验证码/注册/登录/me/解锁/资料）
│   │   ├── user.py                  # 用户主页/关注/简介/设置/密码/注销/管理员
│   │   ├── avatar.py                # 头像上传/读取
│   │   ├── message.py               # 系统消息/定向消息/已读/消息管理
│   │   ├── exam.py                  # 入服考试（考生端 + 管理端）
│   │   ├── server.py                # 服务器实时状态
│   │   ├── search.py                # 全量搜索（/api/search，wiki 页面 + 用户）
│   │   └── wiki.py                  # 维基（页面 CRUD/修订/搜索，按语言）
│   ├── requirements.txt             # Python 依赖
│   └── venv/                        # Python 虚拟环境（不入库）
│
├── mcdr_connecter_plugin/           # MCDR 插件（mcdr2web：连接后端 WS 服务，包结构）
│   ├── mcdreforged.plugin.json      # 插件元数据（id/version/依赖）
│   ├── mcdr2web/                    # 插件包（官方推荐结构）
│   │   └── __init__.py              # 插件入口：WS 客户端（连接/重连/双向请求响应）
│   └── requirements.txt             # 插件 Python 依赖（websockets）
│
├── data/                            # 数据层 + 运行时数据
│   ├── config.json                  # 配置：标题后缀、hCaptcha 密钥、token 密钥（不入库）
│   ├── __init__.py                  # read_config() 读取配置
│   ├── main/
│   │   └── database/
│   │       ├── basic_database.py    # 数据库抽象基类（路径规范化、连接生命周期、CRUD 接口）
│   │       ├── user_database.py     # 用户数据库（sqlite3），users 表 + 校验 + 迁移
│   │       ├── message_database.py  # 消息数据库（sqlite3），messages 表
│   │       ├── exam_database.py     # 考试数据库（sqlite3）
│   │       └── wiki_database.py     # 维基数据库（sqlite3），pages（双语）+ revisions 表
│   ├── database/                    # 运行时 SQLite 文件（basic_user_data.db，不入库）
│   ├── avatar/                      # 用户头像文件（不入库）
│   └── wiki_upload/                 # 维基媒体上传（图片/视频/音频，不入库）
│
├── whs/                             # 前端 — Vue 3 + Vite
│   ├── public/                      # 静态资源
│   ├── src/
│   │   ├── App.vue                  # 根组件（标题管理）
│   │   ├── main.js                  # 入口，挂载 router / i18n
│   │   ├── style.css                # 全局样式 & CSS 变量（主题色）
│   │   ├── assets/                  # 需构建处理的资源
│   │   ├── components/              # 可复用组件
│   │   │   ├── top_navbar.vue       # 顶部导航栏（返回按钮 / 自定义导航 / 头像）
│   │   │   ├── global_search.vue    # 顶部导航全量搜索（图标 + 建议面板）
│   │   │   ├── page_footer.vue      # 底部导航栏（语言 / 主题切换）
│   │   │   ├── login.vue            # 登录表单（账密 / 邮箱验证码）
│   │   │   ├── register.vue         # 注册表单（头像 / 邮箱 / 验证码 / 密码 / hCaptcha）
│   │   │   ├── message_box.vue      # 消息弹窗（占位）
│   │   │   └── wiki/                # 维基组件（outline / markdown / search 等）
│   │   ├── composables/             # 组合式函数
│   │   │   ├── useLanguage.js       # 语言切换（localStorage 持久化）
│   │   │   ├── useAuth.js           # 登录态 / token / 用户信息持久化
│   │   │   └── wiki/                # 维基工具 JS（api / locale / markdown 管线）
│   │   │       ├── api.js           # 维基 API 封装（语言参数 + 鉴权）
│   │   │       ├── locale.js        # 维基语言状态（lang = vue-i18n locale）
│   │   │       └── markdown.js      # markdown-it 管线（自研标题 id + 目录解析）
│   │   ├── i18n/                    # 国际化配置
│   │   ├── locales/                 # 翻译文件 zh.json / en.json
│   │   ├── pages/                   # 页面组件
│   │   │   ├── home.vue             # 首页（hero + 注册弹窗）
│   │   │   ├── about.vue            # 关于
│   │   │   ├── news_platform.vue    # 新闻列表
│   │   │   ├── news_detail.vue      # 新闻详情
│   │   │   ├── login.vue            # 登录/注册页
│   │   │   ├── user.vue             # 用户中心（占位）
│   │   │   ├── joinus.vue           # 加入我们（占位）
│   │   │   ├── search.vue           # 全量搜索页（/search，Wiki | 用户 tabs）
│   │   │   └── wiki/                # 维基页面（全部挂在 /wiki 路由下）
│   │   │       ├── index.vue        # 首页（搜索/分组/最近更新）
│   │   │       ├── layout.vue       # 公共骨架（内容区 + 页脚）
│   │   │       ├── page_view.vue    # 阅读页（Markdown 渲染 + 大纲 + 贡献者）
│   │   │       ├── page_editor.vue  # 编辑器（双栏实时预览 + 语言切换）
│   │   │       ├── page_history.vue # 修订历史（时间线 + 回滚）
│   │   │       └── search.vue       # 搜索结果页（/wiki/search?q=，全部结果列表）
│   │   └── router/                  # 路由配置
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
├── start.bat                        # Windows 一键启动
├── start.sh                         # macOS / Linux 一键启动
└── README.md
```

## 功能特性

- 🌐 **中英文双语切换** — 浏览器语言自动检测，手动选择后 localStorage 持久化。
- 🌓 **深色/浅色主题切换** — 手动切换 / 跟随系统 `prefers-color-scheme`。
- 📱 **响应式布局** — 适配桌面端与移动端（≤768px）。
- 👤 **用户系统**
  - 注册：邮箱 + 邮箱验证码 + 密码 + hCaptcha 人机验证 + 头像上传；
  - 登录：账密模式（邮箱 / UID / 用户名 + 密码）或邮箱验证码模式；
  - 密码安全：前端 SHA-256 哈希，后端加盐（`salt$hash`）存储，原始密码不出浏览器；
  - 登录态：HMAC-SHA256 签名 token（JWT 风格，无状态）；
  - 头像：上传 / 读取，登录后导航栏显示头像。
- 📨 **消息中心**（占位，待接入）。
- 📖 **维基站**（`/wiki`，自研现代化维基，不含任何开源维基代码）
  - 全部页面内容使用 **Markdown** 书写并存入 sqlite3（`wiki.db`，含 Markdown 原文）；
  - **页面目录（TOC）自动从 Markdown 标题解析**：自研 markdown-it 规则为标题生成 id 并收集 h2–h6，阅读时滚动高亮、点击定位；
  - **中英双语 + 实时切换**：固定界面文案走 vue-i18n（与全站一致）；页面内容 / 标题等无法硬编码的部分，切换语言时向后端发送对应语言的请求（`lang` 参数）实时取回；
  - 首页"知识分组"按页面路径（slug）层级自动归类；**搜索基于 SQLite FTS5 全文索引**（trigram 分词，中英文 3 字符及以上子串匹配 + BM25 标题加权排序；短查询自动回退 LIKE），按语言对标题 + 正文检索；
  - 修订历史：每次保存生成一条修订（含作者与摘要），管理员可查看任意版本并一键回滚；页面展示**历史贡献者**（谁编写过、各编辑几次）；
  - **每页独立编辑权限**：常规页面最小编辑权限为 2（player，含创建），管理员可把个别页面调整为 3（admin）或 4（owner）；页级写操作（编辑/删除/回滚）按页面自身权限校验；
  - 权限调整规则与用户管理（admin）一致：只能操作同级或更低等级的页面，且不能把页面权限设置得高于自己的权限；
  - **全站全量搜索**（`/search`）：一次请求同时检索 Wiki 页面（FTS5 标题 + 正文）与**用户**（用户名 / uid / 玩家名 / 昵称 / 小号名），结果按 Wiki | 用户分组展示（tabs）；
  - **顶部导航搜索**：导航栏"关于"右侧搜索图标，点击展开建议面板（防抖实时搜索，Wiki 页面与用户分组展示）；回车时 wiki 标题、用户 username / player_name / uid **完全相等**则直接打开对应页面，否则跳转 `/search?q=` 查看全部结果；Wiki 搜索页（`/wiki/search`）与全量搜索页（`/search`）互有入口按钮；
  - **编辑时上传媒体**：编辑器工具条可直接上传图片（png/jpg/webp/gif，≤5MB）、视频（mp4/webm/mov，≤50MB）、音频（mp3/wav/ogg/m4a/aac/flac，≤20MB），存于 `data/wiki_upload/`（已 gitignore）；插入 Markdown 后渲染时自动显示为图片 / 视频播放器 / 音频播放器；
  - **重定向**：页面改名后旧路径自动跳转到新路径（支持重定向链，拒绝循环）；管理员可手动创建 / 删除 / 查看重定向；
  - **消歧义页**：编辑器可勾选"消歧义页"，阅读时显示消歧义横幅；
  - **系统自动构建消歧义页**：扫描全部页面，发现**同语言标题相同且路径不同**的条目（≥2 个）时，由系统（uid 0）自动创建消歧义页（slug 为 `disambig/<标题slug化>`，中文标题用 sha1 前缀），列出全部同名条目链接；页面写操作与启动时自动触发（管理员也可手动 `POST /api/wiki/disambig/rebuild`）；歧义消失时自动清理失效页；**被人工编辑过的自动页系统不再接管**（词条已有消歧义页时也不重复构建）；
  - 乐观锁防冲突：保存携带 `base_rev`，他人已修改时提示"加载最新 / 强制保存"；
  - 首次启动自动播种双语欢迎页。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3（Composition API + `<script setup>`） |
| 构建工具 | Vite |
| 路由 | Vue Router |
| 国际化 | vue-i18n 9 |
| 图标 | lucide-vue-next |
| 动画 | animejs |
| 3D 模型 | skinview3d（玩家模型展示与鼠标旋转，皮肤经 mc-heads 加载） |
| 人机验证 | hCaptcha（`@hcaptcha/vue3-hcaptcha`） |
| 后端框架 | FastAPI（Python） |
| 服务器 | uvicorn |
| 表单解析 | python-multipart |
| 数据库 | SQLite（标准库 `sqlite3`，无 ORM） |

## 快速启动

### 🚀 一键启动（推荐）

| 平台 | 文件 | 说明 |
|------|------|------|
| Windows | `start.bat` | 双击运行，或在终端执行 `.\start.bat` |
| macOS / Linux | `start.sh` | `chmod +x start.sh` 后 `./start.sh` |

> 首次启动前请确保已安装 [Node.js](https://nodejs.org/) 和 [Python 3](https://www.python.org/)。

### 手动启动

#### 后端

```bash
cd backend

# 创建虚拟环境（仅首次）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动（默认 http://localhost:8000）
uvicorn main:app --reload
```

#### 前端

```bash
cd whs
npm install
npm run dev        # 开发服务器（默认 http://localhost:5173）
npm run build      # 生产构建
npm run preview    # 预览生产构建
```

## 配置说明（`data/config.json`）

```json
{
    "title_suffix": {
        "zh": " - 站点中文标题后缀",
        "en": " - Site English title suffix"
    },
    "hcaptcha": {
        "site_key": "你的 hCaptcha site key（公开）",
        "secret_key": "你的 hCaptcha secret key（私密）"
    },
    "token_secret": "登录态签名密钥（私密，随机生成）",
    "ws_port": 8765
}
```

- **`token_secret`** 用于给登录 token 签名，必须保密且随机。生成方式：
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `config.json` 已被 `.gitignore` 忽略，**部署到服务器时需要手动创建**。

### hCaptcha 注意事项

hCaptcha 的 site key 只在你配置的域名下生效。本地开发用 `localhost` 会报
`localhost detected`，需在 [hCaptcha 控制台](https://dashboard.hcaptcha.com/)
把 `localhost`（或你的自定义本地域名、生产域名）加入该 site key 的允许域名。

## API 接口（后端）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务状态 |
| GET | `/api/whs` | 站点标题后缀（双语） |
| POST | `/api/user/send_code` | 发送邮箱验证码（当前为 mock，回传 `dev_code`） |
| POST | `/api/user/register` | 注册（email + code + password + hcaptcha_response） |
| POST | `/api/user/login` | 登录（账密 / 邮箱验证码，需 hcaptcha_response） |
| GET | `/api/user/me` | 当前登录用户（需 `Authorization: Bearer <token>`） |
| POST | `/api/user/{uid}/avatar` | 上传头像（multipart，jpg/png/webp/ico，≤2MB） |
| GET | `/api/user/{uid}/avatar` | 读取头像 |
| GET | `/api/message/{user_id}` | 消息（占位） |
| GET | `/api/server/status` | 服务器实时状态（公开；后端每 5 分钟用 mcstatus 探测游戏服务器并缓存，地址在 `config.json` 的 `server` 字段配置） |
| GET | `/api/user/by_player_name/{player_name}` | 按玩家名（player_name，非 username/fullname）查 uid，301 跳转到 `/user/{uid}`（前端"成员主页跳转"用） |
| GET | `/api/user/{uid}/accounts` | 查询游戏账户（主账号 / 小号 / 各自正版标签；仅本人或管理员） |
| POST | `/api/user/{uid}/premium` | 修改主账号正版状态（premium/offline；仅本人或管理员） |
| POST | `/api/user/{uid}/alts` | 添加小号（最多两个、全局查重；仅本人或管理员） |
| DELETE | `/api/user/{uid}/alts/{alt_name}` | 注销小号（主账号不可注销；仅本人或管理员） |
| GET | `/api/wiki/pages` | 维基页面清单（双语标题、语言可用性；公开） |
| GET | `/api/wiki/search?q=&lang=` | 维基搜索（FTS5 全文索引 + LIKE 兜底；按语言对标题 + 正文匹配；公开） |
| GET | `/api/search?q=&lang=` | **全量搜索**：`{query, lang, wiki: [...], users: [...]}` —— wiki 为按语言的 FTS5 页面搜索（含摘要），users 为用户名 / uid / 玩家名 / 昵称 / 小号名匹配（各 limit 20；公开） |
| GET | `/api/wiki/page/{slug}?lang=` | 读取页面（Markdown 原文 + 修订信息 + 贡献者 + 最小编辑权限；公开） |
| POST | `/api/wiki/page` | 创建页面 `{slug, content, lang, min_permission?}`（按页面权限，默认 2；管理员可指定 2/3/4） |
| PUT | `/api/wiki/page/{slug}` | 更新页面 `{content, lang, base_rev, summary?}`（按该页最小编辑权限；409 冲突） |
| PUT | `/api/wiki/page/{slug}/permission` | 调整页面最小编辑权限 `{min_permission}`（2/3/4；仅管理员，且不能操作更高等级页面、不能设置高于自身权限） |
| DELETE | `/api/wiki/page/{slug}` | 删除页面及其修订（按该页最小编辑权限；有子页 409） |
| GET | `/api/wiki/page/{slug}/history?lang=` | 页面某语言的修订时间线（公开） |
| GET | `/api/wiki/revision/{rev_id}` | 读取单条修订快照（公开） |
| POST | `/api/wiki/revision/{rev_id}/restore` | 回滚到指定修订（按该页最小编辑权限） |
| POST | `/api/wiki/upload` | 上传媒体文件（图片/视频/音频，权限 ≥ 2；存于 data/wiki_upload/） |
| GET | `/api/wiki/upload/{filename}` | 读取已上传的媒体文件（公开，供页面渲染播放） |
| GET | `/api/wiki/redirects` | 重定向列表（仅管理员） |
| POST | `/api/wiki/redirects` | 创建重定向 `{from_slug, to_slug}`（仅管理员） |
| DELETE | `/api/wiki/redirects/{from_slug}` | 删除重定向（仅管理员） |
| POST | `/api/wiki/disambig/rebuild` | 手动触发系统消歧义页重建（仅管理员；页面写操作自动触发） |

错误响应统一为结构化 + 双语：

```json
{ "code": "username_exists", "message": { "zh": "用户名已被使用", "en": "Username already taken" } }
```

## 数据库结构（`users` 表）

| 列 | 类型 | 说明 |
|----|------|------|
| `uid` | INTEGER PRIMARY KEY AUTOINCREMENT | 自增且永不重复 |
| `email` | TEXT NOT NULL UNIQUE | 唯一邮箱 |
| `username` | TEXT NOT NULL UNIQUE | 唯一用户名（注册时由邮箱自动生成） |
| `fullname` | TEXT NOT NULL | 昵称 |
| `password` | TEXT NOT NULL | 加盐后的哈希（`盐$哈希`） |
| `avatar` | TEXT | 头像文件名（可空） |

## 数据库结构（`wiki.db`）

维基数据全部存于 `data/database/wiki.db`（sqlite3），两张表：

**`pages`（当前版本，双语）**

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | 自增 |
| `slug` | TEXT NOT NULL UNIQUE | 页面路径（小写 ASCII 段，`/` 分层，如 `guide/quick-start`） |
| `title_zh` / `title_en` | TEXT NOT NULL DEFAULT '' | 标题，保存时自动从对应语言 Markdown 第一个 H1 提取 |
| `content_zh` / `content_en` | TEXT NOT NULL DEFAULT '' | 对应语言的 Markdown 原文 |
| `min_permission` | INTEGER NOT NULL DEFAULT 2 | 该页最小编辑权限（2=player 3=admin 4=owner；管理员可调整） |
| `disambig` | INTEGER NOT NULL DEFAULT 0 | 1 = 消歧义页（阅读时显示横幅） |
| `author_uid` | INTEGER NOT NULL | 创建者 |
| `updated_by_uid` | INTEGER NOT NULL | 最后编辑者 |
| `created_at` / `updated_at` | TEXT NOT NULL | ISO 8601 时间 |

**`revisions`（历史快照，每次保存一条）**

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | 自增 |
| `page_id` | INTEGER NOT NULL | → `pages.id`（删页级联删除） |
| `lang` | TEXT NOT NULL | `zh` / `en` |
| `rev_no` | INTEGER NOT NULL | 每种语言自 1 递增 |
| `title` / `content` | TEXT NOT NULL | 该修订时的标题与 Markdown 快照 |
| `summary` | TEXT | 编辑摘要（可空） |
| `author_uid` | INTEGER NOT NULL | 谁保存的（贡献者统计来源） |
| `created_at` | TEXT NOT NULL | ISO 8601 时间 |

> 页面目录（TOC）不落库：由前端渲染时从 Markdown 标题自动解析，保证与渲染产物一致。

**`redirects`（重定向，页面改名后旧路径自动跳转）**

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | 自增 |
| `from_slug` | TEXT NOT NULL UNIQUE | 旧路径（不能是现有页面） |
| `to_slug` | TEXT NOT NULL | 目标路径（可继续指向另一重定向，解析时限制步数） |
| `created_at` | TEXT NOT NULL | ISO 8601 时间 |

## 部署说明

1. 后端：服务器上创建虚拟环境并 `pip install -r requirements.txt`。
2. 配置：在服务器 `data/` 下创建 `config.json`（含 hCaptcha secret key、随机 `token_secret`）。
3. 前端：`npm install && npm run build`，产物在 `whs/dist/`。
4. 反向代理：用 nginx / Caddy 等把 `/api/*` 转发到 FastAPI（8000），其余请求指向 `whs/dist/`；
   务必为 SPA 历史模式配置回退（如 nginx `try_files $uri /index.html`），
   否则 `/wiki/page/...`、`/wiki/edit/...` 等深链直接访问会 404。

## License

MIT License. Copyright (c) 2026 WangHai Server.
