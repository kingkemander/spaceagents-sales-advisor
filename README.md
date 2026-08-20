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

在 GitHub Releases 下载最新的 `spaceagents-sales-advisor-v0.6.1.zip`，然后直接上传到 Space Agents 的技能/插件导入页面。

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
  coach-sales-growth/
bootstrap.py
```

Space Agents 当前只导入 `SKILL.md` 也可以正常使用：首次调用时，入口 Skill 会从固定的 GitHub Release 下载经过 SHA-256 校验的运行时包，安装到当前工作区的 `.spaceagents/plugins/sa-sales-advisor/`。不依赖 `${CLAUDE_PLUGIN_ROOT}`，也不依赖开发者电脑路径。

## 包含能力

- Space Agents 菜单里只显示 `sa-sales-advisor` 一个 Skill。
- 该入口根据用户意图自动读取六个内部 Playbook，不需要用户选择子技能。
- Python 运行包、HTML 模板和规则文件由入口 Skill 在首次调用时自动下载并校验。
- 支持材料入库、客户记忆、个人口吻、每日跟进看板、回复草稿和可选策略参考六类流程。
- 支持直接扫描每个客户的本地材料文件夹；所有图片（包括超长微信截图）先整图调用千问视觉，失败时整图切换 GLM，两个视觉模型都失败才使用跨平台 RapidOCR，不经过聊天附件队列。
- 回复依次参考企业事实、客户事实、全球销售与决策思想、真实相似案例和个人口吻；每次最多匹配两个真正适用的框架，不向客户堆书名或套金句。
- “策略灵感”提供 SPIN Selling、Challenger、Trusted Advisor、Getting to Yes、JOLT、Naval 等方法的可选视角；不设课程、打卡、进度或评分。
- 销售作战台采用克制的 Apple Liquid Glass 视觉语言，玻璃用于功能层，客户内容保持高可读性。

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
- AI 识图使用 Space Agents 已授权网关中的 `SPACEAGENTS_AUTO_API_KEY`，密钥不落盘。OCR 保底依赖由插件按需安装为 Python 包，macOS 与 Windows 均可使用，无需下载数 GB 的本地视觉模型。
- 运行环境允许在当前项目目录创建文件。

## 版本

当前版本：`v0.6.1`。将成长中心重构为可选“策略灵感”，加入全球销售与决策思想库，并移除历史计谋、训练进度、打卡和评分表达。
