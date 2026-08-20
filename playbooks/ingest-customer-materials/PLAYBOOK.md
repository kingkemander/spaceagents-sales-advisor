---
name: ingest-customer-materials
description: 接收销售直接上传或明确指定本地文件夹中的录音纪要、聊天记录、长截图、成批图片、PDF、Word、表格和客户文件，自动识别客户并转换为可追溯 Markdown；在销售确认客户归属和待写入内容后，创建或更新客户专属本地工作区。用户说“整理这份资料”“扫描这个文件夹”“批量识别截图”“录入客户”“把这些放进客户档案”或直接上传销售材料时使用。
---

# 客户资料入库

销售只需上传材料。不要在上传前要求填写客户名称、联系人或分类。

## 首次运行

如果 `SA销售工作区/indexes/customer-index.json` 不存在，运行：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" init --root "<当前项目>/SA销售工作区"
```

只在当前项目内初始化，不扫描其他目录。

## 入库流程

1. 列出本次上传文件，计算摘要和 SHA-256；不修改来源文件。
2. 读取材料并为每个文件生成 Markdown 草稿。图片或截图先识别可见文字；无法辨认处标记“待确认”。
3. 按 [references/extraction-schema.md](references/extraction-schema.md) 提取客户、联系人、需求、预算、周期、决策链、异议、承诺、日期和下一步。
4. 读取 `indexes/customer-index.json`，基于公司全称、别名、联系人和已有项目寻找候选客户。不得只凭简称自动归档。
5. 展示一张入库确认卡：推荐客户、匹配依据、新增事实、冲突、待办、目标路径和不会写入的内容。
6. 未获得明确确认时，把草稿保留为待处理，不更新正式索引和客户文件。
7. 用户选择新客户时，运行 `python3 "<运行时根目录>/sa_sales_advisor/cli.py" customer create` 创建稳定 ID 和目录。
8. 用户确认后，复制原件到 `sources/original/`，保存 Markdown 到 `sources/markdown/`，创建时间线记录，再运行 `register-material` 登记索引和流水。
9. 继续执行 `<运行时根目录>/playbooks/maintain-customer-memory/PLAYBOOK.md`，根据本次已确认事实更新客户状态。
10. 运行 `python3 "<运行时根目录>/sa_sales_advisor/cli.py" customer validate`，确认 customer_id、路径和索引一致。

## 本地文件夹与批量长截图

用户明确给出当前项目内的图片文件夹，或说多张图片属于同一客户时，不要求逐张上传，也不要逐张询问客户归属。

1. 把用户给出的客户名称作为 `customer_hint`。这只是本批次归属提示，正式写入仍需最后统一确认。
2. 准备批次。输出目录固定使用 `<当前项目>/SA销售工作区/inbox/image-batches`：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" images prepare \
  --input "<用户明确指定的图片或文件夹>" \
  --output "<当前项目>/SA销售工作区/inbox/image-batches" \
  --customer-hint "<同一客户名称>"
```

3. 如果返回 `missing_dependency`，自动运行一次以下命令，再重试 `prepare`；不要让用户手工安装：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" images setup
```

4. 读取返回的 `manifest.json`。依次处理其中 `status=pending` 的 `tile_file`，把本地切片的绝对路径直接交给当前环境可用的图片理解或 OCR 工具；不要重新粘贴进聊天输入框。每个切片只做忠实转录：保留说话人、时间、正文、文件名、图片或语音占位；不补写看不清的文字，用 `[无法辨认]` 标记。后台逐张处理，不要求用户重复上传或逐张确认。
5. 每张切片识别后，把纯转录保存为临时 UTF-8 文本，再登记：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" images record \
  --manifest "<manifest.json>" \
  --tile-id "<tile_id>" \
  --text-file "<临时转录文本>" \
  --quality "<high|medium|low|unreadable>"
```

6. 全部处理完后合并：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" images finalize --manifest "<manifest.json>"
```

7. 读取 `combined-ocr.md`，再执行正常的客户匹配和事实提取。只展示一张批次确认卡，包含客户归属、图片数量、切片数量、低质量切片、新增事实、冲突与待确认项。

切片用于避免长图在聊天上传或模型输入时被整体缩小。不得修改原图。不得因为某张图模糊而放弃其余图片。若原始像素本身不足，如实标记低质量，并建议用户提供原始截图、较短截图或可复制文本；不要声称图片增强能够恢复不存在的细节。

## 多客户与不确定情况

- 一个文件涉及多个客户：按客户拆分待确认事实，但保留同一个原始来源引用。
- 匹配到多个客户：让用户选择；不得写入。
- 无法识别客户：建议新建临时名称；让用户确认后创建。
- 用户明确声明多张图片属于同一客户：整批沿用该提示，最后只确认一次，不逐张追问。
- 文件重复：提示已有记录，不重复复制和登记。
- 新旧信息冲突：并列展示来源与日期，等待用户选择或标记“待确认”。

## Markdown 头部

每份转换文件必须包含 `source_file`、`source_hash`、`imported_at`、`material_type`、`customer_id`、`confirmation_status` 和 `sensitivity`。

使用 [assets/material-record-template.md](assets/material-record-template.md) 作为结构，不为了语言流畅改变事实含义。

## 用户可见输出

说明已归入哪个客户、创建或修改了哪些文件、发现了哪些新信息、还有什么待确认。给出相对路径。
