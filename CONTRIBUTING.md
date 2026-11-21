# 贡献指南

感谢你愿意为望海服务器官网（WHS Webpage）做贡献。本文档说明代码提交规范、`main` 分支保护规则、PR 要求，以及前端 / 后端 / 数据层 / MCDR 插件中**应当优先复用**的代码，避免重复造轮子。

项目架构、技术栈、目录结构、部署方式见 [README.md](README.md)；本文档只讲「怎么改、怎么提」。

---

## 目录

1. 参与方式
2. 开发环境与本地运行
3. `main` 分支保护与分支模型
4. PR 要求
5. CI（GitHub Actions）
6. 可复用代码
   - 6.1 前端（`whs/`）
   - 6.2 后端（`backend/`）
   - 6.3 数据层（`data/`）
   - 6.4 MCDR 插件（`mcdr_connecter_plugin/`）
   - 6.5 配置读取
7. 代码风格与约定
8. 不要提交的内容
9. 文档、API 与多语言同步
10. 安全注意事项
11. 问题反馈

---

## 1. 参与方式

- **Bug 报告 / 功能建议**：通过仓库的 Issue 模板（`.github/ISSUE_TEMPLATE/`：Bug 报告 / 功能建议）提交，说明现象、复现步骤、期望行为（Bug 报告会自动打 `bug` 标签、功能建议会自动打 `enhancement` 标签）；前端问题附浏览器 / 分辨率 / 中英文环境，后端问题附请求与响应（**不要贴真实 token、密码、密钥、用户隐私数据**）。
- **文档 / 翻译**：可直接提 PR（修改 `README.md`、`CONTRIBUTING.md` 或 `whs/src/locales/*.json`）。
- **代码**：建议先开 Issue 说明方案，确认方向后再动手；较大的功能 / 重构 / 依赖升级请先讨论。
- **安全漏洞**：不要开公开 Issue、不要在 PR 里描述利用细节，请私下联系维护者（见 `.github/CODEOWNERS`）。

贡献范围：前端（Vue 3）、后端（FastAPI）、数据层（SQLite）、MCDR 插件、文档与翻译。

---

## 2. 开发环境与本地运行

环境要求：

- Python **≥ 3.12**（后端；CI 使用 3.14）
- Node.js + npm（Vite 8 要求 `^20.19.0 || >=22.12.0`；CI 使用 22）

最小步骤（详见 README §5）：

```bash
# 后端
cd backend
python -m venv venv
# Windows: venv\Scripts\activate；macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cd ..

# 前端
cd whs
npm install
cd ..

# 一键启动（前端 dev + 后端 --reload，推荐）
python manage.py --dev
```

说明：

- `backend/venv/`、`whs/node_modules/`、`whs/dist/` 均**不入库**，每台机器各自安装。
- `data/config.json`、`data/whs_config.json` 缺失时会自动生成默认值，默认值**不含真实密钥**（邮件验证码 / hCaptcha / 真实服务器状态相关功能需自行配置）；`data/exam.yml` **不会**自动生成，缺席时考试接口返回配置错误，需要从已有环境拷贝或在管理端保存一次试卷（该文件不入库）。
- 数据库、上传目录首次启动自动创建，均被 `.gitignore` 忽略。
- 前端改动请在**桌面宽度 + 手机宽度（约 390px）**都自测一遍；项目对移动端底部弹层、导航栏宽度、弹层 z-index 等有约定（见 6.1）。

---

## 3. `main` 分支保护与分支模型

`main` 分支已通过 **GitHub Ruleset 保护**：

- **禁止直接 push 到 `main`**：所有改动必须从其他分支以 **Pull Request** 形式提交并合并。
- 请勿对 `main` 强制推送（force push）或删除分支。
- PR 的目标分支必须是 `main`；如 Ruleset 要求「分支必须为最新」，请先同步 `main` 再等待合并。
- 合并由维护者完成；贡献者（包括 fork 贡献者）不需要、也没有权限直接合并。
- 从 fork 提交的 PR 会在 PR 上正常运行 CI，不需要任何 Secret。

推荐的分支模型：

```bash
git switch -c feat/wiki-toc        # 功能：feat/xxx
git switch -c fix/message-table    # 修复：fix/xxx
git switch -c docs/contributing    # 文档：docs/xxx
```

- 一个分支 / 一个 PR 聚焦一件事，避免把无关的格式化、重命名、依赖升级混在一起。
- 提交信息（commit message）写清楚「做了什么、为什么」即可；无需强制格式，但避免 `update`、`fix` 这类无语义标题。
- PR 分支被合并后即可删除；未合并前如需 rebase，请确认没有他人正在基于你的分支工作。

---

## 4. PR 要求

### 4.1 必须满足

