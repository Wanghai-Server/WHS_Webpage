# WHS Webpage

望海服务器（WangHai Server）官方网站。Vue 3 单页前端 + FastAPI 后端 + SQLite，内置完整用户系统（注册 / 登录 / 资料 / 头像 / 关注 / 消息 / 入服考试 / 反馈中心 / 管理端）与自研现代化维基，并通过本机 WebSocket 与 Minecraft 服务器的 MCDR 插件双向通信（在线名单、TPS、白名单）。

- 中英文双语切换（vue-i18n + 维基内容按语言实时请求后端）
- 深色 / 浅色主题，响应式布局
- 前端生产模式由 Vite 构建，后端只提供 `/api/*`，静态资源需单独托管（见「部署」）
- 统一启动器：根目录 `manage.py` 同时拉起前端与后端，收集两路日志并统一关停

---

## 目录

1. 架构总览
2. 功能特性
3. 技术栈
4. 项目结构
5. 快速开始
6. HTTP API（共 91 条）
7. WebSocket 协议（后端 ↔ MCDR）
8. MCDR 插件
9. 数据层（SQLite）
10. 上传与文件存储
11. 部署
12. 运维脚本与开发工具
13. 已知限制与注意事项
14. License

---

## 1. 架构总览

```
浏览器（Vue 3 SPA）
   │  静态资源：Vite dev/preview 或生产环境 nginx/Caddy 托管 whs/dist
   │  HTTP /api/* ──(dev/preview 代理 或 反向代理)──▶ FastAPI（uvicorn 127.0.0.1:7777）
   │                                                  ├─ 6 个数据库单例 → data/database/*.db（sqlite3，无 ORM）
   │                                                  ├─ 上传目录 data/{avatar,exam_image,exam_upload,wiki_upload}
   │                                                  ├─ WsCommandServer（127.0.0.1:<ws_port>，默认 8765）
   │                                                  │    ⇅ JSON：{request_id, command|success, data}
   │                                                  │  MCDR 插件 mcdr2web ──RCON──▶ Minecraft 服务器
   │                                                  └─ smtplib ──▶ 外部 SMTP（验证码 / 通知邮件）
```

要点：

- 后端单进程运行，数据库、验证码、登录失败计数、服务器状态缓存等均为**进程内状态**（见「已知限制」）。
- WS 服务只监听环回地址，仅用于**后端 ↔ MCDR 插件**通信；浏览器不参与 WebSocket，前端通过 HTTP 轮询服务器状态。
- `manage.py` 是推荐的本地启动方式；生产部署也可以直接 `uvicorn` + 独立静态托管。

---

## 2. 功能特性

### 站点与界面

- 中英文双语：界面文案走 vue-i18n（`whs/src/locales/{zh,en}.json`），首次按浏览器语言选择并持久化到 localStorage。
- 深色 / 浅色主题：CSS 变量实现，支持跟随系统偏好，选择结果持久化。
- 响应式布局，桌面 / 移动端适配。
- 顶部导航（自定义导航、全局搜索、消息盒子、头像菜单；手机端以「搜索按钮 + 用户头像」替代桌面导航）、底部页脚（语言 / 主题切换）。
- 手机端导航搜索按钮直接跳转 `/search` 全量搜索页（桌面端仍为滑入式搜索小面板）；导航栏各元素带依次淡入下滑入场动效。
- 手机端（≤768px）所有对话框统一为底部弹层：贴底、全宽、顶部 20px 圆角、高度不小于 20% 且不超过 80% 占屏高、内部滚动，并从底部滑入 / 滑出；桌面端保持居中弹窗不变。
- 非法路由（不存在的站内路径）按 `whs_config.json` 的 `301` 配置统一跳转（站内路径或外链）。

### 用户系统

- 注册：邮箱 + 邮箱验证码 + 密码（前端 SHA-256 后传输）+ 头像/昵称补充步骤。
- 登录：账密模式（邮箱 / UID / 用户名 + 密码）或邮箱验证码模式；连续输错 5 次自动锁定账号。
- 密码安全：前端先 SHA-256，后端再加随机盐存储（`salt$hash`）；原始密码不出浏览器。
- 登录态：HMAC-SHA256 自签 token（JWT 风格，无第三方依赖），`Authorization: Bearer <token>`，有效期 7 天。
- 账号状态：`banned`（封禁）/ `locked`（锁定）由统一依赖拦截，受保护接口一律 403。
- 用户主页：昵称 / 生日 / 性别 / Markdown 简介 / 头像；关注与粉丝列表；UID 复制。
- 账号设置：改资料、改头像、改邮箱（验证码）、改密码（旧密码 + 验证码）、找回密码、退出登录、注销账号。
- 密码可见性：登录 / 注册 / 找回密码 / 修改密码 / 注销账号的密码框右侧带眼睛按钮，可切换明文 / 密文；注册等多密码框表单共用一个按钮同时控制。
- 游戏账户：绑定主账号与最多 2 个小号，记录正版 / 离线标记，支持修改主账号正版状态；添加小号自动加入游戏白名单。
- 权限等级：`0=guest / 1=user / 2=player / 3=admin / 4=owner`；注册默认 1，入服考试及格自动升到 2。

### 消息中心

- 系统消息（管理员发布，Markdown）与定向消息（玩家通知）。
- 已读状态按用户记录（`read_uids`），未读数量徽标；管理员编辑消息后全员重新未读。
- 「全部已读」按钮一键清除未读（透明无边框、扫把图标；手机端仅图标）。
- 管理员可发布 / 编辑 / 删除自己发布的系统消息；用户可查看消息详情。
- 发布 / 编辑对话框支持 **编辑 / 预览** 切换（预览使用与详情相同的 Markdown 渲染，表格、代码块、颜色代码等所见即所得）。

### 入服考试

- 玩家端：阅读考前须知 → 完善游戏名 / 正版状态 → 逐题作答（答案自动保存，可上传附件）→ 交卷；最多 2 次机会，60% 及格。
- 题型：单选、多选（部分分）、填空（按空给分）、主观题（人工改分）。
- 及格副作用：写入玩家名、权限 < 2 时提升到 player、标记通过、自动加入游戏白名单。
- 未通过可重新作答，也可提交人工重审（通知全部管理员，站内消息 + 邮件）。
- 管理端：查看考生列表、试卷在线编辑（覆盖 `data/exam.yml` 即时生效）、查看/改分答题卡、删除答卷、上传题目附图与说明文档（.docx）。

### 维基（自研，不依赖开源维基程序）

