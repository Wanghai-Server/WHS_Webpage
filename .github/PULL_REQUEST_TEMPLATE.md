<!--
感谢贡献！提交前请先阅读 CONTRIBUTING.md：
https://github.com/Wanghai-Server/WHS_Webpage/blob/main/CONTRIBUTING.md

提醒：
- main 分支受 Ruleset 保护，必须通过 PR 合并；
- 合并前 4 个 CI 检查必须全部通过；
- UI 改动请附桌面 + 手机截图；
- 不要提交密钥、数据库、上传文件、构建产物、日志。
-->

## 变更内容

<!-- 一两句话说明改了什么、为什么改。 -->

## 变更类型

- [ ] 前端（whs/）
- [ ] 后端（backend/）
- [ ] 数据层（data/）
- [ ] MCDR 插件（mcdr_connecter_plugin/）
- [ ] 文档 / CI / 其他

## 关联 Issue

Closes #

## 验证方式

- [ ] `cd whs && npm ci && npm run build`
- [ ] `python .github/scripts/backend_smoke.py`
- [ ] `python .github/scripts/data_smoke.py`
- [ ] `python .github/scripts/mcdr_check.py`
- [ ] 手动验证：<!-- 页面 / 接口 / 步骤 -->

## 截图或录屏（UI 改动必填）

<!-- 桌面宽度 + 手机宽度；深色 / 浅色主题如有变化请附上。可直接拖拽图片到此处。 -->

## 影响范围与兼容性

- 是否修改 API / 数据表 / 配置项：
- 是否需要迁移数据、重启服务或更新部署配置：

## 提交前确认

- [ ] 我已阅读 [贡献指南](https://github.com/Wanghai-Server/WHS_Webpage/blob/main/CONTRIBUTING.md)
- [ ] 已同步更新 README 对应章节（API / 数据表 / 配置 / 部署等）
- [ ] 用户可见文案已同步 `whs/src/locales/zh.json` 与 `en.json`
- [ ] 未包含密钥、数据库、上传文件、构建产物、日志
- [ ] 分支基于最新 `main`，没有混入无关改动