1. **通过 PR 提交**：目标分支 `main`，不使用直接 push（Ruleset 会拒绝）。
2. **CI 全绿**：PR 上 4 个检查必须通过（见第 5 节）：
   - `前端 · 依赖安装与生产构建`
   - `后端 · 启动与接口冒烟`
   - `数据层 · 建库与增删查冒烟`
   - `MCDR 插件 · 清单 / 导入 / 打包校验`
3. **描述完整**：按 4.2 模板填写；UI 改动附截图（桌面 + 手机），行为改动写清验证步骤。
4. **同步文档**：改动涉及 API、WebSocket 协议、数据表、配置项、部署方式时，同步更新 README 对应章节（见第 9 节）。
5. **多语言**：用户可见文案必须同时更新 `whs/src/locales/zh.json` 与 `en.json`；后端错误码必须同时提供 `zh` / `en` 文案。
6. **不包含敏感信息与运行时文件**：见第 8 节。
7. **遵守现有架构**：优先复用第 6 节的代码，不要引入与现有实现重复的组件 / 工具函数 / 数据库连接方式。

### 4.2 PR 描述模板

新建 PR 时会自动加载 `.github/PULL_REQUEST_TEMPLATE.md`；模板字段与下方一致，请按实际改动填写（无关项可留空或删除）：

```markdown
## 变更内容
<!-- 一两句话说明改了什么、为什么改 -->

## 变更类型
- [ ] 前端（whs/）
- [ ] 后端（backend/）
- [ ] 数据层（data/）
- [ ] MCDR 插件（mcdr_connecter_plugin/）
- [ ] 文档 / 其他

## 关联 Issue
Closes #<issue 编号>

## 验证方式
- [ ] `cd whs && npm ci && npm run build`
- [ ] `python .github/scripts/backend_smoke.py`
- [ ] `python .github/scripts/data_smoke.py`
- [ ] `python .github/scripts/mcdr_check.py`
- [ ] 手动验证：<步骤 / 页面 / 接口>

## 截图或录屏（UI 改动必填）
<!-- 桌面宽度 + 手机宽度；深色 / 浅色主题如有变化也请附上 -->

## 影响范围与兼容性
- 是否修改 API / 数据表 / 配置项：<是 / 否；如是请说明>
- 是否需要迁移数据、重启服务或更新部署配置：
```

### 4.3 审核与合并

- `.github/CODEOWNERS` 中登记的负责人会被自动请求审核；
- 审核意见请以**追加提交**方式解决（不要 force push 覆盖审核上下文）；
- 合并方式（merge / squash / rebase）由维护者决定；若使用 squash，PR 标题会成为最终提交信息，请写清楚；
- 草稿 PR（Draft）可以提前跑 CI，但请转 Ready 后再请求审核。

### 4.4 提交前自检清单

- [ ] 分支基于最新 `main`，冲突已解决
- [ ] 只包含本次改动，没有混入无关文件（`git status` 检查）
- [ ] 前端改动：`npm ci && npm run build` 通过，桌面 + 手机自测
- [ ] 后端改动：本地 `python manage.py --dev` 实际调用过相关接口
- [ ] 数据层 / MCDR 改动：对应 CI 脚本本地跑通
- [ ] 新增 / 修改的文案已同步中英文
- [ ] 新增 / 修改的 API、数据表、配置项已同步 README
- [ ] 未提交密钥、数据库、上传文件、构建产物、日志
- [ ] 没有遗留调试代码（临时 `print`、测试数据、TODO 请处理或注明）

---

## 5. CI（GitHub Actions）

CI 配置：`.github/workflows/ci.yml`；本地复跑与各任务细节见 README §14。触发时机：

- 向任意分支 push；
- 向 `main` 的 PR；
- Actions 页面手动触发。

常用本地命令：

```bash
cd whs && npm ci && npm run build                      # 前端
python .github/scripts/backend_smoke.py                 # 后端（需 backend 依赖）
python .github/scripts/data_smoke.py                    # 数据层（只需 PyYAML）
python .github/scripts/mcdr_check.py                    # MCDR（需 mcdreforged + websockets）
```

脚本会自行隔离副作用（数据层使用临时数据库目录；后端使用随机端口、结束后恢复 `data/config.json`），可安全重复运行。

CI **不覆盖**：真实 SMTP / hCaptcha、真实 Minecraft 服务器、浏览器端 E2E / 视觉回归、生产部署。这些部分需要人工验证，并在 PR 中写明验证方式。

---

## 6. 可复用代码

> 原则：**先搜索、再复用**。新增功能前先看现有实现，避免重复组件、重复请求逻辑、重复数据库连接代码。修改共享代码前先全局搜索引用，避免影响其他页面 / 接口。

### 6.1 前端（`whs/`）

#### 6.1.1 组合式函数（`whs/src/composables/`）

