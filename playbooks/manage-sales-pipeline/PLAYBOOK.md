---
name: manage-sales-pipeline
description: 维护线索清单和标准销售漏斗，记录机会金额、预计成交日期、阶段、跟进与下一步；生成阶段分布、转化率、收入预测和风险机会报告。用户说“新线索”“更新销售阶段”“查看漏斗”“预计收入”“销售报告”“哪些机会有风险”时使用。
---

# 线索与销售漏斗管理

`customers/*/customer.json` 是唯一主数据。`pipeline/leads.md`、`pipeline/pipeline.md` 和 `pipeline/reports/*.md` 都是自动生成视图，不得直接维护另一套冲突数据。

## 标准阶段

```text
初步接触 → 需求确认 → 方案演示 → 报价谈判 → 赢单/输单
```

行业自定义阶段可继续写入 `stage`，标准漏斗统一写入 `pipeline_stage`。

## 新线索

1. 优先确认公司名称、联系人、联系方式、来源、意向度和行业；缺失内容不得猜测。
2. 用户暂时无法补全时允许先建档，把缺失项写入 `unconfirmed` 并给出下一次自然补问方式。
3. 新线索默认 `pipeline_stage=初步接触`、`win_probability=10`。
4. 复用客户创建和记忆更新流程，不创建第二个客户目录。

## 更新机会

每个机会重点维护：

- `pipeline_stage`
- `opportunity_amount` 与 `currency`
- `expected_close_date`
- `win_probability`
- `last_contact_at`
- `next_followup_at`
- `next_action`

阶段、金额、预计成交日期和赢单/输单属于关键变化，先向用户展示修改内容，确认后使用 `memory update`。运行时会自动追加 `stage_history`，不得覆盖历史。

## 跟进与逾期

- 根据当前阶段、预计成交日期和用户承诺推算建议跟进日期。
- 已存在明确跟进日期时不得擅自改写。
- 到期或逾期机会进入今日行动；提醒销售本人，不自动联系客户。
- 临近预计成交日期但没有下一步动作时标记风险。

## 生成视图与报告

确认更新后运行：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" pipeline --workspace "<当前项目>/SA销售工作区"
```

生成：

- `pipeline/leads.md`：线索清单与资料缺口
- `pipeline/pipeline.md`：全部机会、阶段、金额、概率与下一步
- `pipeline/reports/YYYY-MM-DD.md`：漏斗概览、阶段转化、加权预计收入、风险和数据质量

转化率没有足够阶段历史时必须显示“样本不足”，不得伪造精确比例。报告中的预计收入是管理预测，不是财务确认收入。

## 用户可见回复

状态变化后简要说明：更新了哪个机会、从哪个阶段到哪个阶段、金额和预计成交日期是否齐全、下一步是什么。用户询问整体状况时再输出完整漏斗总结。
