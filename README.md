# WHS Webpage

[![CI](https://github.com/Wanghai-Server/WHS_Webpage/actions/workflows/ci.yml/badge.svg)](https://github.com/Wanghai-Server/WHS_Webpage/actions/workflows/ci.yml)

望海服务器（WangHai Server）官方网站。Vue 3 单页前端 + FastAPI 后端 + SQLite，内置完整用户系统（注册 / 登录 / 资料 / 头像 / 关注 / 消息 / 入服考试 / 反馈中心 / 管理端）与自研现代化维基，并通过本机 WebSocket 与 Minecraft 服务器的 MCDR 插件双向通信（在线名单、TPS、白名单）。

- 中英文双语切换（vue-i18n + 维基内容按语言实时请求后端）
- 深色 / 浅色主题，响应式布局
- 前端生产模式由 Vite 构建，后端只提供 `/api/*`，静态资源需单独托管（见「部署」）
- 统一启动器：根目录 `manage.py` 同时拉起前端与后端，收集两路日志并统一关停
- 统一 Markdown 体系：全站共用一套渲染管线（`§` 颜色、LaTeX、mermaid、代码语法高亮）与通用 Markdown 编辑器（编辑 / 预览、语法工具条、附件上传）

---

## 目录

1. 架构总览
2. 功能特性
3. 技术栈
4. 项目结构
5. 快速开始
6. HTTP API（共 106 条）
7. WebSocket 协议（后端 ↔ MCDR）
8. MCDR 插件
9. 数据层（SQLite）
10. 上传与文件存储
11. 部署
12. 运维脚本与开发工具
13. 已知限制与注意事项
14. CI（GitHub Actions）
15. License

---

## 1. 架构总览

```
浏览器（Vue 3 SPA）
   │  静态资源：Vite dev/preview 或生产环境 nginx/Caddy 托管 whs/dist
   │  HTTP /api/* ──(dev/preview 代理 或 反向代理)──▶ FastAPI（uvicorn 127.0.0.1:7777）
   │                                                  ├─ 6 个数据库单例 → data/database/*.db（sqlite3，无 ORM）
   │                                                  ├─ 上传目录 data/{avatar,exam_image,exam_upload,wiki_upload,markdown_upload}
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
- 管理端悬浮框（用户 / 考试 / 反馈 / 试卷管理、答题卡）统一为单滚动区：桌面端最大高度取遮罩可用高度（视口高度减去上下留白），内容装得下时不出现滚动条、内容少时高度随内容收缩；内容超高时才滚动；头部与翻页栏随内容滚动、不叠加额外背景色；打开时锁定背景页面滚动，滚轮落在代码块 / 表格等小滚动框上时仍可滚动主对话框；手机端在表格等横向滚动区域内的纵向滑动也会转发给主对话框（横向滑动仍交给表格自身）；翻页栏在内容末尾，滚到底即可翻页。
- 非法路由（不存在的站内路径）按 `whs_config.json` 的 `301` 配置统一跳转（站内路径或外链）。

### 用户系统

- 注册：分三步完成——① 邮箱 + 邮箱验证码 + 人机验证（不写数据库，验证通过后由后端在内存签发一次性注册凭证）；② 用户名 + 密码（前端 SHA-256 后传输，提交前校验强度）；③ 完善资料（头像 / 性别单选 / 生日，可留空 = 不透露）。第二步创建账号成功后才写数据库。
- 注册密码强度：至少 8 位、包含数字、同时包含大写和小写字母；未失焦时未满足项为灰色，失焦后标红、满足项标绿；下方进度条 + 低/中/高等级（等级只在三条要求全部满足后按熵估算计算），不满足强度拒绝提交。密码允许数字、字母与常见特殊字符（ASCII，含 `!@#$%^&*` 等）；特殊字符不强制要求，但会计入字符池熵估算、提升强度等级，UI 中作为第 4 条“可选”检查项展示（缺失不标红、不拦截提交）。
- 注册验证码：连续错误 5 次锁定该邮箱 1 小时（发送与校验都拒绝）；发送失败时后端回滚内存中的验证码与 60s 冷却，允许立即重试。
- 登录：账密模式（邮箱 / UID / 用户名 + 密码）或邮箱验证码模式；连续输错 5 次自动锁定账号。
- 密码安全：前端先 SHA-256，后端再加随机盐存储（`salt$hash`）；原始密码不出浏览器。
- 登录态：HMAC-SHA256 自签 token（JWT 风格，无第三方依赖），`Authorization: Bearer <token>`，有效期 7 天。
- 账号状态：`banned`（封禁）/ `locked`（锁定）由统一依赖拦截，受保护接口一律 403。
- 用户主页：昵称 / 生日 / 性别 / Markdown 简介 / 头像；关注与粉丝列表；UID 复制。
- 账号设置：昵称、性别、生日、个人简介、头像、邮箱、密码、游戏账户；其中个人简介 / 基本资料 / 管理游戏账户为“行式入口 + 悬浮窗”编辑，基本资料的性别单选项与生日输入框与注册表单一致。
- 修改密码：先校验当前邮箱验证码与旧密码，再设置新密码；新密码输入框带与注册相同的强度提示（进度条 + 三条硬性要求 + 可选特殊字符），不满足强度不提交；密码可见性切换与其它表单一致。
- 改头像、改邮箱（验证码）、找回密码、退出登录、注销账号。
- 密码可见性：登录 / 注册 / 找回密码 / 修改密码 / 注销账号的密码框右侧带眼睛按钮，可切换明文 / 密文；注册等多密码框表单共用一个按钮同时控制。
- 游戏账户：绑定主账号与最多 2 个小号，记录正版 / 离线标记，支持修改主账号正版状态；添加小号自动加入游戏白名单。玩家名（主账号 / 小号 / 考试填写）统一遵循 Minecraft Java 官方规则：**3–16 位、仅英文字母 / 数字 / 下划线**；考试结束后（通过或答题次数用完）玩家名锁定，不可再修改。
- 权限等级：`0=guest / 1=user / 2=player / 3=admin / 4=owner`；注册默认 1，入服考试及格自动升到 2。

### Markdown 体系

- 统一渲染管线（`whs/src/composables/markdown/renderer.js`）：全站 Markdown 共用同一套 markdown-it 配置与插件，支持维基同款 `§` 颜色 / 格式代码、LaTeX（`$...$` / `$$...$$`，KaTeX）、mermaid 图表、代码块语法高亮（highlight.js 全语言）、外链新窗口、标题 id / 目录、图片与音视频媒体渲染。
- 统一编辑器（`whs/src/components/markdown_editer.vue`）：GitHub 风格“编辑 / 预览”标签页 + 语法提示工具条 + 字数统计；图片 / 视频 / 音频上传（类型与大小同维基）支持点击、粘贴文件与拖拽到组件区域；代码块带语言栏与复制按钮，mermaid 图右上角可复制源码。
- 渲染性能：KaTeX / mermaid / highlight.js 均按需懒加载（不进入首屏包）；mermaid 语法错误不向页面追加错误图，只在图表位置提示原始代码。
- 使用位置：个人简介、消息发布 / 编辑、反馈提交 / 编辑、反馈评论、试卷说明 = 统一编辑器；个人主页简介、消息详情、反馈详情 / 评论、考试说明、维基正文 = 统一渲染组件（`markdown_view.vue`；维基另有排版包装 `wiki_markdown.vue`）。
- 编辑器支持 `multilingual` 参数（v-model 为 `{ zh, en }` 对象，编辑与编辑预览按所选语言，站点展示始终跟随网站语言）；系统消息的标题 + 正文已启用该模式（发布 / 编辑时统一语言切换），个人简介 / 反馈 / 试卷说明等其余非维基字段仍是单语言字符串。

### 消息中心

- 系统消息（管理员发布，Markdown）与定向消息（玩家通知）。
- 标题 / 正文均为双语对象 `{ zh, en }`：列表与详情按站点语言展示，缺失语言自动回退另一种；旧消息只有中文时，英文界面显示中文。发布 / 编辑对话框用统一语言切换（同一开关同时控制标题与正文）。
- 已读状态按用户记录（`read_uids`），未读数量徽标；管理员编辑消息后全员重新未读。
- 「全部已读」按钮一键清除未读（透明无边框、扫把图标；手机端仅图标）。
- 管理员可发布 / 编辑 / 删除自己发布的系统消息；用户可查看消息详情。
- 发布 / 编辑对话框使用统一 Markdown 编辑器（编辑 / 预览标签页、语法工具条、上传 / 粘贴 / 拖拽），预览与详情使用同一渲染管线，表格、代码块、LaTeX、mermaid、颜色代码等所见即所得。

### 入服考试

- 玩家端：阅读考前须知 → 完善游戏名 / 正版状态 → 逐题作答（答案自动保存，可上传附件）→ 交卷；最多 2 次机会，60% 及格。
- 题型：单选、多选（部分分）、填空（按空给分）、主观题（人工改分）。
- 及格副作用：写入玩家名、权限 < 2 时提升到 player、标记通过、自动加入游戏白名单。考试结束后（通过或答题次数用完）`POST /api/exam/profile` 拒绝再修改玩家名（`exam_profile_locked`）。
- 未通过可重新作答，也可提交人工重审（通知全部管理员，站内消息 + 邮件）。
- 管理端：查看考生列表、试卷在线编辑（覆盖 `data/exam.yml` 即时生效）、查看/改分答题卡、删除答卷、上传题目附图与说明文档（.docx）；试卷说明使用统一 Markdown 编辑器（含图片 / 视频 / 音频上传）。

### 维基（自研，不依赖开源维基程序）

- 页面内容为 Markdown，存于 SQLite（`wiki.db`），中英双语各存一份；标题从正文首个 H1 自动提取。
- 正文使用全站统一渲染管线：`§` 颜色代码、LaTeX（KaTeX）、mermaid 图表、代码块语法高亮（highlight.js）、音视频媒体均与站内其它 Markdown 一致；代码块带语言栏与复制按钮，mermaid 图右上角可复制源码。
- 目录（TOC）由前端渲染时从 Markdown 标题（h1–h6）自动生成，滚动高亮、点击定位、阅读进度。
- 搜索：SQLite FTS5 全文索引（`trigram` 分词，中文/英文 3 字符及以上子串匹配，BM25 标题加权），短查询自动回退 LIKE。
- 每页独立的**最小编辑权限**（2/3/4）：普通玩家默认 2，管理员可调高；页面级写操作按页面自身权限校验。
- 修订历史：每次保存生成一条修订（作者 + 摘要 + 时间），每页每语言保留最近 100 条；管理员可查看任意版本并回滚；页面展示历史贡献者与编辑次数。
- 乐观锁：保存携带 `base_rev`，他人已修改时返回 409，前端提示「加载最新 / 强制保存」。
- 重定向：页面改名后旧路径自动跳转（支持重定向链，最多 8 步，拒绝循环）；管理员可增删查。
- 消歧义页：编辑器可标记「消歧义页」；系统也会在启动与页面写操作时自动构建/清理自动消歧义页（被人工编辑过的自动页不再接管）。
- 媒体上传：图片（≤5MB）/ 视频（≤50MB）/ 音频（≤20MB），插入 Markdown 后渲染为图片、`<video>`、`<audio>` 播放器；编辑器支持点击上传、粘贴文件与**全屏拖拽**上传，上传规则与全站 Markdown 编辑器共用同一套白名单 / 大小限制。
- 颜色 / 格式代码：支持 MC 风格的 `§` 代码（全站 Markdown 通用，包括维基、反馈、消息、考试提示与用户简介）——`§0`–`§f` 为 MC 官方 16 色，`§#RRGGBB` 支持任意 HEX；`§l` 粗体、`§o` 斜体、`§n` 下划线、`§m` 删除线、`§r` 复位。代码块与行内代码内不解析；编辑器工具栏提供颜色下拉（选中文字上色并自动加 `§r`，光标处插入则按 MC 规则持续生效）；页面标题 / 搜索与列表摘要会自动剥离 `§` 代码。注意：颜色代码会重置格式，需要「颜色 + 粗体」时先写颜色再写格式（如 `§e§l文字`）。
- 编辑器：保留双栏实时预览、语言切换、附件上传、拖拽分栏、未保存离开确认；语法插入 / 撤销 / 上传片段生成复用全站共享工具（`composables/markdown/insert.js`），预览使用统一渲染组件。
- 文档导入：编辑器工具栏可直接选 `.docx` / `.xlsx`，服务端转成 Markdown 插到光标处，作者确认后再保存。Word 的标题层级、粗体斜体、项目符号/编号列表、引用、表格和内嵌图片都会保留（图片存进 `data/wiki_upload/`，正文替换为图片地址）；Excel 每个工作表转一张表，多表用二级标题分开。限制：单文件 ≤30MiB、表格单元格总数 ≤20000。转换失败或文件损坏会提示，不会写坏现有正文。

### 全站搜索

- 顶部导航搜索（桌面端）：滑入式小面板，防抖实时建议，Wiki 页面与用户分组展示；标题 / 用户名 / 玩家名 / UID 完全相等时直接打开对应页面。手机端导航搜索按钮直接进入 `/search`。
- `/search` 全量搜索页：一次请求同时检索 Wiki（FTS5 + 摘要）、用户（用户名 / uid / 玩家名 / 昵称 / 小号名）与反馈（标题 / 正文 + 命中摘要）；结果按「Wiki / 用户 / 反馈」标签页分组展示。

### 反馈中心

- 公开浏览：`/feedback` 列表（分页、状态筛选、关键词搜索）与 `/feedback/:id` 详情页；列表/详情无需登录。
- 提交与评论需登录：标题 + 分类（问题 / 建议 / 其他）+ Markdown 正文，正文使用统一 Markdown 编辑器（编辑 / 预览、语法工具条、上传 / 粘贴 / 拖拽）；详情页评论回复同样使用该编辑器，评论内容以统一渲染管线展示。
- 状态流转：`pending`（待处理）/ `resolved`（已处理）/ `closed`（已关闭）；管理员可在详情页或管理端修改状态。
- 权限：作者可编辑 / 删除自己的反馈；管理员（permission ≥ 3）可删除任意反馈、修改状态。
- 管理端：用户页「管理员」→「反馈管理」，列表支持状态筛选、分页、查看、改状态、删除（带确认框）。
- 入口：底部页脚「快速链接 → 反馈」；顶部导航不放入口。
- 存储：`feedback` + `feedback_comments` 两张 SQLite 表（`data/database/feedback.db`）。

### 服务器状态

- 在线人数 / TPS / MSPT / 玩家上限全部来自 MCDR 插件上报（在线名单 + RCON `tick query` / `list`），后端缓存 5 分钟。
- `bot_` 前缀视为假人，不计入官网在线人数；WS 不可用时回退上一次缓存或离线占位。
- 白名单列表接口已提供（前端预留成员墙用途）。

### 工程管理

- 公开浏览 `/projects`：按状态筛选（全部 / 待认领 / 已认领 / 已完成）、查看详情；入口只放在用户下拉栏（顶部 / 底部导航不放入口）。
- 权限与游戏内插件逻辑一致：发起需 permission ≥ 3（创建者使用已绑定的 MC 账号）；认领需 ≥ 2；完成需发起者或 ≥ 3；删除需 ≥ 4（任意状态），否则仅未认领时 ≥ 3 或发起者可删；描述 / 备注仅发起者或 ≥ 3 可编辑。
- 数据源是游戏内 signup 插件的 `project.json`（经 mcdr2web 的 WS 桥接），网页不另存工程库；网页改动立即对游戏内 `!!signup project` 可见，反之亦然。
- 描述为 Markdown、备注为纯文本，均不能在游戏内修改；创建 / 认领 / 完成 / 更新时间由插件自动记录。
- 多账号（主账号 + 小号）可在发起 / 认领时选择，默认主账号；「下次保持当前选择」只写浏览器 localStorage。
- 游戏服务器离线时显示横幅并禁用写操作，列表回退 10 秒缓存并标记 stale。

---

## 3. 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3（Composition API + `<script setup>`） |
| 构建 / 开发服务器 | Vite 8（`/api` 在 dev 与 preview 下均代理到 `127.0.0.1:7777`） |
| 路由 | Vue Router 5（history 模式，页面全部懒加载） |
| 国际化 | vue-i18n 9 |
| 图标 / 动画 / 3D | lucide-vue-next / animejs / skinview3d |
| Markdown | markdown-it + 自研统一渲染管线（§ 颜色、标题 id、目录、媒体、代码块语言栏）；highlight.js（代码高亮）、KaTeX（LaTeX）、mermaid（图表），三者均按需懒加载 |
| DOCX 渲染 | mammoth（考试说明文档） |
| 人机验证 | hCaptcha（`@hcaptcha/vue3-hcaptcha`） |
| 后端框架 | FastAPI + uvicorn |
| 表单 / 上传 | python-multipart |
| 数据库 | SQLite（标准库 `sqlite3`，手写 SQL，无 ORM） |
| 实时能力 | `websockets`（后端 WS 服务 + MCDR 插件客户端） |
| 试卷配置 | PyYAML（`data/exam.yml`） |
| 邮件 | 标准库 `smtplib`（外部 SMTP） |
| MCDR 插件 | mcdreforged ≥ 2.15、whitelist_api ≥ 2.0、online_player_api ≥ 1.0；工程桥接依赖 signup ≥ 1.6（可选，缺失时工程接口返回离线提示） |

> Python 版本要求 **≥ 3.12**（后端代码使用了 PEP 701 的嵌套 f-string 语法），`backend/requirements.txt` 未固定 Python 版本。

---

## 4. 项目结构

```
WHS_Webpage/
├── manage.py                        # 统一启动管理器（前端 dev/prod + 后端 + 日志收集 + 统一关停）
├── README.md
├── CONTRIBUTING.md                  # 贡献指南：PR 要求 / main 分支保护 / 前后端可复用代码
├── LICENSE
├── .github/                         # GitHub 配置与 CI
│   ├── CODEOWNERS                   # 默认审核人（PR 自动请求审核）
│   ├── PULL_REQUEST_TEMPLATE.md     # PR 模板（变更类型 / 验证方式 / 截图 / 核对清单）
│   ├── ISSUE_TEMPLATE/              # Issue 模板
│   │   ├── bug_report.yml           # Bug 报告（自动打 bug 标签）
│   │   ├── feature_request.yml      # 功能建议（自动打 enhancement 标签）
│   │   └── config.yml               # 模板选择页配置（快捷链接、允许空白 Issue）
│   ├── workflows/ci.yml             # GitHub Actions：前端 / 后端 / 数据层 / MCDR 四层校验
│   └── scripts/                     # CI 校验脚本（可本地复跑，见第 14 节）
│       ├── backend_smoke.py
│       ├── data_smoke.py
│       └── mcdr_check.py
├── express_set_perm.py              # 运维脚本：离线修改用户权限（直接写 SQLite，慎用）
├── unlock_user.py                   # 运维脚本：离线解锁账号（尚未纳入版本库）
│
├── backend/                         # 后端（FastAPI）
│   ├── main.py                      # 组合根：数据库实例、token/密码/hCaptcha/SMTP、考试判分、
│   │                                #   错误码表、全局异常处理、lifespan、路由注册
│   ├── ws_server.py                 # 与 MCDR 插件通信的 WS 命令服务（127.0.0.1:<ws_port>）
│   ├── requirements.txt
│   ├── api/                         # 路由层（按业务拆分，共 106 条路由）
│   │   ├── __init__.py
│   │   ├── site.py                  # 服务状态 / 站点公开配置
│   │   ├── auth.py                  # 验证码 / 注册 / 登录 / 账号信息 / 解锁
│   │   ├── user.py                  # 用户主页 / 关注 / 资料 / 邮箱 / 密码 / 注销 / 封禁 / 权限 / 游戏账户
│   │   ├── avatar.py                # 头像上传与读取
│   │   ├── message.py               # 系统消息 / 定向消息 / 已读 / 消息管理
│   │   ├── exam.py                  # 入服考试（考生端 + 管理端）
│   │   ├── feedback.py              # 反馈中心（列表 / 详情 / 提交 / 编辑 / 删除 / 评论 / 状态）
│   │   ├── project.py               # 工程管理（列表 / 发起 / 认领 / 完成 / 删除 / 描述备注；经 WS 读写 signup）
│   │   ├── server.py                # 服务器实时状态
│   │   ├── search.py                # 全站搜索（Wiki + 用户 + 反馈）
│   │   ├── wiki.py                  # 维基（页面 / 修订 / 重定向 / 消歧义 / 媒体）
│   │   ├── markdown.py              # 全站 Markdown 编辑器媒体上传 / 读取
│   │   └── media_upload.py          # 媒体上传共享工具（白名单 / 大小限制 / 落盘 / 读取）
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
│   ├── wiki_upload/                 # 维基媒体文件（不入库）
│   └── markdown_upload/             # 全站 Markdown 编辑器媒体文件（不入库）
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
│       │   ├── useEmailCode.js      # 邮箱验证码发送 / 冷却 / 重置人机验证（统一封装）
│       │   ├── usePasswordStrength.js # 密码强度规则、低/中/高等级与熵估算
│       │   ├── useProjectPlayer.js  # 工程账号选择记忆（仅 localStorage）
│       │   ├── sha256.js            # 前端密码哈希
│       │   ├── clipboard.js
│       │   ├── markdown/            # 统一 Markdown 体系
│       │   │   ├── renderer.js      # 全站渲染管线（§ 颜色 / LaTeX / mermaid / 代码占位 / 媒体 / 标题目录）
│       │   │   ├── insert.js        # 语法插入 / 媒体片段生成（编辑器与维基共用）
│       │   │   ├── upload.js        # Markdown 编辑器上传（/api/markdown/upload）与类型 / 大小常量
│       │   │   └── colorCodes.js    # MC § 颜色 / 格式代码插件
│       │   └── wiki/{api,locale,markdown}.js  # 维基 API / 语言状态 / Markdown 兼容层（委托统一渲染管线）
│       ├── components/              # 42 个可复用组件
│       │   ├── 导航与公共：top_navbar / page_footer / global_search / user_dropdown / tabs / tips / dialog_box / status_dropdown / hcaptcha_box
│       │   ├── 工程：project_create（发起）/ project_detail（详情与操作）/ project_account_dialog（认领 / 发起确认与账号选择）/ mc_account_picker（账号选择）
│       │   ├── Markdown：markdown_editer（通用编辑器）/ markdown_view（统一渲染与复制 / mermaid / 公式增强）
│       │   ├── 账号：login / register / forgot_password / full_user_info / username_suggestion / change_password / cancel_account / user_settings / manage_accounts / user_profile / basic_user_info / follow_list / player_info
│       │   ├── 消息：message_box / message_detail
│       │   ├── 反馈：feedback_editor
│       │   ├── 考试：exam_question / exam_editor / doc_viewer
│       │   ├── 维基：wiki_markdown / wiki_outline / wiki_outline_node / wiki_search / wiki_page_404
│       │   └── 管理：admin_settings / admin_user_panel / joinus_tips
│       └── pages/                   # 18 个页面
│           ├── home.vue / about.vue / map.vue / login.vue / user.vue / search.vue / joinus.vue / exam.vue
│           ├── forum/index.vue      # 论坛（静态占位）
│           ├── feedback/            # 反馈中心：index（列表） / detail（详情）
│           ├── project/index.vue    # 工程管理（列表 / 发起 / 详情；入口在用户下拉栏）
│           └── wiki/                # index / layout / page_view / page_editor / page_history / search
│
├── mcdr_connecter_plugin/           # MCDR 插件（mcdr2web）
│   ├── mcdreforged.plugin.json      # 插件元数据
│   ├── mcdr2web/__init__.py         # WS 客户端：连接 / 重连 / 双向请求、RCON 采集、命令注册、工程桥接（signup）
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

- **Python ≥ 3.12**（后端；CI 使用 3.14）
- **Node.js + npm**（前端构建 / 开发服务器；Vite 8 要求 Node `^20.19.0 || >=22.12.0`，CI 使用 22）
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

## 6. HTTP API（共 106 条）

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

### 6.3 认证（10 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/user/send_code` | 公开（需 hCaptcha） | 发送邮箱验证码；同邮箱 60s 冷却，验证码 5 分钟有效；发送失败回滚冷却与验证码；邮箱被锁定时 429 |
| GET | `/api/user/username_exists` | 公开 | 用户名是否已占用 |
| GET | `/api/user/player_name_exists` | 公开 | 玩家名是否已占用（含小号） |
| POST | `/api/user/suggest_username` | 公开 | 基于 base 推荐一个未占用用户名 |
| POST | `/api/user/register/email` | 公开 | 注册第一步：校验邮箱验证码，返回一次性注册凭证 `{ticket, email, expires_in}`（10 分钟、不写数据库）；验证码错误 5 次锁定该邮箱 1 小时 |
| POST | `/api/user/register` | 公开（注册凭证） | 注册第二步：`{ticket, username, password}` 创建账号；成功返回 `{uid, token}`；凭证无效返回 `register_ticket_invalid` |
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
| POST | `/api/admin/messages` | ≥3 | 发布系统消息 `{title:{zh,en}, content:{zh,en}}`（也兼容旧版字符串，按中文处理） |
| PUT | `/api/admin/messages/{message_id}` | ≥3 且作者本人 | 编辑系统消息（同一双语结构；全员重新未读） |
| DELETE | `/api/admin/messages/{message_id}` | ≥3 且作者本人 | 删除系统消息 |
| GET | `/api/message/{user_id}` | 登录且本人/≥3 | 定向消息列表 |

- 消息的 `title` / `content` 统一返回 `{zh,en}` 对象；前端按站点语言取值，缺失语言回退另一种。系统消息与定向消息（考试重审 / 通过通知）都带双语内容。

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
| POST | `/api/exam/profile` | 登录 | 保存玩家名与正版状态（玩家名 3–16 位字母/数字/下划线、全局查重；考试结束后 403 `exam_profile_locked`） |
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

### 6.11 维基（17 条）

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
| POST | `/api/wiki/import` | 登录且 permission≥2 | 上传 `.docx` / `.xlsx`（≤30MiB），返回转换后的 Markdown，不落库 |

### 6.12 在线地图（3 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/map/config` | 登录且 permission≥2 | 下发地图入口、地图列表与出生点，同时写入短期 HttpOnly Cookie（默认 600 秒） |
| GET | `/api/map/auth` | Cookie | 供 nginx `auth_request` 调用，凭据有效返回 204，否则 401 |
| GET | `/api/map/players?map_id=` | 登录且 permission≥2 | 当前世界在线玩家数量（已排除其他维度的 `foreign` 玩家） |

地图由服务器上的 BlueMap 网页端提供，地图页固定使用 3D 透视视图；后端不再代理瓦片，只负责鉴权与下发配置。

### 6.13 全站 Markdown 上传（2 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/markdown/upload` | 登录 | 上传 Markdown 编辑器媒体（multipart）；类型 / 大小与维基媒体相同：图片≤5MB / 视频≤50MB / 音频≤20MB；返回 `{url, type, original}` |
| GET | `/api/markdown/upload/{filename}` | 公开 | 读取已上传的 Markdown 媒体文件 |

- 文件保存到独立目录 `data/markdown_upload/`（与维基分开），随机 UUID 文件名；与 `/api/wiki/upload` 共用 `backend/api/media_upload.py` 的白名单 / 大小限制 / 落盘与读取逻辑。
- 错误码：`markdown_upload_unsupported`（400）/ `markdown_upload_too_large`（413）/ `markdown_upload_not_found`（404）。

### 6.14 工程管理（8 条）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/projects` | 公开 | 工程列表 + 状态计数 + 每项 `viewer` 标记；`online` / `stale` 表示 MCDR 桥接状态；10s 缓存 |
| GET | `/api/projects/detail?name=` | 公开 | 单个工程详情 + `viewer`；离线时返回缓存并标记 `stale` |
| GET | `/api/projects/accounts` | 登录 | 当前用户的 MC 账号（主账号 + 小号），供发起 / 认领选择 |
| POST | `/api/projects` | 等级 ≥ 3 | `{name, player}` 发起工程（玩家名必须是本人账号） |
| POST | `/api/projects/claim` | 等级 ≥ 2 | `{name, player}` 认领工程；同一用户任一游戏账号认领后不可再次认领 |
| POST | `/api/projects/complete` | 发起者或 ≥ 3 | `{name}` 标记完成 |
| DELETE | `/api/projects?name=` | ≥ 4 任意状态；否则未认领时 ≥ 3 或发起者 | 删除工程（与插件逻辑一致） |
| PUT | `/api/projects/meta` | 发起者或 ≥ 3 | `{name, description?, remark?}` 更新描述（Markdown ≤ 20000）/ 备注（纯文本 ≤ 500） |

- 数据源是游戏内 signup 插件的 `project.json`，经 `mcdr2web` 的 `project_*` WS 指令读写；后端不另存工程库。
- 工程名 1–32 字符（去首尾空白、禁止控制字符）；`player` 必须是当前用户的主账号或小号。
- 认领去重：网页按「用户」判断（主账号或任一小号已在认领者中即隐藏按钮并拒绝请求），工程数据仍按 MC 名记录；游戏内插件仍只按 MC 名判定。
- 错误码：`project_not_found`（404）/ `project_exists`（409）/ `project_name_invalid`、`project_player_invalid`、`project_already_claimed`、`project_not_claimed`、`project_completed`（400）/ `project_permission_denied`（403）/ `project_name_too_large`、`project_description_too_large`、`project_remark_too_large`（413）/ `project_unavailable`（503）。
- MCDR 离线：读接口回退缓存并返回 `online:false`，写接口返回 `project_unavailable`。

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
| 后端 → MCDR | `project_list` | 工程列表（含描述 / 备注 / 时间；数据源为 signup 插件的 `project.json`） |
| 后端 → MCDR | `project_get` | `{name}` → 单个工程 |
| 后端 → MCDR | `project_create` | `{name, creator}` → 创建工程（创建者身份由后端校验后传入） |
| 后端 → MCDR | `project_claim` | `{name, player}` → 认领工程（同一 MC 名不可重复认领） |
| 后端 → MCDR | `project_complete` | `{name}` → 标记完成 |
| 后端 → MCDR | `project_delete` | `{name}` → 删除工程 |
| 后端 → MCDR | `project_update` | `{name, description?, remark?}` → 更新描述 / 备注（仅官网编辑） |

断线重连由 MCDR 插件负责（固定 5s 重试，**日志只在连接状态变化时输出**）；后端 WS 未连接时，`/api/server/status` 回退上次缓存或离线占位，白名单相关操作失败只记日志、不阻断主流程；工程接口读操作回退 10s 缓存并标记 `online:false`，写操作返回 `project_unavailable`。

---

## 8. MCDR 插件

目录 `mcdr_connecter_plugin/`：

- 元数据（`mcdreforged.plugin.json` 与代码内 `PLUGIN_METADATA` 一致）：`id=mcdr2web`、`version=0.2.0`、`name=MCDR to Web`。
- 依赖：`mcdreforged>=2.15.0`、`whitelist_api>=2.0.0`、`online_player_api>=1.0.0`；插件自身依赖 `websockets`。
- 事件：仅 `on_load` / `on_unload`（在线玩家与服务器事件由 `online_player_api` 负责维护）。
- 命令：`!!mcdr2web ping`（测试后端 WS 连通）、`!!mcdr2web status`（显示连接状态）。
- 配置：MCDR 工作目录下 `config/mcdr2web.json`，字段 `ws_host` / `ws_port` / `tps_report_interval`。
- TPS/MSPT 采集：RCON `tick query`；玩家上限：RCON `list`。RCON 未开启时对应字段为空。
- 工程桥接：按需 `from signup import ...`（handler 内延迟导入）调用 signup ≥ 1.6.0 的工程数据函数；signup 未安装 / 版本过旧时工程指令返回 `project_unavailable`，不影响其他指令。工程描述 / 备注 / 时间不可在游戏内修改，signup 的 `website_url`（默认 `https://wanghaiserver.top:31480/`）决定游戏内"官网工程页"可点击链接。
- `whitelist_api`（未入库）：按 `server.properties` 的 `online-mode`（以及 Paper/Velocity 配置）区分正版 / 离线模式；正版模式走服务器命令，离线模式维护 `whitelist.json`。
- `online_player_api`（未入库）：内存维护在线名单，提供 `get_player_list` / `is_online`。

> `whitelist_api/`、`online_player_api/` 与 `signup/` 均在 `.gitignore` 中被忽略，不在版本库中；全新克隆仓库时插件无法加载，需要另行获取（或从已部署的 MCDR 环境拷贝）。signup 1.6.0 起工程记录新增 `description` / `remark` / `created_at` / `updated_at` / `claimed_at` / `completed_at` 字段，旧 `project.json` 加载时自动补全。

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
| `title` / `content` | 中文（主语言）标题 / Markdown 正文 |
| `title_en` / `content_en` | 英文标题 / 正文；为空字符串时展示回退到中文（旧消息自动补空列） |
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
| Markdown 编辑器媒体 | `data/markdown_upload/` | 图片 5MB / 视频 50MB / 音频 20MB | 与维基媒体相同（共用 `backend/api/media_upload.py` 的白名单与大小限制；上传需登录） |

- 文件名使用随机 uuid，服务端保存时按声明的 Content-Type / 扩展名白名单校验，**不检查文件真实内容**。
- 维基文档导入（`.docx` / `.xlsx`）不会写进上表目录，只有 Word 里内嵌的图片会落到 `data/wiki_upload/`，正文里替换成 `/api/wiki/upload/<uuid>.<ext>`。
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

- Markdown 渲染增强依赖 `highlight.js`（代码高亮）、`katex`（LaTeX）与 `mermaid`（图表），均由 `npm install` 安装，并在运行时按需懒加载：不进入首屏主包，但构建产物会包含 KaTeX 字体、mermaid / 高亮分块；部署机的 `npm install` 不能跳过。
- `npm run build` 输出中 KaTeX / mermaid / highlight 相关分块大于 500KB 属于预期（按需加载，不影响首屏），无需据此调整构建配置。

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
- 维基与全站 Markdown 编辑器支持视频上传（单个上限 50MB），请确认 nginx `client_max_body_size` 足够（建议 ≥55m）；否则上传会先被 nginx 以 413 拦截，后端无日志。

### 11.4 端口一览

| 端口 | 服务 | 监听地址 |
|------|------|----------|
| 7777 | 后端 HTTP API | `127.0.0.1`（经反代对外） |
| 5173 | 前端开发 / 预览服务器 | dev 默认 localhost；preview 为 `0.0.0.0` |
| 8765 | 后端 ↔ MCDR 的 WS | `127.0.0.1`（由 `ws_port` 配置） |
| 8100 | BlueMap 网页端（启用在线地图时） | `127.0.0.1`（由 nginx 反代 `/map3d/`） |

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
- **验证码**：存于内存（重启丢失）、5 分钟有效，并会打印到后端 stdout；注册验证码连续错误 5 次会锁定该邮箱 1 小时；注册凭证（ticket）同样只在内存中保存 10 分钟，重启后失效；重置密码等流程没有尝试次数上限。
- **注册三步**：第一步不写数据库，第二步创建账号、第三步完善资料分别写库；若用户中途放弃，账号已创建但资料为空，可登录后在设置中补齐。
- **上传校验**：仅校验声明的类型 / 扩展名与大小，不校验文件真实内容。
- **无 CORS 中间件**：前端与 API 必须同源（开发用 Vite 代理，生产用反向代理）。
- **数据库**：无外键、无跨语句事务；部分业务（注册、注销、关注）中途失败可能留下部分写入。
- **考试接口**：`/api/exam/answer` 会返回对错并允许覆盖提交，`reset` 不消耗次数；接口层面未强制 `can_answer`（仅部分接口检查）。
- **仓库内容**：`whitelist_api`、`online_player_api`、`signup`、`pseudo_mcdr`、`SMTP` 不在版本库中；仓库内没有单元测试框架，自动化校验由 CI（见第 14 节）覆盖前端构建、后端启动冒烟、数据层建库冒烟与 MCDR 插件打包 / 导入检查。
- **Markdown 渲染**：LaTeX / mermaid / 代码高亮全部在浏览器端按需加载（`katex` / `mermaid` / `highlight.js` 均在首次出现对应内容时下载分块），不参与首屏；超大 mermaid 图或超长代码块的高亮可能有可感知延迟。mermaid 使用 `securityLevel: strict`，语法错误只在图表位置显示原始源码，不向页面追加错误图、不执行图表脚本。
- **Markdown 多语言**：通用编辑器已支持 `multilingual`（v-model 为 `{zh,en}` 对象，编辑 / 预览按所选语言、展示跟随站点语言）；系统消息的标题与正文已启用双语（缺失语言回退），个人简介 / 反馈 / 试卷说明等其余字段仍为单语言；维基仍按 `lang` 列在数据库内存双份。
- **消息双语**：`messages` 表新增 `title_en` / `content_en` 两列，旧库启动时自动迁移、旧消息英文为空（展示回退中文）；定向消息（考试重审 / 通过通知）同样写入双语内容。管理员可在发布 / 编辑对话框补齐英文版本。
- **Markdown 上传**：全站 Markdown 编辑器上传要求登录（不检查 permission 等级），文件存 `data/markdown_upload/`；维基上传仍要求 permission ≥ 2，文件存 `data/wiki_upload/`；两处共用同一套类型 / 大小白名单，但不校验文件真实内容。
- **工程管理（`/projects`）**：数据源是 MCDR 侧 signup 插件的 `project.json`，网页不另存库；游戏服务器或 signup 插件不可用时列表只能读 10 秒缓存（标记 `stale`），写操作返回 503。描述 / 备注 / 时间只能官网编辑，游戏内 `get` 不展示描述与备注；删除权限与插件一致（4 级任意状态；未认领时 3 级或发起者可删）；认领按网站用户去重（任一账号已认领即隐藏 / 拒绝），游戏内仍按 MC 名。入口只在用户下拉栏。
- **Python 版本**：必须 ≥ 3.12（代码使用了 3.12 才支持的 f-string 语法）。
- **在线地图（`/map`）**：页面本身不含地图数据，由服务器上的 BlueMap 网页端提供 3D 透视视图。没部署时页面显示「服务器尚未开启在线地图」。安装和代理都在服务器上做：
  1. 服务端是 Fabric 1.21.11，BlueMap 要放进 `mods/`，不是 `plugins/`。版本按官方下载页标注的 1.21.11 支持线选（5.x，5.14 及以上），别拿面向 26.x 的最新构建。
  2. 首次启动会生成 `config/bluemap/`。`core.conf` 里 `accept-download` 改成 `true`（要联网下载原版材质）；`maps/world.conf` 里打开 `enable-perspective-view`，地图页固定使用 3D 透视；`enable-flat-view` 可保留但网站不再提供 2D 切换入口；BlueMap 5.x 没有 `display-type` 这个键。`webserver.conf` 里 `enabled` 改成 `true`、`port` 设 8100、`ip` 显式写 `127.0.0.1`，这一项默认是对外监听的。
  3. 第一次启动会全量渲染整张地图，吃 CPU 和磁盘，挑没人玩的时候跑，渲染线程数可以调低。
  4. nginx 把 `/map3d/` 反代到 `127.0.0.1:8100/`，`proxy_pass` 末尾必须带斜杠，否则路径会多一层 `map3d` 直接 404；同时转发 `Host`、去掉上游的 `X-Frame-Options` 和 CSP 里的 `frame-ancestors`，不然 iframe 会被浏览器拒绝；BlueMap 5.x 的在线玩家是轮询 `players.json`，关掉缓冲可以减少到达延迟。这段放进现有的 `server { listen 31480 ssl; ... }` 里即可。
  5. 代理必须挂鉴权。网站的登录态存在浏览器里，iframe 发请求时不会自己带上，所以后端通过 `/api/map/config` 下发一个 600 秒的 HttpOnly Cookie，nginx 用 `auth_request` 校验。注意 `auth_request` 是**每个子请求**都会触发的，3D 场景一次加载就有几百上千个瓦片和模型请求，不加缓存会把这些全部打到后端，必须按下面的配置给鉴权结果做缓存（通过的结果 60 秒，失败的结果 10 秒）：

```nginx
# 放在 http { } 块：鉴权结果缓存，否则 3D 场景里每个瓦片 / 模型请求
# 都会回源到后端一次，一个页面就是几百上千次
# cache/mapauth 目录要事先建好，路径相对于 nginx 的 prefix 目录
proxy_cache_path cache/mapauth levels=1:2 keys_zone=mapauth:1m max_size=10m inactive=60s;

# 内部鉴权端点，直接打后端，不经过前端 dev server
location = /api/map/auth {
    internal;
    proxy_pass http://127.0.0.1:7777;
    proxy_set_header X-Real-IP $remote_addr;

    # 后端本身异常时不能被全局的 proxy_intercept_errors 换成维护页，
    # 否则 auth_request 收到的是一段 HTML，前端拿不到真实的 5xx
    proxy_intercept_errors off;

    proxy_cache mapauth;
    proxy_cache_key "$cookie_whs_map";
    # 通过的结果缓存 60 秒，一个用户再怎么拖地图，一分钟最多回源一次；
    # 失败的只缓存 10 秒，免得刚登录的人被挡太久
    proxy_cache_valid 204 60s;
    proxy_cache_valid 401 10s;
    # 同一凭据的并发请求只放一个回源，其余等结果，避免瞬间打满后端
    proxy_cache_lock on;
    # 等 3 秒还没回来就不再等，直接并发回源，防止一个慢请求拖住整批瓦片
    proxy_cache_lock_timeout 3s;
    # 后端异常时沿用上一次的鉴权结果，避免整页资源一起 5xx
    proxy_cache_use_stale error timeout updating;

    # 子请求必须快进快出，默认 60 秒会让整个页面卡住
    proxy_connect_timeout 1s;
    proxy_read_timeout 5s;
}

location /map3d/ {
    auth_request /api/map/auth;
    proxy_pass http://127.0.0.1:8100/;

    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # 在线玩家是轮询 players.json，关掉缓冲减少到达延迟
    proxy_buffering off;
    proxy_read_timeout 3600s;

    # BlueMap 自带禁止被 iframe 引用的响应头，不去掉会白屏
    proxy_hide_header X-Frame-Options;
    proxy_hide_header Content-Security-Policy;

    # 全局开了 proxy_intercept_errors，这里要关掉，
    # 否则 BlueMap 的 502 会被替换成维护页，前端拿不到真实状态
    proxy_intercept_errors off;
}

# 地图接口同样要绕开全局的 proxy_intercept_errors，
# 否则 BlueMap 没部署时前端拿到的是维护页，而不是 map_not_ready
location /api/map/ {
    proxy_pass http://127.0.0.1:7777;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_intercept_errors off;
}
```

  6. `data/config.json` 的 `map` 段：`bluemap_base` 填 `http://127.0.0.1:8100`，后端拉 settings 和玩家数用；`bluemap_viewer` 填 `/map3d/`，这是浏览器入口，必须是同源路径；`maps` 填真实地图 id，默认 `world`；`start_y` 是地图出生点的地表高度，地图页固定 3D，会在此基础上抬 20 格；站点是 HTTPS，`cookie_secure` 直接设 `true`。
  7. 改完配置重启后端生效。访问权限卡在 permission ≥ 2，代码里已经处理。


---

## 14. CI（GitHub Actions）

仓库使用 GitHub Actions 做四层自动校验：

- 工作流：`.github/workflows/ci.yml`
- 校验脚本：`.github/scripts/{backend_smoke,data_smoke,mcdr_check}.py`（与 CI 同一套逻辑，可本地直接运行）

### 14.1 触发条件

- 向**任意分支** push；
- 向 `main` 提交或更新 PR；
- 在 Actions 页面手动触发（`workflow_dispatch`）。

同一分支 / PR 的新推送会自动取消上一次仍在运行的 CI。CI 只有只读权限（`contents: read`），不读取任何 Secret，不发布、不部署任何产物。

### 14.2 运行环境

| 项 | 值 |
|----|----|
| Runner | `ubuntu-24.04`（固定版本，避开 `ubuntu-latest` 镜像迁移期的环境差异） |
| Python | 3.14（后端 / 数据层 / MCDR 三个任务） |
| Node.js | 22（满足 Vite 8 engines 要求：Node 20.19+ 或 22.12+） |
| 权限 / 密钥 | 只读 / 不需要 |

### 14.3 四个检查任务

| 检查名称 | 校验内容 | 本地对应命令 |
|----------|----------|--------------|
| `前端 · 依赖安装与生产构建` | `npm ci`（严格按 `package-lock.json`）→ `vite build` → 校验 `dist/index.html` 与 JS 产物 | `cd whs && npm ci && npm run build` |
| `后端 · 启动与接口冒烟` | 全仓 Python 语法编译 → 真实启动 uvicorn（含 lifespan、6 个数据库连接、MCDR WS 命令服务）→ 检查 `/`、`/api/whs`、未登录 401、维基页面 / 搜索、工程接口离线 / 未登录行为、未知路由 404、错误方法 405 → WS `ping` 与未知指令 → 日志无 Traceback | `python .github/scripts/backend_smoke.py` |
| `数据层 · 建库与增删查冒烟` | 考试 YAML 解析（合法 / 非法用例）、`§` 颜色代码剥离、五个 SQLite 库建表与增删查改、维基欢迎页种子与搜索、乐观锁 / 重定向等行为 | `python .github/scripts/data_smoke.py` |
| `MCDR 插件 · 清单 / 导入 / 打包校验` | `mcdreforged pack` 校验插件清单并生成 `.mcdr` → 用最小桩模块替代未入库依赖后导入插件 → 检查命令表、`tick query` / `list` 解析函数、工程桥接（signup 桩：缺失提示 / 创建 / 认领 / 完成 / 更新 / 删除 / 错误码）与打包产物内容 | 先安装 `mcdreforged` + `websockets`，再 `python .github/scripts/mcdr_check.py --packed <pack 输出目录>` |

### 14.4 本地复跑与副作用

```bash
# 前端
cd whs && npm ci && npm run build

# 后端（需先安装 backend/requirements.txt；Windows 本地会跳过「优雅关闭」日志断言）
python .github/scripts/backend_smoke.py

# 数据层（只需要 PyYAML）
python .github/scripts/data_smoke.py

# MCDR 插件（需要 mcdreforged>=2.15 与 websockets；产物 *.mcdr 已被 .gitignore 忽略）
python -m mcdreforged pack -i mcdr_connecter_plugin -o dist-mcdr
python .github/scripts/mcdr_check.py --packed dist-mcdr
```

脚本会自行隔离副作用：数据层脚本先把数据库目录重定向到临时目录；后端脚本使用随机端口启动 uvicorn，并临时改写 `data/config.json` 的 `ws_port`（退出时恢复原内容，原本不存在的文件会删除）。

CI 不覆盖：真实 SMTP / hCaptcha 外部服务、实际 Minecraft 服务器与 MCDR 运行环境、浏览器端 UI / E2E / 视觉回归、生产部署。涉及这些方面的改动仍需人工验证。

> PR 要求、`main` 分支保护规则与前后端可复用代码约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## License

MIT License. Copyright (c) 2026 WangHai Server.