| 文件 | 提供 | 说明 / 用法 |
|------|------|-------------|
| `useAuth.js` | `useAuth()` → `{ state, setAuth, updateUser, clearAuth, isLoggedIn, fetchMe }` | 模块级单例登录态，`token` / `user` 持久化到 localStorage；`App.vue` 启动时调用一次 `fetchMe()`。请求头使用 `Authorization: Bearer ${state.token}` |
| `useLanguage.js` | `{ t, tm, locale, switchLanguage }` | 界面文案与语言切换；语言持久化到 localStorage `lang` |
| `useSiteConfig.js` | `useSiteConfig()`（响应式配置）、`ensureSiteConfig()`（路由守卫等非组件场景） | `/api/whs` 站点公开配置（title_suffix / hcaptcha_site_key / 301），模块级单例、只请求一次 |
| `useTips.js` | `{ showTip, dismiss }` | 全局轻提示：`showTip(type, 文本)`，type 取 `info` / `warning` / `error`；由全局 `tips.vue` 渲染 |
| `useDialogBox.js` | `{ confirm, alert }` | Promise 版确认 / 提示框，**替代 `window.confirm` / `window.alert`**；由全局 `dialog_box.vue` 渲染 |
| `useHcaptchaSiteKey.js` | `siteKey` ref | hCaptcha 公钥（来自 `/api/whs`），不要在前端硬编码 |
| `useEmailCode.js` | `EMAIL_RE`、`useEmailCode()` → `{ sending, cooldown, send, stopCooldown }` | 邮箱验证码发送统一封装：邮箱校验 / 人机验证要求 / 60s 冷却 / 提示 / 成功后重置人机验证；所有发码处（注册、登录、找回密码、改密码、注销、改邮箱）必须使用本模块，不要各组件重复实现 |
| `usePasswordStrength.js` | `PASSWORD_ALLOWED_RE`、`analyzePassword`、`hasSpecialCharacter`、`estimatePasswordEntropy`、`getPasswordStrengthLevel`、`usePasswordStrength(password)` → `{ touched, rules, hardRules, level, percent, touch }` | 密码强度：三条硬性要求（≥8 位 / 数字 / 大小写）+ 一条“特殊字符（可选）”检查项；等级只在三条硬性要求全部满足后按字符池熵估算（特殊字符计入 33 字符池）给出低 / 中 / 高；未失焦前未满足项为灰色，调用 `touch()` 后硬性未满足项标红，可选特殊字符项永不标红；提交用 `hardRules` 判断 |
| `sha256.js` | `sha256(text)` | 纯 JS SHA-256（HTTP 环境也可用）；密码在前端哈希后再传后端 |
| `clipboard.js` | `copyText(text)` | 复制到剪贴板（Clipboard API 不可用时回退 textarea） |
| `wiki/api.js` | `wikiApi`、`WikiApiError` | 维基 API 封装：自动附 token、自动带 `lang`，异常统一带 `code` |
| `wiki/locale.js` | `useWikiLocale()` → `{ lang }` | 维基内容语言（跟随全局 i18n），内容接口按 `lang` 实时请求 |
| `wiki/markdown.js` | `wikiMarkdown.render(content)` → `{ html, outline }`、`buildOutlineTree(items)` | 维基 Markdown 兼容层：`wikiMarkdown` 即统一 `siteMarkdown`，只额外保留目录树组装函数 |
| `markdown/renderer.js` | `siteMarkdown`、`renderMarkdown(content, locale)`、`resolveMarkdownContent`、`displayLanguage`、`COPY_ICON` / `CHECK_ICON` | 全站唯一 Markdown 渲染管线：`§` 颜色、LaTeX、mermaid、代码块占位、媒体、标题 id / 目录、外链；**不要在组件里再 `new MarkdownIt(...)`** |
| `markdown/insert.js` | `useMarkdownInsert(textRef, taRef, hooks)`、`buildMediaMarkdown(url, type)` | 语法提示插入 / 包裹选区 / 插入表格 / 链接 / 图片 / `§` 颜色；编辑器与维基编辑器共用（维基通过 hooks 接撤销栈） |
| `markdown/upload.js` | `uploadMarkdownFile(file)`、`MARKDOWN_UPLOAD_ACCEPT`、`MARKDOWN_UPLOAD_LIMITS`、`mediaKindOf` | 通用 Markdown 编辑器上传（`/api/markdown/upload`）；类型 / 大小常量与后端、维基保持一致 |
| `markdown/colorCodes.js` | `colorCodesPlugin(md)`、`MC_COLORS` | 全站 `§` 颜色 / 格式代码插件；只由统一渲染管线注册，不要单独组合到自建实例 |

#### 6.1.2 Markdown 与颜色代码