- 页面内容为 Markdown，存于 SQLite（`wiki.db`），中英双语各存一份；标题从正文首个 H1 自动提取。
- 目录（TOC）由前端渲染时从 Markdown 标题（h1–h6）自动生成，滚动高亮、点击定位、阅读进度。
- 搜索：SQLite FTS5 全文索引（`trigram` 分词，中文/英文 3 字符及以上子串匹配，BM25 标题加权），短查询自动回退 LIKE。
- 每页独立的**最小编辑权限**（2/3/4）：普通玩家默认 2，管理员可调高；页面级写操作按页面自身权限校验。
- 修订历史：每次保存生成一条修订（作者 + 摘要 + 时间），每页每语言保留最近 100 条；管理员可查看任意版本并回滚；页面展示历史贡献者与编辑次数。
- 乐观锁：保存携带 `base_rev`，他人已修改时返回 409，前端提示「加载最新 / 强制保存」。
- 重定向：页面改名后旧路径自动跳转（支持重定向链，最多 8 步，拒绝循环）；管理员可增删查。
- 消歧义页：编辑器可标记「消歧义页」；系统也会在启动与页面写操作时自动构建/清理自动消歧义页（被人工编辑过的自动页不再接管）。
- 媒体上传：图片（≤5MB）/ 视频（≤50MB）/ 音频（≤20MB），插入 Markdown 后渲染为图片、`<video>`、`<audio>` 播放器。
- 颜色 / 格式代码：支持 MC 风格的 `§` 代码（全站 Markdown 通用，包括维基、反馈、消息、考试提示与用户简介）——`§0`–`§f` 为 MC 官方 16 色，`§#RRGGBB` 支持任意 HEX；`§l` 粗体、`§o` 斜体、`§n` 下划线、`§m` 删除线、`§r` 复位。代码块与行内代码内不解析；编辑器工具栏提供颜色下拉（选中文字上色并自动加 `§r`，光标处插入则按 MC 规则持续生效）；页面标题 / 搜索与列表摘要会自动剥离 `§` 代码。注意：颜色代码会重置格式，需要「颜色 + 粗体」时先写颜色再写格式（如 `§e§l文字`）。
- 编辑器：双栏实时预览、语言切换、附件上传、拖拽分栏、未保存离开确认。

### 全站搜索

- 顶部导航搜索（桌面端）：滑入式小面板，防抖实时建议，Wiki 页面与用户分组展示；标题 / 用户名 / 玩家名 / UID 完全相等时直接打开对应页面。手机端导航搜索按钮直接进入 `/search`。
- `/search` 全量搜索页：一次请求同时检索 Wiki（FTS5 + 摘要）、用户（用户名 / uid / 玩家名 / 昵称 / 小号名）与反馈（标题 / 正文 + 命中摘要）；结果按「Wiki / 用户 / 反馈」标签页分组展示。

### 反馈中心

- 公开浏览：`/feedback` 列表（分页、状态筛选、关键词搜索）与 `/feedback/:id` 详情页；列表/详情无需登录。
- 提交与评论需登录：标题 + 分类（问题 / 建议 / 其他）+ Markdown 正文，支持编辑预览；详情页评论区支持 Markdown，登录用户可跟帖。
- 状态流转：`pending`（待处理）/ `resolved`（已处理）/ `closed`（已关闭）；管理员可在详情页或管理端修改状态。
- 权限：作者可编辑 / 删除自己的反馈；管理员（permission ≥ 3）可删除任意反馈、修改状态。
- 管理端：用户页「管理员」→「反馈管理」，列表支持状态筛选、分页、查看、改状态、删除（带确认框）。
- 入口：底部页脚「快速链接 → 反馈」；顶部导航不放入口。
- 存储：`feedback` + `feedback_comments` 两张 SQLite 表（`data/database/feedback.db`）。

### 服务器状态

- 在线人数 / TPS / MSPT / 玩家上限全部来自 MCDR 插件上报（在线名单 + RCON `tick query` / `list`），后端缓存 5 分钟。
- `bot_` 前缀视为假人，不计入官网在线人数；WS 不可用时回退上一次缓存或离线占位。
- 白名单列表接口已提供（前端预留成员墙用途）。

---

## 3. 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3（Composition API + `<script setup>`） |
| 构建 / 开发服务器 | Vite 8（`/api` 在 dev 与 preview 下均代理到 `127.0.0.1:7777`） |
| 路由 | Vue Router 5（history 模式，页面全部懒加载） |
| 国际化 | vue-i18n 9 |
| 图标 / 动画 / 3D | lucide-vue-next / animejs / skinview3d |
| Markdown | markdown-it（自研标题 id、目录、媒体渲染规则） |
| DOCX 渲染 | mammoth（考试说明文档） |
| 人机验证 | hCaptcha（`@hcaptcha/vue3-hcaptcha`） |
| 后端框架 | FastAPI + uvicorn |
| 表单 / 上传 | python-multipart |
| 数据库 | SQLite（标准库 `sqlite3`，手写 SQL，无 ORM） |
| 实时能力 | `websockets`（后端 WS 服务 + MCDR 插件客户端） |
| 试卷配置 | PyYAML（`data/exam.yml`） |
| 邮件 | 标准库 `smtplib`（外部 SMTP） |
| MCDR 插件 | mcdreforged ≥ 2.15、whitelist_api ≥ 2.0、online_player_api ≥ 1.0 |

> Python 版本要求 **≥ 3.12**（后端代码使用了 PEP 701 的嵌套 f-string 语法），`backend/requirements.txt` 未固定 Python 版本。

---

## 4. 项目结构

