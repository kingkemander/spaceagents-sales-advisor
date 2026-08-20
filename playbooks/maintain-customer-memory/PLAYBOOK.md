---
name: maintain-customer-memory
description: 把销售已确认的新材料和反馈合并进指定客户的动态记忆，维护简洁客户卡片、当前状态、跟进计划和可追溯时间线。用户确认入库内容、报告客户最新消息、成交、失单、暂停、项目进度或要求查看和更新客户画像时使用。
---

# 客户记忆维护

把 `customer.json` 作为机器状态源，把 Markdown 文件作为简洁视图。只合并用户已确认的事实。

## 更新流程

1. 根据 customer_id 读取 `customer.json`、客户卡片、最新状态和最近时间线。
2. 区分新事实、销售判断、AI 建议和冲突信息。
   同时检查 `source_channel`、`company_name`、`job_title`、`industry`、`needs`、`budget`、`timeline` 和 `decision_chain` 是否有新信息；缺失保持为空并进入待确认，不猜测补齐。
3. 向用户展示将要修改的字段；涉及客户状态、成交、失单原因、金额、日期或承诺时必须确认。
4. 将确认后的字段写成 JSON patch 文件，运行：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" memory update --workspace "<工作区>" --customer-id "<ID>" --patch-file "<patch.json>"
```

5. 脚本自动刷新 `customer-card.md`、`current-status.md` 和 `follow-up-plan.md`。
6. 把本次已确认变化追加为新的时间线文件，不覆盖历史记录。
7. 运行 `validate` 检查索引和目录一致性。

## 客户卡原则

- 一屏能读完，优先展示“现在是什么情况”。
- 历史过程放在时间线，不堆进客户卡。
- 已成交客户显示项目进度、下一里程碑和交付风险。
- 未成交客户显示明确原因、证据、是否可重新激活及触发条件。
- 没有依据时写“未确认”，不填心理标签。
- 客户卡、当前状态、跟进计划和销售作战台都是面向销售直接使用的最终页面。只能写确定的业务语言，不得出现 AI、识图、OCR、模型、插件、Skill、入库、文件路径、SHA、置信度、customer.json 或“新建档案”等内部处理措辞。
- 内部识别路径、证据文件和技术日志只保留在 `evidence`、材料索引及日志中，不得拼接到 `latest_update`、`followup_reason`、`next_action`、`risks` 或回复话术。
- 不写“AI 推断”。有充分事实依据的判断改写为销售建议；依据不足的内容放入“待确认”，不作为结论展示。

字段约束见 [references/customer-schema.md](references/customer-schema.md)。展示结构见 [assets/customer-card-template.md](assets/customer-card-template.md)。