- **渲染**：一律使用 `components/markdown_view.vue`（内部走 `markdown/renderer.js`）。它负责 `§` 颜色、LaTeX（KaTeX）、mermaid、代码块语法高亮、媒体、标题 id / 目录、外链与复制按钮。**不要在任何组件里再 `new MarkdownIt(...)`**，也不要另写渲染 HTML 的管线；`html: true` 一律禁止（存储型 XSS）。
- **编辑器**：一律使用 `components/markdown_editer.vue`（编辑 / 预览标签页、语法工具条、上传 / 粘贴 / 拖拽、代码块语言栏与复制、mermaid 复制）。属性：`modelValue`、`multilingual`（默认 `false`；传 `true` 时 v-model 为 `{zh,en}` 对象）、`lang`（受控编辑语言，配合 `showLangSwitch=false` 由外层统一切换）、`placeholder`、`minHeight`、`disabled`、`ariaLabel`；`ref.focus()` 可聚焦输入框。新增 Markdown 输入位置时不要再用裸 `<textarea>` 自己拼预览。
- **上传**：编辑器媒体走 `markdown/upload.js` → `POST /api/markdown/upload`，文件存 `data/markdown_upload/`；类型 / 大小与维基相同（图片 5MB / 视频 50MB / 音频 20MB），后端规则集中在 `backend/api/media_upload.py`。
- **维基**：正文渲染用 `wiki_markdown.vue`（内部就是 `markdown_view.vue`，只额外提供 `.wiki-md` 排版与 `outline` 事件）；维基编辑器保留自己的双栏 / 保存 / 撤销逻辑，但语法插入复用 `markdown/insert.js`，上传片段复用 `buildMediaMarkdown()`，不要复制一套。
- **样式**：统一正文样式在 `whs/src/style.css` 的 `.md-body`（标题、表格、代码块、公式 / mermaid 容器、高亮配色、复制按钮）；维基排版在 `wiki_markdown.vue` 的 scoped `.wiki-md` 中覆盖。新增 Markdown 位置直接套用这两种，不要另写一套排版。
- `§` 语法：`§0`–`§f`、`§#RRGGBB`、`§l/§o/§n/§m`、`§r`；颜色代码会重置格式（与 MC 语义一致），纯文本场景（标题 / 摘要 / 搜索片段）用后端 `strip_mc_color_codes` 剥离。修改语法时需同时改前端 `colorCodes.js` 与后端 `data/main/database/text_utils.py`。

#### 6.1.3 全局组件与组件目录（`whs/src/components/`）

- `tips.vue` / `dialog_box.vue` 在 `App.vue` 全局挂载，**不要**在页面里再实现 toast / confirm。
- 导航与公共：`top_navbar`（导航、用户下拉、消息悬浮按钮）、`page_footer`、`global_search`、`user_dropdown`、`tabs`、`status_dropdown`、`hcaptcha_box`。
- **hCaptcha 统一使用 `hcaptcha_box.vue`**：它负责跨域 iframe 的宽度适配（够宽居中、更窄等比缩放）并提供 `reset()`（`ref.reset()`）；新增人机验证时不要再直接使用 `@hcaptcha/vue3-hcaptcha`，也不要再写 `iframe { width: 100% }`。
- 账号：`login` / `register` / `forgot_password` / `full_user_info` / `username_suggestion` / `change_password` / `cancel_account` / `user_settings` / `manage_accounts` / `user_profile` / `basic_user_info` / `follow_list` / `player_info`。
- Markdown：`markdown_editer`（通用编辑器，所有 Markdown 输入统一使用）、`markdown_view`（统一渲染 + KaTeX / mermaid / 高亮增强 + 复制按钮）。两者是 Markdown 功能的唯一入口，不要在页面里重复实现。
- 消息：`message_box`（消息中心 + 发布 / 编辑，正文用 `markdown_editer`，标题 / 正文均为双语对象）、`message_detail`（Markdown 详情，用 `markdown_view`，标题按站点语言解析）。
- 反馈：`feedback_editor`（新建 / 编辑，正文用 `markdown_editer`）；反馈详情页的评论回复同样使用 `markdown_editer`，评论内容用 `markdown_view` 渲染。
- 考试：`exam_question`（答题 / 附件上传）、`exam_editor`（管理端编辑；试卷说明用 `markdown_editer`）、`doc_viewer`（DOCX 文档渲染）。
- 维基：`wiki_markdown` / `wiki_outline` / `wiki_outline_node` / `wiki_search` / `wiki_page_404`。
- 管理：`admin_settings` / `admin_user_panel` / `joinus_tips`。

新页面优先组合现有组件（导航 / 页脚 / tabs / 提示 / 对话框 / 编辑器）；复制已有组件前先考虑改为复用或扩展 props。

#### 6.1.4 样式与主题