```
WHS_Webpage/
├── manage.py                        # 统一启动管理器（前端 dev/prod + 后端 + 日志收集 + 统一关停）
├── README.md
├── LICENSE
├── express_set_perm.py              # 运维脚本：离线修改用户权限（直接写 SQLite，慎用）
├── unlock_user.py                   # 运维脚本：离线解锁账号（尚未纳入版本库）
│
├── backend/                         # 后端（FastAPI）
│   ├── main.py                      # 组合根：数据库实例、token/密码/hCaptcha/SMTP、考试判分、
│   │                                #   错误码表、全局异常处理、lifespan、路由注册
│   ├── ws_server.py                 # 与 MCDR 插件通信的 WS 命令服务（127.0.0.1:<ws_port>）
│   ├── requirements.txt
│   ├── api/                         # 路由层（按业务拆分，共 91 条路由）
│   │   ├── __init__.py
│   │   ├── site.py                  # 服务状态 / 站点公开配置
│   │   ├── auth.py                  # 验证码 / 注册 / 登录 / 账号信息 / 解锁
│   │   ├── user.py                  # 用户主页 / 关注 / 资料 / 邮箱 / 密码 / 注销 / 封禁 / 权限 / 游戏账户
│   │   ├── avatar.py                # 头像上传与读取
│   │   ├── message.py               # 系统消息 / 定向消息 / 已读 / 消息管理
│   │   ├── exam.py                  # 入服考试（考生端 + 管理端）
│   │   ├── feedback.py              # 反馈中心（列表 / 详情 / 提交 / 编辑 / 删除 / 评论 / 状态）
│   │   ├── server.py                # 服务器实时状态
│   │   ├── search.py                # 全站搜索（Wiki + 用户 + 反馈）
│   │   └── wiki.py                  # 维基（页面 / 修订 / 重定向 / 消歧义 / 媒体）
│   └── venv/                        # Python 虚拟环境（不入库）
│
├── data/                            # 配置 + 数据层 + 运行时数据
│   ├── __init__.py                  # 配置读取 / 默认值（read_config、read_whs_config）
│   ├── config.json                  # 私密配置（不入库，缺失时自动生成默认值）
│   ├── whs_config.json              # 公开配置（不入库，缺失时自动生成默认值）
│   ├── exam.py                      # 试卷 YAML 的加载 / 校验 / 写入
│   ├── exam.yml                     # 当前试卷（不入库，管理端在线编辑即覆盖本文件）
│   ├── main/
│   │   └── database/
│   │       ├── basic_database.py    # 数据库抽象基类（路径规范化、连接生命周期、线程安全包装）
│   │       ├── user_database.py     # users / user_info 表 + 迁移 + 游戏账户
│   │       ├── message_database.py  # messages 表
│   │       ├── exam_database.py     # exam_answers / exam_profiles 表
│   │       ├── wiki_database.py     # pages / revisions / redirects / FTS5 + 消歧义构建
│   │       └── feedback_database.py # feedback / feedback_comments 表 + 分页/搜索
│   ├── database/                    # SQLite 运行时文件（不入库）
│   │   ├── basic_user_data.db
│   │   ├── basic_message_data.db
│   │   ├── exam_data.db
│   │   ├── wiki.db
│   │   └── feedback.db
│   ├── avatar/                      # 头像文件（不入库）
│   ├── exam_image/                  # 试卷附图 / 说明文档（不入库）
│   ├── exam_upload/                 # 答题附件（不入库）
│   └── wiki_upload/                 # 维基媒体文件（不入库）
│
├── whs/                             # 前端（Vue 3 + Vite）
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js               # dev / preview 均代理 /api → 127.0.0.1:7777
│   ├── public/                      # 静态资源（icons 等）
│   ├── dist/                        # 生产构建产物（不入库）
│   └── src/
│       ├── main.js                  # 入口：挂载 router / i18n
│       ├── App.vue                  # 根组件（全局 Tips / DialogBox、标题、用户态刷新、快捷键）
│       ├── style.css                # 全局样式与主题 CSS 变量
│       ├── router/index.js          # 路由表 + 非法路径 301 跳转
│       ├── i18n/index.js
│       ├── locales/{zh,en}.json     # 翻译文件
│       ├── assets/                  # 需构建处理的资源
│       ├── composables/             # 组合式函数
│       │   ├── useAuth.js           # 登录态（模块级单例 + localStorage）
│       │   ├── useLanguage.js       # 语言切换与持久化
│       │   ├── useSiteConfig.js     # /api/whs 站点公开配置
│       │   ├── useTips.js           # 全局轻提示
│       │   ├── useDialogBox.js      # 全局确认 / 提示对话框
│       │   ├── useHcaptchaSiteKey.js# hCaptcha site key
│       │   ├── sha256.js            # 前端密码哈希
│       │   ├── clipboard.js
│       │   └── wiki/{api,locale,markdown}.js  # 维基 API 封装 / 语言状态 / Markdown 管线
│       ├── components/              # 35 个可复用组件
│       │   ├── 导航与公共：top_navbar / page_footer / global_search / user_dropdown / tabs / tips / dialog_box / status_dropdown
│       │   ├── 账号：login / register / forgot_password / full_user_info / username_suggestion / change_password / cancel_account / user_settings / manage_accounts / user_profile / basic_user_info / follow_list / player_info
│       │   ├── 消息：message_box / message_detail
│       │   ├── 反馈：feedback_editor
│       │   ├── 考试：exam_question / exam_editor / doc_viewer
│       │   ├── 维基：wiki_markdown / wiki_outline / wiki_outline_node / wiki_search / wiki_page_404
│       │   └── 管理：admin_settings / admin_user_panel / joinus_tips
│       └── pages/                   # 16 个页面
│           ├── home.vue / about.vue / login.vue / user.vue / search.vue / joinus.vue / exam.vue
│           ├── forum/index.vue      # 论坛（静态占位）
│           ├── feedback/            # 反馈中心：index（列表） / detail（详情）
│           └── wiki/                # index / layout / page_view / page_editor / page_history / search
│
├── mcdr_connecter_plugin/           # MCDR 插件（mcdr2web）
│   ├── mcdreforged.plugin.json      # 插件元数据
│   ├── mcdr2web/__init__.py         # WS 客户端：连接 / 重连 / 双向请求、RCON 采集、命令注册
│   ├── requirements.txt             # websockets
│   ├── whitelist_api/               # 依赖插件（本地目录，未入库）
│   └── online_player_api/           # 依赖插件（本地目录，未入库）
│
├── pseudo_mcdr/                     # WS 客户端测试替身（未入库，见「开发工具」）
├── SMTP/                            # 本地收信调试服务（未入库，见「开发工具」）
└── logs/                            # manage.py 运行日志（运行时生成，不入库）
```

---

## 5. 快速开始

### 5.1 环境要求

