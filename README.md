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

在 GitHub Releases 下载最新的 `spaceagents-sales-advisor-v0.4.0.zip`，然后直接上传到 Space Agents 的技能/插件导入页面。

仓库采用“一个插件、一个 Skill 入口、多个内部流程”的结构：

```text
.claude-plugin/
  plugin.json
skills/
  sa-sales-advisor/SKILL.md
sa_sales_advisor/
  cli.py
  init_workspace.py
  ingest_store.py
  memory_store.py
  render_dashboard.py
  templates/dashboard-template.html
playbooks/
  ingest-customer-materials/
  maintain-customer-memory/
  learn-sales-voice/
  plan-daily-followups/
  draft-sales-reply/
bootstrap.py
```

Space Agents 当前只导入 `SKILL.md` 也可以正常使用：首次调用时，入口 Skill 会从固定的 GitHub Release 下载经过 SHA-256 校验的运行时包，安装到当前工作区的 `.spaceagents/plugins/sa-sales-advisor/`。不依赖 `${CLAUDE_PLUGIN_ROOT}`，也不依赖开发者电脑路径。

## 包含能力

- Space Agents 菜单里只显示 `sa-sales-advisor` 一个 Skill。
- 该入口根据用户意图自动读取五个内部 Playbook，不需要用户选择子技能。
- Python 运行包、HTML 模板和规则文件由入口 Skill 在首次调用时自动下载并校验。
- 支持材料入库、客户记忆、个人口吻、每日跟进看板和回复草稿五类流程。
- 支持直接扫描当前项目内的本地图片文件夹；微信长截图会先无损切片和增强，再由 Agent 后台逐张识别，用户无需反复上传。

## 第一次测试

安装后，建议新建一个测试任务并依次发送：

1. `请初始化 SA 销售军师。`
2. 上传一份脱敏的会议纪要或聊天记录，然后说：`请整理并录入。`
3. 检查客户归属、事实和目标路径，确认无误后说：`确认入库。`
4. `生成今天的销售作战台。`
5. `根据这个客户的画像和我的口吻，给我三种跟进回复。`

批量截图测试时，把图片放在当前项目的一个文件夹中，然后说：

```text
扫描“客户材料/某客户聊天截图”文件夹，里面所有图片属于同一个客户。后台批量识别，最后统一让我确认，不要逐张询问。
```

正常情况下，当前项目会生成独立的 `SA销售工作区/`，客户资料、索引、画像和 HTML 看板都保存在其中。

## 产品边界

- 不连接 CRM、微信、企微或其他聊天平台。
- 不自动向客户发送消息。
- 不在用户确认前写入正式客户档案。
- 不把 AI 推断当成客户事实。
- 不修改或删除用户上传的来源文件。
- 默认只操作当前项目中的 `SA销售工作区/`。

## 运行要求

- Space Agents 能安装带 `.claude-plugin/plugin.json` 的 Claude Code 插件。
- 运行环境提供 Python 3，用于客户索引和 HTML 看板生成。
- 运行环境允许在当前项目目录创建文件。

## 版本

当前版本：`v0.4.0`。新增本地文件夹批量截图识别、微信长截图切片、识别队列和统一确认流程；仍只安装一个 Skill，首次调用自动准备完整运行时，后续离线复用已安装文件。