- `whs/src/style.css` 定义主题 CSS 变量（`--bg-color`、`--card-color`、`--text-color`、`--links-color`、`--notice-color`、`--float-bg` 及 `*-rgb` 版本），深色模式由 `html.dark` 与系统 `prefers-color-scheme` 共同控制。
- **不要硬编码颜色**，使用现有变量以保证深 / 浅色主题一致；新增变量需同时补齐 `:root`、`html.dark` 与 `prefers-color-scheme` 三处。
- Markdown 正文样式统一在 `style.css` 的 `.md-body`（含代码块 / 语言栏 / 复制按钮 / 公式 / mermaid / 高亮配色），维基在 `wiki_markdown.vue` 的 `.wiki-md` 覆盖；新增 Markdown 展示位置不要再复制一套排版。
- 管理端悬浮框（`admin_settings.vue`）约定为单滚动容器：`.panel` 自身滚动，`.panel-body` 不参与拉伸（内容少时高度跟随内容，内容超高才滚动），头部与翻页栏随内容滚动、不吸顶、不叠加背景色；打开时锁定背景页面滚动。手机端在表格等横向滚动容器内的纵向滑动由 `onOverlayTouchMove` 转发给主对话框，横向滑动保留给容器自身；新增弹窗不要恢复成 `.panel` + `.panel-body` 双层滚动。
- 移动端约定：底部弹层使用 20px 顶部圆角、`min-height: 20vh` / `max-height: 80vh` 或类似范围、`overscroll-behavior: contain`；弹层层级参考现有 z-index（消息层 3000、发布层 9500、悬浮按钮 2500）。
- 动画优先使用已有 `.load-in` 等类，并尊重 `prefers-reduced-motion`。

#### 6.1.5 国际化（i18n）

- 界面文案全部通过 `useLanguage()` / `useI18n()` 的 `t()` 获取，新增 key 同时写入 `whs/src/locales/zh.json` 与 `en.json`。
- 页面标题使用路由 `meta.titleKey`（`App.vue` 统一设置 document.title）。
- 后端返回的错误响应是 `{ code, message: { zh, en } }`：按 `code` 分支处理，展示时按当前语言取 `message`（参考 `useAuth.fetchMe` 与 `wiki/api.js` 的 `localMessage`）。

#### 6.1.6 前端 API 调用约定

- 统一使用 `fetch('/api/...')`（dev / preview 由 Vite 代理到 `127.0.0.1:7777`）。
- 需要登录的请求带 `Authorization: Bearer <token>`；token 来源是 `useAuth().state.token`（`localStorage` 中的 `token`）。
- 非 2xx 响应中读取 `data.code` / `data.message`，不要只提示 `HTTP 500`。
- 目前多个组件内各自定义了 `authHeaders()`（未抽公共工具）；新代码可沿用现有写法，若要统一抽取请单独开 PR 讨论。

### 6.2 后端（`backend/`）

#### 6.2.1 可复用的安全 / 认证 / 响应工具（`backend/main.py`）

| 名称 | 用途 |
|------|------|
| `create_token(uid, ttl)` / `verify_token(token)` | HMAC-SHA256 自签 token（默认 7 天），无需第三方 JWT 库 |
| `_hash_password(client_hash)` / `_verify_password(stored, client_hash)` | 前端 SHA-256 结果 + 随机盐后存储 / 校验 |
| `get_current_user(authorization=Header(None))` | FastAPI 依赖：解析 token → 用户 dict 或 `None`；账号封禁 / 锁定抛 `UserNotActiveError` → 403 |
| `check_user_active(user)` | 返回 `account_banned` / `account_locked` / `None` |
| `_public_user(user)` | 去掉 `password` 等敏感字段 |
| `_error_response(code, status)` | 生成统一错误响应 `{ code, message: { zh, en } }` |
| `ERROR_MESSAGES` / `ERROR_STATUS` | 错误码 → 双语文案 / HTTP 状态码；新增错误码必须同时登记这两张表 |
| `UserNotActiveError` | 封禁 / 锁定账号的专用异常（全局 handler 统一翻译） |
| `_send_email(to, subject, body, locale)` | 通过 SMTP 发送邮件，失败返回 `False`（不抛异常） |
| `_verify_hcaptcha(response)` | 服务端校验 hCaptcha（`async` 版本） |
| `ws_request_sync(command, data, timeout)` | 后端 → MCDR 插件（WS）的同步请求封装，失败返回 `{success: False}` |
| `fetch_online_players()` / `is_player_online(player)` / `get_whitelist()` | 在线名单 / 在线判断 / 白名单查询（经 MCDR） |
| `add_player_whitelist()` / `remove_player_whitelist()` / `remove_user_whitelist()` | 白名单增删（含幂等处理与结果封装） |
| `_load_exam()` / `_grade_exam_question()` / `_exam_question_public()` | 试卷加载、自动判分、题目对外结构（不泄露答案） |
| `_apply_exam_pass()` / `_notify_exam_passed()` | 考试通过后的权限升级 / 白名单写入 / 消息与邮件通知 |
| `_attach_message_author(msg)` | 把消息的 `author_uid` 解析为作者名称 |