- **Python ≥ 3.12**（后端）
- **Node.js + npm**（前端构建 / 开发服务器）
- 可选：Minecraft 服务器 + [MCDR](https://mcdreforged.com/)（服务器状态、在线名单、白名单联动需要）

### 5.2 配置

首次启动时若缺少配置文件会自动生成默认值；**默认值不含真实密钥 / 邮件服务器信息，部署前必须手工填写**。两个配置文件均被 `.gitignore` 忽略，部署到新机器时需要重新创建。

**`data/config.json`（私密）**

| 字段 | 说明 |
|------|------|
| `hcaptcha.secret_key` | hCaptcha 服务端校验密钥（仅发送验证码时使用） |
| `smtp.username` / `smtp.password` | 发信账号与授权码 |
| `token_secret` | 登录 token 的 HMAC 签名密钥，必须随机且保密（生成：`python -c "import secrets; print(secrets.token_hex(32))"`） |
| `server.host` / `server.port` | 游戏服务器地址，目前用于 `/api/exam/get_ip` 返回给及格考生 |
| `server.timeout` | 保留字段，当前代码未读取 |
| `ws_port` | 后端与 MCDR 插件通信的 WS 端口（默认 8765，仅监听环回） |

**`data/whs_config.json`（公开）**

| 字段 | 说明 |
|------|------|
| `title_suffix.zh` / `title_suffix.en` | 站点标题后缀（首页使用） |
| `hcaptcha.site_key` | hCaptcha 前端公钥 |
| `smtp.host` / `smtp.port` / `smtp.sender` / `smtp.sender_name` / `smtp.use_ssl` | 发信服务器参数（与 `config.json` 的账号密码组合使用） |
| `301` | 无效站内链接统一跳转目标：`http(s)://` 开头视为外链整页跳转，否则视为站内路径；为空则回 `/` |

**hCaptcha 注意事项**：site key 只在控制台登记的域名下生效。本地开发用 `localhost` 时需要在 [hCaptcha 控制台](https://dashboard.hcaptcha.com/) 把 `localhost` 加入允许域名，否则会提示 `localhost detected`。

**试卷**：`data/exam.yml` 由管理端在线编辑（`PUT /api/admin/exam/config` 会校验后覆盖写入），也可手工编辑，重启无需重启服务（每次读取即时生效）。

### 5.3 一键启动（推荐）

根目录的 `manage.py` 会同时拉起前端与后端两个子进程，把两路日志实时输出到终端，并统一关停：

```bash
python manage.py            # 交互选择前端环境（1=开发，2=生产，回车默认开发）
python manage.py --dev      # 开发：npm run dev（后端 uvicorn --reload，带热重载）
python manage.py --prod     # 生产：先 npm run build，成功后 npm run preview（后端不带 --reload）
```

启动后：

- 后端：<http://127.0.0.1:7777>（API；`GET /` 返回 JSON 服务状态）
- 前端：<http://localhost:5173>（开发服务器 / dist 预览服务，`/api` 自动代理到后端）
- MCDR WS：`127.0.0.1:8765`（仅本机，插件用）

停止方式：

- 在终端输入 `stop` / `quit` / `exit` 回车；
- 或按 `Ctrl+C`（`Ctrl+Break` 亦可）。

脚本会**先终止前端、再终止后端**，随后退出，不会留下 node / python 孤儿进程。

日志：

- 终端：`[HH:MM:SS.mmm] [backend|frontend|frontend:build|manager] 内容`
- 文件：每次启动新建 `logs/YYYYMMDD-HHMMSS.log`，行首为完整时间戳（`[YYYY-MM-DD HH:MM:SS.mmm]`）

行为约定：

- 生产模式构建失败时不会启动后端；任一子进程意外退出时，其余服务一并停止。
- 首次使用需先在 `whs/` 执行 `npm install`、在 `backend/` 创建 venv 并安装依赖（否则脚本会给出明确提示）。

### 5.4 手动启动

**后端**

```bash
cd backend
python -m venv venv            # 仅首次
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 7777 --reload
```

**前端**

```bash
cd whs
npm install                    # 仅首次
npm run dev                    # 开发服务器（默认 5173）
npm run build                  # 生产构建，产物在 whs/dist/
npm run preview                # 预览生产构建（--host 0.0.0.0 --port 5173）
```

### 5.5 接入 MCDR（可选）

服务器状态、在线名单、白名单联动依赖 MCDR 插件：

1. 将 `mcdr_connecter_plugin/` 下的 `mcdr2web` 与两个依赖插件 `whitelist_api`、`online_player_api` 放入 MCDR 的 `plugins/` 目录（后两者不在版本库中，需从开发机 / 上游获取）。
2. 安装依赖：`pip install websockets`（插件自身的 `requirements.txt`）。
3. 首次加载会生成 `config/mcdr2web.json`（位于 MCDR 工作目录），默认：

   ```json
   { "ws_host": "127.0.0.1", "ws_port": 8765, "tps_report_interval": 300 }
   ```

   `ws_port` 必须与 `data/config.json` 的 `ws_port` 一致。
4. 插件启动后自动连接后端 WS，并每 5 分钟上报 TPS / MSPT / 玩家上限；RCON 未开启时 TPS 与上限为空（`/api/server/status` 中为 `null` / 0）。
5. 白名单操作：正版模式执行服务器 `whitelist add/remove` 命令；离线模式直接改 `whitelist.json`（离线 UUID）后 `whitelist reload`。

---

## 6. HTTP API（共 91 条）

### 6.1 约定

- 前缀：全部接口挂在 `/api/*`（另有 `GET /` 返回服务状态 JSON）。
- 鉴权：需要登录的接口带 `Authorization: Bearer <token>`；表中「鉴权」列含义：
  - **公开**：无需 token；**可选**：有 token 则识别身份，无 token 也返回；
  - **登录**：必须有效 token；**本人/≥3**：仅本人或 permission≥3；**≥3**：admin/owner；
  - **页权限**：需 permission ≥ 该页 `min_permission`（2/3/4）。
- 权限等级：`0=guest / 1=user / 2=player / 3=admin / 4=owner`。
- 错误响应统一为结构化 + 双语：

  ```json
  { "code": "username_exists", "message": { "zh": "用户名已被使用", "en": "Username already taken" } }
  ```

  常见 HTTP 状态：400 参数错误 / 401 未登录 / 403 权限不足（含 `account_banned`、`account_locked`）/ 404 不存在 / 409 冲突 / 413 文件过大 / 429 频率限制 / 502 邮件发送失败。
- 全局兜底同样使用上述结构：参数校验失败（422）→ `invalid_parameter`；框架层 404 / 405 → `not_found` / `method_not_allowed`（其他 HTTP 异常 → `http_error`）；未捕获异常（500）→ `internal_error`。
- 分页接口参数：`page`、`page_size`（≤100）；缺省为 1 / 10，0 或负数按 1 处理；`GET /api/feedback` 的 `page_size` 上限为 50。

### 6.2 站点（2 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/` | 公开 | 服务状态 `{message, status}` |
| GET | `/api/whs` | 公开 | 站点公开配置：`title_suffix`、`hcaptcha_site_key`、`301` |

### 6.3 认证（9 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/user/send_code` | 公开（需 hCaptcha） | 发送邮箱验证码；同邮箱 60s 冷却，验证码 5 分钟有效 |
| GET | `/api/user/username_exists` | 公开 | 用户名是否已占用 |
| GET | `/api/user/player_name_exists` | 公开 | 玩家名是否已占用（含小号） |
| POST | `/api/user/suggest_username` | 公开 | 基于 base 推荐一个未占用用户名 |
| POST | `/api/user/register` | 公开（邮箱验证码） | 注册；成功返回 `{uid, token}` |
| POST | `/api/user/login` | 公开 | 登录（账密 / 邮箱验证码两种模式） |
| GET | `/api/user/me` | 登录 | 当前登录用户信息 |
| POST | `/api/user/{uid}/unlock` | ≥3 且权限严格高于目标 | 解锁账号并清空失败计数 |
| POST | `/api/user/{uid}/info` | 本人/≥3 | 保存昵称、性别、生日 |

### 6.4 用户（20 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/user/by_player_name/{player_name}` | 公开 | 按玩家名查 uid，301 跳转 `/user/{uid}` |
| GET | `/api/user/{uid}` | 可选 | 用户主页数据（本人/管理员可见邮箱、权限、封禁状态等） |
| POST | `/api/user/{uid}/follow` | 登录 | 关注用户 |
| POST | `/api/user/{uid}/unfollow` | 登录 | 取消关注 |
| POST | `/api/user/{uid}/profile` | 本人/≥3 | 保存 Markdown 简介（上限 20000 字符） |
| POST | `/api/user/{uid}/email` | 本人/≥3 | 修改邮箱（需新邮箱验证码） |
| POST | `/api/user/password_reset_verify` | 公开 | 找回密码第一步：校验邮箱验证码 |
| POST | `/api/user/password_reset` | 公开 | 找回密码第二步：设置新密码 |
| POST | `/api/user/{uid}/password_verify` | 本人/≥3 | 修改密码第一步：校验验证码 + 旧密码 |
| POST | `/api/user/{uid}/password` | 本人/≥3 | 修改密码 |
| POST | `/api/user/{uid}/cancel` | 仅本人 | 注销账号（验证码 + 旧密码；删除头像与账号数据） |
| POST | `/api/user/{uid}/ban` | ≥3 且权限严格高于目标 | 封禁 / 解封；封禁时移出全部游戏白名单 |
| POST | `/api/user/{uid}/permission` | ≥3 且不低于目标、新值≤自己 | 修改用户权限（0–4） |
| GET | `/api/admin/users` | ≥3 | 用户列表（分页；`q` 搜索用户名 / 昵称 / 邮箱 / UID） |
| GET | `/api/user/{uid}/followers` | 公开 | 粉丝列表 |
| GET | `/api/user/{uid}/followings` | 公开 | 关注列表 |
| GET | `/api/user/{uid}/accounts` | 本人/≥3 | 游戏账户（主账号 / 小号 / 正版标记） |
| POST | `/api/user/{uid}/premium` | 本人/≥3 | 修改主账号正版状态（`premium` / `offline`） |
| POST | `/api/user/{uid}/alts` | 本人/≥3 | 添加小号（最多 2 个、全局查重、自动加入白名单） |
| DELETE | `/api/user/{uid}/alts/{alt_name}` | 本人/≥3 | 注销小号（自动移出白名单，主账号不可注销） |

### 6.5 头像（2 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/user/{uid}/avatar` | 本人/≥3 | 上传头像（multipart，jpg/png/webp/ico，≤2MB） |
| GET | `/api/user/{uid}/avatar` | 公开 | 读取头像文件 |

### 6.6 消息（8 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/message/system` | 可选 | 系统消息列表（未登录时 `is_read` 为 null） |
| GET | `/api/message/unread_count` | 登录 | 未读消息数量（系统 + 定向） |
| POST | `/api/message/{message_id}/read` | 登录 | 标记消息已读（幂等） |
| POST | `/api/message/read_all` | 登录 | 把本人全部消息（系统 + 定向）标为已读（幂等，用于「全部已读」） |
| POST | `/api/admin/messages` | ≥3 | 发布系统消息 `{title, content}` |
| PUT | `/api/admin/messages/{message_id}` | ≥3 且作者本人 | 编辑系统消息（全员重新未读） |
| DELETE | `/api/admin/messages/{message_id}` | ≥3 且作者本人 | 删除系统消息 |
| GET | `/api/message/{user_id}` | 登录且本人/≥3 | 定向消息列表 |

### 6.7 入服考试（23 条）

**考生端**

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/exam` | 登录 | 试卷（题面，不含标准答案） |
| GET | `/api/exam/progress` | 登录 | 答题进度（已存答案 / 附件 / 得分） |
| POST | `/api/exam/answer` | 登录 | 提交单题答案（即时判分；可重复提交覆盖） |
| POST | `/api/exam/upload` | 登录 | 上传答题附件（仅允许上传的题；jpg/png/webp/gif，≤20MB） |
| GET | `/api/exam/attachment/{filename}` | 登录且本人/≥3 | 读取答题附件 |
| DELETE | `/api/exam/attachment/{filename}` | 登录且本人/≥3 | 删除答题附件 |
| GET | `/api/exam/profile` | 登录 | 考试档案（玩家名 / 正版状态 / 次数 / 是否通过） |
| POST | `/api/exam/profile` | 登录 | 保存玩家名与正版状态（玩家名全局查重） |
| POST | `/api/exam/reset` | 登录（可作答时） | 清空本人答题记录（不消耗次数） |
| POST | `/api/exam/finish` | 登录（可作答时） | 交卷：汇总分数、次数 +1、及格处理 |
| POST | `/api/exam/review` | 登录 | 申请人工重审（通知全部管理员，站内消息 + 邮件） |
| GET | `/api/exam/get_ip` | 登录且已通过 | 返回游戏服务器地址 `{ip: "host:port"}`，未通过 403 |
| POST | `/api/exam/submit` | 登录 | 只读汇总当前分数（保留接口，前端未使用） |

**试卷资源**

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/admin/exam/image` | ≥3 | 上传题目 / 选项附图（jpg/png/webp/gif，≤5MB） |
| GET | `/api/exam/image/{filename}` | 公开 | 读取试卷附图 |
| POST | `/api/admin/exam/doc` | ≥3 | 上传试卷说明文档（仅 .docx，≤10MB） |
| GET | `/api/exam/doc/{filename}` | 公开 | 读取试卷说明文档 |

**管理端**

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/admin/exam/candidates` | ≥3 | 考生列表（分页，含次数 / 是否通过 / 已答题数；`q` 搜索用户名 / 玩家名 / UID） |
| GET | `/api/admin/exam/config` | ≥3 | 读取完整试卷配置（含标准答案） |
| PUT | `/api/admin/exam/config` | ≥3 | 保存试卷（校验后覆盖写入 `data/exam.yml`，即时生效） |
| GET | `/api/admin/exam/answers/{uid}` | ≥3 | 查看某考生答题卡（含题目、答案、得分） |
| POST | `/api/admin/exam/score` | ≥3 | 修改某题得分（0 ~ 题满分；达标未通过时触发及格处理） |
| DELETE | `/api/admin/exam/answers/{uid}` | ≥3 | 删除某考生答卷（重置答题与通过状态） |

### 6.8 服务器（3 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/server/status` | 公开 | 实时状态（在线人数 / TPS / MSPT / 上限；缓存 5 分钟，数据来自 MCDR 插件） |
| GET | `/api/server/is_online` | 公开 | 指定玩家是否在线（前端暂未使用） |
| GET | `/api/server/whitelist` | 公开 | 白名单玩家列表（前端预留成员墙） |

### 6.9 搜索（1 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/search` | 公开 | 全站搜索 `?q=&lang=`：`{wiki: [...], users: [...], feedback: [...]}`（各 20 条） |

### 6.10 反馈（7 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/feedback` | 公开 | 反馈列表 `?page=&page_size=&status=&category=&q=`；返回 `{total, page, page_size, items}`，每项含作者名、摘要、评论数 |
| GET | `/api/feedback/{feedback_id}` | 可选 | 反馈详情：`{feedback, comments, viewer}`；`viewer` 含 `logged_in / can_edit / can_delete / can_moderate` |
| POST | `/api/feedback` | 登录 | 提交反馈 `{title, content, category}`；`category` ∈ `bug / suggestion / other`，状态默认 `pending` |
| PUT | `/api/feedback/{feedback_id}` | 仅作者 | 编辑反馈 `{title, content, category}` |
| DELETE | `/api/feedback/{feedback_id}` | 作者或 ≥3 | 删除反馈（应用层级联删除评论） |
| POST | `/api/feedback/{feedback_id}/comments` | 登录 | 发表评论 `{content}`（Markdown） |
| PUT | `/api/admin/feedback/{feedback_id}/status` | ≥3 | 修改状态 `{status}`；`status` ∈ `pending / resolved / closed` |

错误码：写接口字段类型不合法 → 400 `feedback_invalid_field`；`page` 超出范围 → 400 `feedback_page_invalid`；非法分类 / 状态 → 400 `feedback_category_invalid` / `feedback_status_invalid`。

### 6.11 维基（16 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/wiki/pages` | 公开 | 页面清单（双语标题、语言可用性、页权限、作者） |
| GET | `/api/wiki/search` | 公开 | 按语言搜索（FTS5 + LIKE 兜底，返回摘要） |
| GET | `/api/wiki/page/{slug}/history` | 公开 | 页面某语言的修订时间线 |
| GET | `/api/wiki/revision/{rev_id}` | 公开 | 读取单条修订快照（标题 + Markdown 正文） |
| POST | `/api/wiki/revision/{rev_id}/restore` | 登录 + 页权限 | 回滚到指定修订（生成新修订） |
| PUT | `/api/wiki/page/{slug}/permission` | ≥3 且 permission≥页权限 | 调整页面最小编辑权限（2/3/4） |
| GET | `/api/wiki/page/{slug}` | 公开 | 读取页面（无此页时返回重定向目标 `{page: null, redirect}` 或 404） |
| POST | `/api/wiki/page` | 登录 + 页权限 | 创建页面 `{slug, content, lang, min_permission?, disambig?}` |
| PUT | `/api/wiki/page/{slug}` | 登录 + 页权限 | 更新页面 `{content, lang, base_rev, summary?, disambig?}`；冲突 409 |
| DELETE | `/api/wiki/page/{slug}` | 登录 + 页权限 | 删除页面及全部修订（存在子页时 409） |
| GET | `/api/wiki/redirects` | ≥3 | 重定向列表 |
| POST | `/api/wiki/redirects` | ≥3 | 创建 / 覆盖重定向 `{from_slug, to_slug}` |
| DELETE | `/api/wiki/redirects/{from_slug}` | ≥3 | 删除重定向 |
| POST | `/api/wiki/disambig/rebuild` | ≥3 | 手动触发系统消歧义页重建 |
| POST | `/api/wiki/upload` | 登录且 permission≥2 | 上传媒体（图片≤5MB / 视频≤50MB / 音频≤20MB） |
| GET | `/api/wiki/upload/{filename}` | 公开 | 读取已上传媒体文件 |

---

## 7. WebSocket 协议（后端 ↔ MCDR）

后端在 FastAPI 生命周期内启动一个独立 WS 命令服务，只监听 `127.0.0.1:<data/config.json 的 ws_port>`（默认 8765），**无鉴权、无 TLS**，安全边界仅「只监听环回地址」。

统一消息格式（JSON）：

```jsonc
// 请求（任一方发送）
{ "request_id": "<uuid hex>", "command": "<指令名>", "data": <任意> }
// 响应（对方回复）
{ "request_id": "<同上>", "success": true|false, "data": <任意> }
```

- 区分请求 / 响应：顶层**有 `success` 键**即为响应，否则按请求处理（没有 `type` 字段）。
- 无客户端连接时后端发请求立即失败；默认超时 10s（后端业务调用：读 3s、写 10s）。
- 服务端主动请求会**广播给所有已连接客户端**，首个响应胜出；白名单增删按「已存在 / 不存在」做幂等处理。

指令全集：

| 方向 | command | 说明 |
|------|---------|------|
| MCDR → 后端 | `ping` | 连通性检查，返回 `"pong"` |
| MCDR → 后端 | `report_tps` | 周期上报 `{tps, mspt, healthy, max?}`（默认 300s 一次，RCON `tick query` + `list`） |
| 后端 → MCDR | `ping` | 同上 |
| 后端 → MCDR | `get_player_list` | 在线玩家名单（`bot_` 前缀视为假人，不计入官网在线人数） |
| 后端 → MCDR | `is_online` | `{player}` → 是否在线（大小写不敏感；前端暂未使用） |
| 后端 → MCDR | `get_whitelist` | 白名单玩家名单 |
| 后端 → MCDR | `add_player` | `{player}` → 加入白名单（幂等） |
| 后端 → MCDR | `remove_player` | `{player}` → 移出白名单（幂等） |

断线重连由 MCDR 插件负责（固定 5s 重试）；后端 WS 未连接时，`/api/server/status` 回退上次缓存或离线占位，白名单相关操作失败只记日志、不阻断主流程。

---

## 8. MCDR 插件

目录 `mcdr_connecter_plugin/`：

- 元数据（`mcdreforged.plugin.json` 与代码内 `PLUGIN_METADATA` 一致）：`id=mcdr2web`、`version=0.1.0`、`name=MCDR to Web`。
- 依赖：`mcdreforged>=2.15.0`、`whitelist_api>=2.0.0`、`online_player_api>=1.0.0`；插件自身依赖 `websockets`。
- 事件：仅 `on_load` / `on_unload`（在线玩家与服务器事件由 `online_player_api` 负责维护）。
- 命令：`!!mcdr2web ping`（测试后端 WS 连通）、`!!mcdr2web status`（显示连接状态）。
- 配置：MCDR 工作目录下 `config/mcdr2web.json`，字段 `ws_host` / `ws_port` / `tps_report_interval`。
- TPS/MSPT 采集：RCON `tick query`；玩家上限：RCON `list`。RCON 未开启时对应字段为空。
- `whitelist_api`（未入库）：按 `server.properties` 的 `online-mode`（以及 Paper/Velocity 配置）区分正版 / 离线模式；正版模式走服务器命令，离线模式维护 `whitelist.json`。
- `online_player_api`（未入库）：内存维护在线名单，提供 `get_player_list` / `is_online`。

> `whitelist_api/` 与 `online_player_api/` 在 `.gitignore` 中被忽略，不在版本库中；全新克隆仓库时插件无法加载，需要另行获取（或从已部署的 MCDR 环境拷贝）。

---

## 9. 数据层（SQLite）

### 9.1 文件与连接模型

| 文件 | 内容 |
|------|------|
| `data/database/basic_user_data.db` | `users` + `user_info` |
| `data/database/basic_message_data.db` | `messages` |
| `data/database/exam_data.db` | `exam_answers` + `exam_profiles` |
| `data/database/wiki.db` | `pages` + `revisions` + `redirects` + `wiki_fts`（FTS5 虚表） |
| `data/database/feedback.db` | `feedback` + `feedback_comments` |

- 路径统一锚定到 `data/database/`（与启动时的工作目录无关）。
- 每个库一个进程级连接；`check_same_thread=False` + 连接级 `RLock` 串行化访问，`cached_statements=0`。
- 启动时自动建表 / 补列迁移（`PRAGMA table_info` + `ALTER TABLE ADD COLUMN`）；wiki 有旧库结构迁移逻辑。
- **没有外键、没有跨语句事务**：多步业务由多次提交组成，级联（如删页删修订）由应用层手写 SQL 完成。
- `users` 与 `user_info` 是**两条独立连接打开同一个文件**；并发写入依赖 SQLite 文件锁（未设置 `busy_timeout`）。

### 9.2 表结构

**`users`**

| 列 | 类型 | 说明 |
|----|------|------|
| `uid` | INTEGER PK AUTOINCREMENT | 自增、永不重复 |
| `email` | TEXT NOT NULL UNIQUE | 唯一邮箱 |
| `username` | TEXT NOT NULL UNIQUE | 唯一用户名 |
| `fullname` | TEXT | 昵称（可空） |
| `password` | TEXT NOT NULL | `salt$hash`（前端 SHA-256 后加盐） |
| `avatar` | TEXT | 头像文件名（可空） |
| `permission` | INTEGER NOT NULL DEFAULT 1 | 0–4 |
| `locked` | INTEGER NOT NULL DEFAULT 0 | 是否锁定 |
| `banned` | INTEGER NOT NULL DEFAULT 0 | 是否封禁 |

**`user_info`**（与 `users` 1:1）

| 列 | 说明 |
|----|------|
| `uid` | 主键，对应 `users.uid` |
| `birthday_year` / `birthday_month` / `birthday_day` | 生日 |
| `gender` | 性别 |
| `player_name` | 主游戏名（唯一索引） |
| `followers` / `followings` | 粉丝 / 关注 uid 列表（JSON） |
| `profile` | Markdown 简介 |
| `alt_accounts` | 小号列表（JSON） |
| `premium_flags` | 各游戏账号正版标记（JSON） |

**`messages`**

| 列 | 说明 |
|----|------|
| `id` | 主键 |
| `scope` | `system` / `user` |
| `target_uid` | 定向消息接收者（系统消息为空） |
| `title` / `content` | 标题 / Markdown 正文 |
| `author_uid` | 发布者 uid（系统消息为管理员） |
| `read_uids` | 已读用户 uid 列表（JSON） |
| `created_at` / `updated_at` | 时间 |

**`exam_answers`**

| 列 | 说明 |
|----|------|
| `id` | 主键 |
| `uid` | 考生 uid |
| `question_id` | 题号 |
| `answer` | 答案（JSON） |
| `attachment` | 附件文件名列表（JSON） |
| `obtained_score` | 本题得分 |
| `answered_at` | 作答时间 |

唯一约束：`(uid, question_id)`。

**`exam_profiles`**

| 列 | 说明 |
|----|------|
| `uid` | 主键 |
| `player_name` / `is_premium` | 考试档案中的玩家名 / 正版状态 |
| `attempts` | 已交卷次数（上限 2） |
| `passed` | 是否通过 |
| `review_requested` | 本轮是否已申请重审 |
| `updated_at` | 更新时间 |

**`feedback`**

| 列 | 说明 |
|----|------|
| `id` | 主键 |
| `title` / `content` | 标题 / Markdown 正文 |
| `category` | `bug` / `suggestion` / `other` |
| `status` | `pending` / `resolved` / `closed` |
| `author_uid` | 提交者 uid |
| `created_at` / `updated_at` | 创建 / 最近编辑时间 |

**`feedback_comments`**

| 列 | 说明 |
|----|------|
| `id` | 主键 |
| `feedback_id` | → `feedback.id`（删反馈时由应用层级联删除） |
| `author_uid` | 评论者 uid |
| `content` | Markdown 评论正文 |
| `created_at` | 评论时间 |

**`pages`**

| 列 | 说明 |
|----|------|
| `id` | 主键 |
| `slug` | 页面路径（唯一；小写 ASCII 段，`/` 分层） |
| `title_zh` / `content_zh` / `title_en` / `content_en` | 双语标题与 Markdown 正文（标题自动取自首个 H1） |
| `min_permission` | 最小编辑权限（2/3/4，默认 2） |
| `disambig` | 是否为消歧义页 |
| `author_uid` / `updated_by_uid` | 创建者 / 最后编辑者 |
| `created_at` / `updated_at` | 时间 |

**`revisions`**

| 列 | 说明 |
|----|------|
| `id` | 主键 |
| `page_id` | → `pages.id`（删页时由应用层级联删除） |
| `lang` | `zh` / `en` |
| `rev_no` | 每种语言自 1 递增；每页每语言仅保留最近 100 条 |
| `title` / `content` | 该修订的快照 |
| `summary` | 编辑摘要（可空） |
| `author_uid` | 编辑者（0 表示系统） |
| `created_at` | 时间 |

**`redirects`**

| 列 | 说明 |
|----|------|
| `id` | 主键 |
| `from_slug` | 旧路径（唯一，不能是现有页面） |
| `to_slug` | 目标路径（可链式，解析最多 8 步） |
| `created_at` | 时间 |

**`wiki_fts`（FTS5）**

```sql
CREATE VIRTUAL TABLE wiki_fts USING fts5(
  slug UNINDEXED, title_zh, content_zh, title_en, content_en, tokenize='trigram'
);
```

- 没有 SQL 触发器，文章写入后由应用层**全量重建**该索引；查询 <3 字符时直接走 `LIKE` 兜底；FTS 出错时同样回退 `LIKE`。
- 标题加权排序使用 BM25（中英文分别对对应语言的标题 / 正文列加权）。

---

## 10. 上传与文件存储

| 用途 | 目录 | 大小上限 | 允许类型 |
|------|------|----------|----------|
| 用户头像 | `data/avatar/` | 2MB | jpg / png / webp / ico |
| 答题附件 | `data/exam_upload/` | 20MB | jpg / png / webp / gif |
| 试卷附图 | `data/exam_image/` | 5MB | jpg / png / webp / gif |
| 试卷说明文档 | `data/exam_image/` | 10MB | 仅 `.docx` |
| 维基媒体 | `data/wiki_upload/` | 图片 5MB / 视频 50MB / 音频 20MB | png/jpg/jpeg/webp/gif、mp4/webm/mov、mp3/wav/ogg/m4a/aac/flac |

- 文件名使用随机 uuid，服务端保存时按声明的 Content-Type / 扩展名白名单校验，**不检查文件真实内容**。
- 以上目录均被 `.gitignore` 忽略，部署与备份时需单独处理。

---

## 11. 部署

### 11.1 后端

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 7777
```

- 以**单 worker** 运行（验证码、登录失败计数、服务器状态缓存等均为进程内状态，多 worker 会互相不可见）。
- 需要长期运行时可交给 systemd / supervisor / Windows 服务等进程管理器；本地一键启动可直接用 `python manage.py --prod`。
- 首次启动会自动创建数据表、播种维基欢迎页；欢迎页内容随版本升级自动刷新（仅当未被用户编辑过时，以「系统」身份追加修订并保留旧版历史）；`data/` 下缺少的配置文件会以默认值生成，需要手工补全密钥（见 5.2）。

### 11.2 前端

```bash
cd whs
npm install
npm run build        # 产物：whs/dist/
```

### 11.3 反向代理（nginx 示例）

后端不提供静态文件（`GET /` 只返回 JSON），生产环境由 Web 服务器托管 `dist` 并转发 `/api`：

```nginx
server {
    listen 80;
    server_name example.com;

    location /api/ {
        proxy_pass http://127.0.0.1:7777;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        root /path/to/WHS_Webpage/whs/dist;
        try_files $uri /index.html;    # SPA history 模式回退，深链必需
    }
}
```

- 前后端必须**同源**部署（后端没有 CORS 中间件）；同上 nginx 方案即满足。
- MCDR 插件的 WS 是环回地址，不需要也不应该代理到公网。
- 若用 `npm run preview` 代替 nginx，注意它默认监听 `0.0.0.0:5173`（局域网可见）。

### 11.4 端口一览

| 端口 | 服务 | 监听地址 |
|------|------|----------|
| 7777 | 后端 HTTP API | `127.0.0.1`（经反代对外） |
| 5173 | 前端开发 / 预览服务器 | dev 默认 localhost；preview 为 `0.0.0.0` |
| 8765 | 后端 ↔ MCDR 的 WS | `127.0.0.1`（由 `ws_port` 配置） |

---

## 12. 运维脚本与开发工具

### `manage.py`（统一启动管理器）

- 同时托管前端与后端两个子进程，实时转发两路日志到终端并写入 `logs/`；停止时先前端后后端，超时强杀进程树。
- `--dev` / `--prod` 选择前端环境；不带参数时交互询问。
- 需要 `backend/venv` 与 `whs/node_modules` 已存在（缺失会在启动前检查并提示）。

### `express_set_perm.py`（慎用）

直接连接 `data/database/basic_user_data.db` 修改任意用户的 `permission`，**绕过 API 权限校验**，且使用相对路径（必须在项目根目录运行）。仅供运维应急。

### `unlock_user.py`（尚未入库）

离线解锁账号：使用后端同一套数据库对象清除 `locked` 标记。注意它不会清理后端进程内的失败计数，解锁后再次输错可能立刻重新锁定；带内存清理的正式接口是 `POST /api/user/{uid}/unlock`。

### `pseudo_mcdr/`（未入库，WS 测试替身）

无需真实 MCDR 即可验证 WS 通路与服务器状态接口：

```bash
python pseudo_mcdr/pseudo_mcdr.py --selftest     # 连接 WS 并调用 HTTP 接口做端到端自检
python pseudo_mcdr/pseudo_mcdr.py                # 交互模式
```

参数：`--host`（默认 127.0.0.1）、`--port`（默认 8765，需与 `ws_port` 一致）、`--tps-interval`（默认 60，0 关闭）、`--selftest`、`--http-base`（需与后端端口一致，当前为 `http://127.0.0.1:7777`）。交互命令：`ping / players / wl / online / add / remove / report / status / quit`。

### `SMTP/`（未入库，本地收信调试服务）

```bash
python SMTP/mail_server.py
```

监听 `127.0.0.1:2000`，把收到的邮件保存为 `SMTP/inbox/*.eml`；与默认配置（`whs_config.json` 的 `smtp.host=localhost`、`port=2000`、`use_ssl=false`）配套，用于本地调试验证码邮件而不真正外发。

---

## 13. 已知限制与注意事项

- **单进程假设**：验证码、发送冷却、登录失败计数、TPS / 服务器状态缓存都在进程内存中；多 worker 部署会出现行为不一致。
- **token 不可吊销**：HMAC 自签 token 有效期 7 天，无刷新 / 登出接口，改密码不会使旧 token 立即失效（banned / locked 会在请求时拦截）。
- **密钥兜底**：`config.json` 读取异常时 token 密钥会回退到代码内默认值，部署时必须保证配置文件可读且 `token_secret` 为强随机值。
- **验证码**：存于内存（重启丢失）、5 分钟有效，并会打印到后端 stdout；重置密码等流程没有尝试次数上限。
- **上传校验**：仅校验声明的类型 / 扩展名与大小，不校验文件真实内容。
- **无 CORS 中间件**：前端与 API 必须同源（开发用 Vite 代理，生产用反向代理）。
- **数据库**：无外键、无跨语句事务；部分业务（注册、注销、关注）中途失败可能留下部分写入。
- **考试接口**：`/api/exam/answer` 会返回对错并允许覆盖提交，`reset` 不消耗次数；接口层面未强制 `can_answer`（仅部分接口检查）。
- **仓库内容**：`whitelist_api`、`online_player_api`、`pseudo_mcdr`、`SMTP` 不在版本库中；仓库内也没有自动化测试 / CI 配置。
- **Python 版本**：必须 ≥ 3.12（代码使用了 3.12 才支持的 f-string 语法）。

---

## License

MIT License. Copyright (c) 2026 WangHai Server.
