# Space Agents 销售军师技能包

面向卖房、卖车、写字楼、产业园区和其他长周期顾问式销售场景的本地客户管理案例。

销售只需上传会议纪要、录音转写、聊天记录、截图或客户文件。技能包会在人工确认后建立客户专属工作区、更新客户画像、生成每日跟进作战台，并结合销售个人口吻起草回复。

## 安装到 Space Agents

### 方式一：GitHub 链接

在 Space Agents 的技能安装页面选择“从 GitHub 安装”，粘贴本仓库地址：

```text
https://github.com/kingkemander/spaceagents-sales-advisor
```

### 方式二：上传 ZIP

在 GitHub Releases 下载 `spaceagents-sales-advisor-v0.1.0.zip`，然后直接上传到 Space Agents 的技能/插件导入页面。

仓库遵循通用 Agent Skills 目录约定：

```text
skills/
  sa-sales-advisor/SKILL.md
  ingest-customer-materials/SKILL.md
  maintain-customer-memory/SKILL.md
  learn-sales-voice/SKILL.md
  plan-daily-followups/SKILL.md
  draft-sales-reply/SKILL.md
```

## 包含能力

- `sa-sales-advisor`：总入口和多技能路由。
- `ingest-customer-materials`：直接接收材料、转换 Markdown、客户匹配与确认入库。
- `maintain-customer-memory`：更新简明客户卡片、当前状态和下一步计划。
- `learn-sales-voice`：从销售本人真实表达中学习个人口吻，生成可修改的 `sales-soul.md`。
- `plan-daily-followups`：生成每日优先级、提醒文字和离线 HTML 销售作战台。
- `draft-sales-reply`：结合企业知识、客户画像和个人口吻生成三种跟进草稿。

## 第一次测试

安装后，建议新建一个测试任务并依次发送：

1. `请初始化 SA 销售军师。`
2. 上传一份脱敏的会议纪要或聊天记录，然后说：`请整理并录入。`
3. 检查客户归属、事实和目标路径，确认无误后说：`确认入库。`
4. `生成今天的销售作战台。`
5. `根据这个客户的画像和我的口吻，给我三种跟进回复。`

正常情况下，当前项目会生成独立的 `SA销售工作区/`，客户资料、索引、画像和 HTML 看板都保存在其中。

## 产品边界

- 不连接 CRM、微信、企微或其他聊天平台。
- 不自动向客户发送消息。
- 不在用户确认前写入正式客户档案。
- 不把 AI 推断当成客户事实。
- 不修改或删除用户上传的来源文件。
- 默认只操作当前项目中的 `SA销售工作区/`。

## 运行要求

- Space Agents 能识别通用 `SKILL.md` 技能包。
- 运行环境提供 Python 3，用于客户索引和 HTML 看板生成。
- 运行环境允许在当前项目目录创建文件。

## 版本

当前版本：`v0.1.0`。这是用于真实场景测试的第一版，建议先使用脱敏客户资料。