> 说明：以 `_` 开头表示「后端内部复用」，路由模块通过 `from main import (...)` 使用（现有代码如此）；对外可复用的公共函数请写清 docstring 并尽量使用明确名称。

#### 6.2.2 路由层约定（`backend/api/`）

- 每个业务一个文件，使用 `APIRouter`；路由模块通过 `from main import (...)` 复用组合根中的数据库实例与工具函数。`backend/main.py` 在文件**末尾**导入并 `app.include_router(...)` 注册（放在末尾是为了避免循环导入），新增路由文件必须在这里注册。
- 路由注册顺序敏感：静态段路由必须写在动态参数路由之前（如 `/api/user/me`、`/api/user/username_exists` 要先于 `/api/user/{uid}`；维基的 `/page/{slug:path}/history` 要先于 `/page/{slug:path}`）。
- 需要登录的接口统一 `user: dict | None = Depends(get_current_user)`；未登录返回 `_error_response("unauthorized", 401)`。
- 成功响应直接返回 dict；错误响应统一 `_error_response(code, status)`，不要返回裸字符串或自定义结构。
- 分页参数统一 `page` / `page_size`（上限 100；反馈接口 50），缺省 1 / 10。
- 请求体参数优先用函数参数 / `Body(...)` + 手动校验（与现有代码一致），错误码写入 `ERROR_MESSAGES` / `ERROR_STATUS`。
- **玩家名统一使用 `main.MC_NAME_RE`**（Minecraft Java 官方：`^[A-Za-z0-9_]{3,16}$`）：考试问卷、主账号、小号等所有写入玩家名的入口都必须用它校验，不要再用不限长度的 `USERNAME_RE`；考试结束后（通过 / 次数用完）玩家名锁定（`exam_profile_locked`）。

#### 6.2.3 权限模型

| permission | 角色 |
|-----------|------|
| 0 | guest |
| 1 | user |
| 2 | player（考试通过后自动升级，可编辑低权限维基页） |
| 3 | admin |
| 4 | owner |

- 管理接口通常要求 `(user.get("permission") or 0) >= 3`；维基编辑另受页面 `min_permission` 限制（2 / 3 / 4）。
- 不能封禁 / 修改权限高于或等于自己的用户；不能修改自己的权限；不能封禁自己（错误码见 `ERROR_MESSAGES`）。

#### 6.2.4 WebSocket（后端 ↔ MCDR）

- `backend/ws_server.py` 的 `WsCommandServer`：`register("命令名")` 注册 `async handler(data) -> Any`，`start()` / `stop()` 由 FastAPI lifespan 管理，服务端主动请求用 `await ws_server.request(...)`（同步上下文用 `main.ws_request_sync`）。
- 协议：请求 `{request_id, command, data}`，响应 `{request_id, success, data}`；新增指令需**前后端 + MCDR 插件同时改**，并更新 README §7。

#### 6.2.5 媒体上传（`backend/api/media_upload.py`）

- 白名单、大小限制（图片 5MB / 视频 50MB / 音频 20MB）、流式读取、随机 UUID 文件名、读取时文件名校验与 MIME 推断统一在 `media_upload.py`；`wiki.py`（`data/wiki_upload/`，permission≥2）与 `markdown.py`（`data/markdown_upload/`，登录即可）都复用它。
- 新增上传接口时**不要复制常量或另写落盘逻辑**；路由只需指定目录、权限与错误码前缀。
- 错误码统一为 `*_upload_unsupported`（400）/ `*_upload_too_large`（413）/ `*_upload_not_found`（404），新增错误码必须同时登记 `ERROR_MESSAGES` / `ERROR_STATUS`。
- 上传只校验声明的类型 / 大小与扩展名，**不校验文件真实内容**（与现有头像 / 维基上传一致）。

#### 6.2.6 消息双语（系统消息 + 定向消息）

- `messages` 表：`title` / `content` 为中文（主语言），`title_en` / `content_en` 为英文；旧库启动时自动补列，旧消息英文为空、展示时回退中文。
- API 响应由 `backend/api/message.py` 的 `_serialize_message()` 统一输出 `{zh, en}` 对象；发布 / 编辑接受 `{title:{zh,en}, content:{zh,en}}`，同时兼容旧版字符串（按中文处理）。
- 校验：每个语言标题 ≤100、正文 ≤20000 字符；至少一种语言非空，错误码沿用 `message_title_empty` / `message_content_empty`。
- **新增定向消息**（考试通知等）必须同时提供中英文：`message_db.create_message(..., title_en=..., content_en=...)`，不要只写中文；前端展示统一用 `resolveMarkdownContent(value, locale)` 做语言回退。
- 管理端编辑器使用 `MarkdownEditer` 的 `multilingual` + 受控 `lang` + `:show-lang-switch="false"`，由外层语言切换同时控制标题输入与正文编辑器。

