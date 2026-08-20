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
2. 读取材料并为每个文件生成 Markdown 草稿。所有图片（包括超长聊天截图）统一执行“千问视觉 → GLM 视觉 → RapidOCR”的识别链，既提取文字，也理解图表、现场、版式和图片关系；无法辨认处标记“待确认”。
3. 按 [references/extraction-schema.md](references/extraction-schema.md) 提取客户、联系人、需求、预算、周期、决策链、异议、承诺、日期和下一步。
4. 读取 `indexes/customer-index.json`，基于公司全称、别名、联系人和已有项目寻找候选客户。不得只凭简称自动归档。
5. 展示一张入库确认卡：推荐客户、匹配依据、新增事实、冲突、待办、目标路径和不会写入的内容。
6. 未获得明确确认时，把草稿保留为待处理，不更新正式索引和客户文件。
7. 用户选择新客户时，运行 `python3 "<运行时根目录>/sa_sales_advisor/cli.py" customer create` 创建稳定 ID 和目录。
8. 用户确认后，复制原件到 `sources/original/`，保存 Markdown 到 `sources/markdown/`，创建时间线记录，再运行 `register-material` 登记索引和流水。
9. 继续执行 `<运行时根目录>/playbooks/maintain-customer-memory/PLAYBOOK.md`，根据本次已确认事实更新客户状态。
10. 运行 `python3 "<运行时根目录>/sa_sales_advisor/cli.py" customer validate`，确认 customer_id、路径和索引一致。

## 客户文件夹与批量图片

用户明确给出本地图片文件夹，或说多张图片属于同一客户时，不要求逐张上传，也不要逐张询问客户归属。工作区外的明确路径只读，所有识别产物仍写入当前项目的 `SA销售工作区`。

1. 把用户给出的客户名称作为 `customer_hint`。这只是本批次归属提示，正式写入仍需最后统一确认。
2. 使用一条命令完成文件遍历、AI 识图、失败降级、长图切片和 Markdown 合并。输出目录固定使用 `<当前项目>/SA销售工作区/inbox/image-batches`：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" images scan \
  --input "<用户明确指定的图片或文件夹>" \
  --output "<当前项目>/SA销售工作区/inbox/image-batches" \
  --customer-hint "<同一客户名称>"
```

3. 如果返回 `missing_dependency`，自动运行一次以下命令，再重试 `scan`；不要让用户手工安装 Python 图片依赖。依赖使用跨平台 Python 包，适用于 macOS 和 Windows：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" images setup
```

4. `scan` 对每张原图（包括超长聊天截图）执行固定降级链：
   - 首选 `qwen3.7-plus`，通过 `https://token.spaceagents.cn/v1/chat/completions`，把本地图片转为 Base64 data URL 后直接请求；
   - 首选模型失败时自动调用 `glm-5.2`；
   - 两个视觉模型都失败时，才对该图片的切片执行 RapidOCR；
   - 不调用 `analyze-image` 扩展，不把图片复制到聊天附件队列，不要求用户逐张上传。
5. 密钥只能读取 Space Agents 运行环境中的 `SPACEAGENTS_AUTO_API_KEY`，端点可由 `SPACEAGENTS_INFERENCE_URL` 覆盖。不得把密钥写入文件、命令输出、日志或客户档案。
6. 读取返回的 `combined-analysis.md`，再执行正常的客户匹配和事实提取。视觉模型输出中的“图片事实”和“AI 推断”必须分开；推断不得直接写入客户事实。
7. 只展示一张批次确认卡，包含客户归属、图片数量、每张图片采用的识别路径、视觉失败与 OCR 降级情况、新增事实、冲突、聊天式补充问题和待确认项。

切片仅用于两个视觉模型都失败后的 OCR 保底，不替代千问或 GLM 对整张长图的语义理解。不得修改原图。不得因为某张图模糊或某个模型失败而放弃其余图片。若原始像素本身不足，如实标记低质量，并建议用户提供原始截图、较短截图或可复制文本；不要声称图片增强能够恢复不存在的细节。

## 识别后的聊天式补充

完成识别后，先基于现有材料形成“暂定客户画像”，再一次性询问最多 3 个真正影响跟进决策的问题，例如当前成交状态、关键决策人、下一次承诺日期。材料中已经明确的内容不得重复询问。用户回答后：

1. 把回答标记为“销售补充”，与图片事实分开保留来源；
2. 重新生成简明客户卡、当前状态、成交或失单原因、项目进度、风险和下一步；
3. 展示最终确认卡；
4. 只有用户明确确认后，才执行正式归档、更新客户画像和时间线。

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
