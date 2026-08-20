---
name: sa-sales-advisor
description: 统一入口的本地销售 AI 军师。用户首次使用、上传客户会议纪要或聊天记录、指定本地材料文件夹、批量识别微信长截图、建立客户档案、更新客户画像、学习个人口吻、查询今天跟谁、生成销售作战台或起草客户回复时使用。适用于房产、汽车、写字楼、产业园区及其他长周期顾问式销售；不连接 CRM 或聊天平台。首次调用时自动从固定 GitHub Release 下载并校验运行时。
---

# SA 销售军师

仅向用户提供一个入口。自动完成运行时准备，再根据意图执行材料入库、客户记忆、口吻学习、每日跟进或回复起草流程。

## 准备运行时

不要使用 `${CLAUDE_PLUGIN_ROOT}`，不要引用开发者电脑路径，也不要要求用户手工复制插件文件。

以当前 Space Agents 工作区为 `<工作区>`。运行时固定安装到：

```text
<工作区>/.spaceagents/plugins/sa-sales-advisor/runtime-v0.4.0/
```

每次触发时，先检查以下文件是否存在：

```text
<工作区>/.spaceagents/plugins/sa-sales-advisor/runtime-v0.4.0/sa_sales_advisor/cli.py
```

如果不存在，自动执行以下两步。优先使用 `python3`；环境只有 `python` 时替换命令名。

第一步，下载固定版本的引导器并验证 SHA-256。把 `<工作区>` 替换为当前工作区绝对路径：

```bash
python3 -c "import hashlib,pathlib,urllib.request; u='https://raw.githubusercontent.com/kingkemander/spaceagents-sales-advisor/v0.4.0/bootstrap.py'; p=pathlib.Path(r'<工作区>')/'.spaceagents/plugins/sa-sales-advisor/bootstrap-v0.4.0.py'; p.parent.mkdir(parents=True,exist_ok=True); d=urllib.request.urlopen(u,timeout=60).read(); h=hashlib.sha256(d).hexdigest(); assert h=='993b3fdf742f1085c559414ee622614dcb476fe824431600a989e8e313a7a52e', f'bootstrap checksum mismatch: {h}'; p.write_bytes(d); print(p)"
```

第二步，运行引导器。它会下载并校验运行时包，然后返回真实 CLI 路径：

```bash
python3 "<工作区>/.spaceagents/plugins/sa-sales-advisor/bootstrap-v0.4.0.py" --workspace "<工作区>"
```

如果下载、校验或解压失败，停止操作并把原始错误告诉用户；不要绕过校验，不要退回任何本机绝对路径。已安装且校验完整时，引导器是幂等的，不重复下载。

后续使用：

```text
<运行时根目录> = <工作区>/.spaceagents/plugins/sa-sales-advisor/runtime-v0.4.0
<CLI> = <运行时根目录>/sa_sales_advisor/cli.py
<销售数据> = <工作区>/SA销售工作区
```

## 第一次使用

运行：

```bash
python3 "<CLI>" init --root "<销售数据>"
```

告诉用户可以直接上传会议纪要、录音转写、聊天记录、截图、PDF、Word 或客户文件，无需预先填表。只在客户归属和新增事实得到确认后写入正式档案。

## 自动路由

根据当前请求只读取对应内部操作手册，并把其中的 `<运行时根目录>` 替换为上述真实路径：

- 材料上传、Markdown 转换、客户匹配与确认入库：`<运行时根目录>/playbooks/ingest-customer-materials/PLAYBOOK.md`
- 客户画像、当前状态和跟进计划：`<运行时根目录>/playbooks/maintain-customer-memory/PLAYBOOK.md`
- 学习或修改销售个人口吻：`<运行时根目录>/playbooks/learn-sales-voice/PLAYBOOK.md`
- 每日跟进、提醒和 HTML 作战台：`<运行时根目录>/playbooks/plan-daily-followups/PLAYBOOK.md`
- 根据企业知识、客户画像和个人口吻起草回复：`<运行时根目录>/playbooks/draft-sales-reply/PLAYBOOK.md`

一个请求涉及多个阶段时，按“材料确认入库 → 更新客户记忆 → 规划下一步 → 起草回复”的顺序执行，不要求用户选择子技能，不让用户重复提供已有信息。

## 固定边界

- 只处理用户直接上传或明确指定的材料。
- 不连接 CRM、微信、企微或其他聊天平台。
- 不自动向客户发送消息。
- 客户归属、事实冲突和正式承诺必须由销售确认。
- 价格、优惠、合同、库存、房源和交付承诺只能引用已确认资料。
- 客户事实、销售判断和 AI 建议分开保存。
- 不修改或删除用户原始材料。
- 只扫描用户明确指定的当前项目内文件或文件夹；批量图片在后台逐张处理，最后统一确认。

## 完成标准

每次操作说明：处理了什么、写入哪些相对路径、哪些内容仍待确认、下一步最小行动是什么。生成看板时返回 `<销售数据>/dashboard/index.html` 的可点击路径。