### 6.3 数据层（`data/`）

#### 6.3.1 基类与连接模型

- `data/main/database/basic_database.py`：
  - `BasicDatabase`：数据库路径规范化（统一锚定 `data/database/`）、连接生命周期、线程安全包装、`exists` / `clear` / `__len__` / 上下文管理器等默认实现；
  - `_LockedConnection` / `_LockedCursor`：连接级 `RLock` + `cached_statements=0`，供 FastAPI 线程池并发访问；
  - 抽象方法：`connect` / `close` / `create_table` / `drop_table` / `list_tables` / `get` / `set` / `delete` / `keys`。
- 新增数据库类：继承 `UserDatabase`（可复用连接 / 迁移 / 用户辅助逻辑）或 `BasicDatabase`；实现 `connect()`（先 `super().connect()` → 建表 → 补列迁移）与 `close()`（先提交关闭 → `super().close()`）。
- **不要**自己 `sqlite3.connect(...)`、不要传自定义目录（路径会被规范化到 `data/database/`；测试场景请参考 CI 脚本重定向 `DATABASE_DIR`）。
- 所有 SQL 使用参数化查询；表名 / 列名拼接前必须用现有 `_validate_identifier` 校验。

#### 6.3.2 已有数据库类

| 类 | 文件 | 表 |
|----|------|----|
| `UserDatabase` | `user_database.py` | `users`（+ 迁移） |
| `UserInfoDatabase` | `user_database.py` | `user_info`（与 users 共用一个 `.db` 文件） |
| `MessageDatabase` | `message_database.py` | `messages` |
| `ExamDatabase` | `exam_database.py` | `exam_answers` / `exam_profiles` |
| `WikiDatabase` | `wiki_database.py` | `pages` / `revisions` / `redirects` / `wiki_fts`（FTS5，不可用时自动回退 LIKE） |
| `FeedbackDatabase` | `feedback_database.py` | `feedback` / `feedback_comments` |

错误约定：数据层抛带稳定 `code` 的异常（如 `UserDatabaseError`、`WikiDatabaseError`、`FeedbackDatabaseError` 子类），由 `backend/main.py` 的全局异常处理转换为 HTTP 响应；新增错误码需同步 `ERROR_MESSAGES` / `ERROR_STATUS`。

#### 6.3.3 可复用工具

| 名称 | 位置 | 用途 |
|------|------|------|
| `read_config()` / `read_whs_config()` / `create_default_config()` | `data/__init__.py` | 读取 / 生成配置文件（缺失时写默认值） |
| `parse_exam_yaml()` / `validate_exam_dict()` / `load_exam_config()` / `save_exam_config()` | `data/exam.py` | 试卷 YAML 解析、校验、读写 |
| `fill_blank_blanks()` | `data/exam.py` | 填空题答案规范化（单空 / 多空） |
| `strip_mc_color_codes()` | `data/main/database/text_utils.py` | 剥离 MC `§` 颜色 / 格式代码（标题、摘要、搜索片段） |

### 6.4 MCDR 插件（`mcdr_connecter_plugin/`）

- 元数据：`mcdreforged.plugin.json` 与 `mcdr2web/__init__.py` 中的 `PLUGIN_METADATA` **必须保持一致**（CI 会逐字段校验）。
- 可复用组件：
  - `command_handlers`：`命令名 -> async handler(data)` 注册表，后端发来的 `command` 在此分发；
  - `send_message()` / `request_async()` / `request_sync()`：插件 → 后端的消息发送与请求（同步版供聊天命令使用）；
  - `parse_tick_query_output()` / `parse_list_output()`：RCON `tick query` / `list` 输出解析（纯函数，CI 有测试）；
  - `DEFAULT_CONFIG` + `server.load_config_simple()`：配置读取与默认值；
  - `on_load` / `on_unload` + `_mcdr_event_loop()`：常驻协程调度与卸载清理。
- 新增指令：同时修改插件 `command_handlers`、后端 `ws_server.register(...)`，并更新 README §7；`whitelist_api` / `online_player_api` 不在版本库中，CI 用桩模块替代，真实联调需自行准备。
- 本地无 MCDR 环境时可用（未入库的）`pseudo_mcdr/pseudo_mcdr.py` 作为 WS 客户端替身。

### 6.5 配置读取

