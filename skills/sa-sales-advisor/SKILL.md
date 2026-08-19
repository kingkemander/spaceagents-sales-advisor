---
name: sa-sales-advisor
description: 统一入口的本地销售 AI 军师。用户首次使用、直接上传客户会议纪要或聊天记录、要求建立客户档案、更新客户画像、学习个人口吻、查询今天跟谁、生成销售作战台或起草客户回复时使用。适用于房产、汽车、写字楼、产业园区及其他长周期顾问式销售；不连接 CRM 或聊天平台。
license: MIT
metadata:
  version: "0.2.0"
  homepage: https://github.com/kingkemander/spaceagents-sales-advisor
  author: SpaceAgents
---

# SA 销售军师

这是插件唯一对外入口。不要要求用户在六个技能之间选择；根据意图自动执行插件内部流程。

插件根目录由 `${CLAUDE_PLUGIN_ROOT}` 表示。运行工具时始终使用完整路径，不假设当前工作目录等于插件目录：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/sa_sales_advisor/cli.py" --help
```

运行时只依赖 Python 标准库，无需用户执行 `pip install`。

## 第一次使用

1. 在当前工作区创建 `SA销售工作区/`，不得扫描工作区外目录：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/sa_sales_advisor/cli.py" init --root "<当前工作区>/SA销售工作区"
```

2. 告诉用户可以直接上传会议纪要、录音转写、聊天记录、截图、PDF、Word 或客户文件，无需先填表。
3. 只有客户归属和新增事实得到用户确认后，才写入正式客户档案。

## 自动路由

按当前请求读取对应内部操作手册；这些文件不是独立 Skill，不向用户展示六个入口：

- 材料上传、Markdown 转换、客户匹配与确认入库：`${CLAUDE_PLUGIN_ROOT}/playbooks/ingest-customer-materials/PLAYBOOK.md`
- 客户画像、当前状态和跟进计划更新：`${CLAUDE_PLUGIN_ROOT}/playbooks/maintain-customer-memory/PLAYBOOK.md`
- 学习或修改销售个人口吻：`${CLAUDE_PLUGIN_ROOT}/playbooks/learn-sales-voice/PLAYBOOK.md`
- 每日跟进排序、提醒和 HTML 作战台：`${CLAUDE_PLUGIN_ROOT}/playbooks/plan-daily-followups/PLAYBOOK.md`
- 根据企业知识、客户画像和个人口吻起草回复：`${CLAUDE_PLUGIN_ROOT}/playbooks/draft-sales-reply/PLAYBOOK.md`

一个请求涉及多个阶段时，按“材料确认入库 → 更新客户记忆 → 规划下一步 → 起草回复”的顺序执行，不让用户重复提供已存在的信息。

## 本地运行入口

所有确定性操作使用同一个 CLI：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/sa_sales_advisor/cli.py" customer create --workspace "<工作区>/SA销售工作区" --name "<客户名>" --owner "<销售>"
python3 "${CLAUDE_PLUGIN_ROOT}/sa_sales_advisor/cli.py" memory update --workspace "<工作区>/SA销售工作区" --customer-id "<客户ID>" --patch-file "<patch.json>"
python3 "${CLAUDE_PLUGIN_ROOT}/sa_sales_advisor/cli.py" dashboard --workspace "<工作区>/SA销售工作区"
python3 "${CLAUDE_PLUGIN_ROOT}/sa_sales_advisor/cli.py" customer validate --workspace "<工作区>/SA销售工作区"
```

不要让用户手工输入上述命令；由智能体根据操作手册执行。

## 固定边界

- 只处理用户直接上传或明确指定的材料。
- 不连接 CRM、微信、企微或其他聊天平台。
- 不自动向客户发送消息。
- 客户归属、事实冲突和正式承诺必须由销售确认。
- 价格、优惠、合同、库存、房源和交付承诺只能引用已确认资料。
- 客户事实、销售判断和 AI 建议分开保存。
- 不修改或删除用户原始材料。

## 完成标准

每次操作都说明：处理了什么、写入哪些相对路径、哪些内容仍待确认、下一步最小行动是什么。生成看板时返回 `SA销售工作区/dashboard/index.html` 的可点击路径。
