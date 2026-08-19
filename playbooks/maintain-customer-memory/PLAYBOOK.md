---
name: maintain-customer-memory
description: 把销售已确认的新材料和反馈合并进指定客户的动态记忆，维护简洁客户卡片、当前状态、跟进计划和可追溯时间线。用户确认入库内容、报告客户最新消息、成交、失单、暂停、项目进度或要求查看和更新客户画像时使用。
---

# 客户记忆维护

把 `customer.json` 作为机器状态源，把 Markdown 文件作为简洁视图。只合并用户已确认的事实。

## 更新流程

1. 根据 customer_id 读取 `customer.json`、客户卡片、最新状态和最近时间线。
2. 区分新事实、销售判断、AI 建议和冲突信息。
3. 向用户展示将要修改的字段；涉及客户状态、成交、失单原因、金额、日期或承诺时必须确认。
4. 将确认后的字段写成 JSON patch 文件，运行：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/sa_sales_advisor/cli.py" memory update --workspace "<工作区>" --customer-id "<ID>" --patch-file "<patch.json>"
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

字段约束见 [references/customer-schema.md](references/customer-schema.md)。展示结构见 [assets/customer-card-template.md](assets/customer-card-template.md)。