- 私密配置 `data/config.json`、公开配置 `data/whs_config.json` 均由 `data/__init__.py` 的默认值生成，**都不入库**。
- 新增配置项：在 `data/__init__.py` 的默认配置函数中补默认值，并更新 README §5.2 的字段表；读取时使用 `read_config()` / `read_whs_config()`，不要直接 `open()`。
- 不得在代码中硬编码真实密钥 / 密码 / token；`token_secret` 必须为强随机值。

---

## 7. 代码风格与约定

- **前端**：Vue 3 `<script setup>` + Composition API；文件与组件命名沿用现有 `snake_case`（如 `message_box.vue`）；缩进 2 空格、不加分号（与现有文件一致）；样式优先使用现有 CSS 变量与类名。
- **后端**：PEP 8、4 空格缩进、类型注解与中文 docstring（与现有代码一致）；路由函数默认同步（FastAPI 线程池），仅在需要异步 IO 时使用 `async def`。
- **数据层**：手写参数化 SQL（无 ORM）；连接 / 迁移逻辑复用基类；错误码集中在异常类与 `main.py` 的错误码表。
- **注释**：解释「为什么」而不是「是什么」；不要提交调试输出、临时测试数据、被注释掉的大段代码。
- **依赖**：后端追加依赖写入 `backend/requirements.txt`（保持版本下限风格）；前端仅在后端无现成能力或生态必要的时候新增依赖，并在 PR 中说明理由。Markdown 渲染增强已引入 `highlight.js` / `katex` / `mermaid`（均按需懒加载），新增 Markdown 相关功能优先复用现有管线，不要重复引入同类高亮 / 公式 / 图表库。

---

## 8. 不要提交的内容

以下路径已被 `.gitignore` 忽略，**不要**用 `git add -f` 强行提交：

- `backend/venv/`、`whs/node_modules/`、`whs/dist/`、`__pycache__/`
- `data/config.json`、`data/whs_config.json`、`data/exam.yml`、`data/database/`、`data/avatar/`、`data/exam_image/`、`data/exam_upload/`、`data/wiki_upload/`、`data/markdown_upload/`
- `logs/`、`*.mcdr`、`*.zip`
- `SMTP/`、`pseudo_mcdr/`、`mcdr_connecter_plugin/whitelist_api/`、`mcdr_connecter_plugin/online_player_api/`
- 本地工具 / 截图 / 报告产物目录（不要提交）

提交前用 `git status` / `git diff --stat` 检查是否混入了上述文件或无关改动。

---

## 9. 文档、API 与多语言同步

以下改动必须同步文档（README 对应章节）：

| 改动 | 需要更新 |
|------|----------|
| 新增 / 修改 HTTP 接口 | README §6（含鉴权列、错误码） |
| WebSocket 协议 / MCDR 指令 | README §7、§8 |
| 数据表 / 字段 / 迁移 | README §9 |
| 消息双语结构 / 编辑器多语言 | README §2「Markdown 体系」「消息中心」、§6.6、§9 |
| 配置项 | README §5.2 |
| 上传目录 / 大小限制 | README §10 |
| 部署方式 / 端口 / 依赖 | README §11 |
| 新增 CI 检查或脚本 | README §14 |

多语言约定：

- 前端界面文案：`whs/src/locales/zh.json` + `en.json` 同步新增；
- 后端错误文案：`ERROR_MESSAGES` 中每个错误码同时提供 `zh` / `en`；
- 改动双语文案时请检查对应页面的中英文显示效果。

---

## 10. 安全注意事项

- **不要提交任何真实密钥**（`token_secret`、SMTP 授权码、hCaptcha secret、数据库内容、用户数据）。
- **防 XSS**：Markdown 渲染保持 `html: false`；任何 `v-html` 的内容必须来自受控渲染管线（`markdown-it` / 现有渲染函数），不要直接拼接用户输入。
- **防 SQL 注入**：使用参数化查询；标识符（表名 / 列名）必须通过校验函数。
- **权限校验**：新增接口必须明确鉴权方式（公开 / 登录 / 本人 / permission 门槛），服务端校验不能依赖前端隐藏按钮。
- **输入上限**：文本长度、上传大小 / 类型、分页参数沿用现有上限校验，避免新增无上限接口。
- **日志**：不要在日志里输出密码、token 等敏感信息；验证码目前按现有设计会打印到后端 stdout（见 README §13），新增日志不要扩大敏感信息范围。

---

## 11. 问题反馈

- 功能 / 缺陷：GitHub Issues（请使用仓库提供的 Bug 报告 / 功能建议模板）；
- 安全漏洞：私下联系维护者（`.github/CODEOWNERS` 中的负责人），不要在公开渠道披露利用细节；
- 贡献流程相关建议：欢迎直接提 PR 改进本文档。
