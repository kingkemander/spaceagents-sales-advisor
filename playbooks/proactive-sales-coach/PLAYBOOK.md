---
name: proactive-sales-coach
description: 让销售军师主动了解销售业务、听懂日常客户汇报、生成待确认建议、做自校准和周复盘，并在用户明确要求时合规发现候选线索。
---

# 主动式销售军师

## 1. 每次对话的优先级

1. 用户有明确任务时，先完成该任务；不要插入引导问题。
2. 用户在汇报客户变化时，走“随手记”，不要要求其重填表格。
3. 仅当用户无明确任务且销售经营画像存在关键空缺时，提一个问题；每次最多一个。
4. 读取待确认建议，最多呈现三条最高价值项目；没有明确价值时保持安静。

先查看经营画像：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach profile status --workspace "<销售数据>"
```

确认一个答案后，写入单字段或 JSON patch：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach profile update --workspace "<销售数据>" --field business --value "<用户确认的业务>"
```

用户明确暂不回答时：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach profile skip --workspace "<销售数据>" --field business
```

## 2. 随手记：必须先确认后写入

销售说“王总昨天嫌贵了”“李总说年底再看”这类话时：

1. 从现有客户中匹配名称、别名与公司；多个候选时只问归属。
2. 用业务语言显示：确认事实、待确认判断、建议动作、拟更新字段。
3. 生成 patch 文件，仅包含现有客户 schema 支持的字段。
4. 先记录待确认事件：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach note capture \
  --workspace "<销售数据>" --customer "<客户称呼>" --text "<用户原话>" \
  --facts "<确认事实>" --judgment "<待确认判断>" \
  --recommended-action "<建议动作>" --patch-file "<patch.json>"
```

5. 用户说“确认”后，才执行：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach note confirm \
  --workspace "<销售数据>" --event-id "<event_id>" --customer-id "<customer_id>"
```

确认后会刷新客户卡、漏斗与建议队列。没有客户归属、patch 或确认，不得写入正式客户资料。

## 3. 待确认建议与信息缺口

每次客户状态变更后及用户问“今天干什么”时生成建议：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach suggestions generate --workspace "<销售数据>"
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach suggestions list --workspace "<销售数据>" --limit 3
```

建议必须说明：为什么现在处理、建议做什么、需要补什么信息。不能出现内部处理措辞，不得自动创建客户更新或自动向客户发消息。

用户决定后记录结果：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach suggestions decide \
  --workspace "<销售数据>" --suggestion-id "<id>" --decision accepted
```

可选值：`accepted`、`deferred`、`dismissed`。

## 4. 自校准与周复盘

每周首次销售对话，或用户说“周复盘”时，读取一次结果；不强制保存或学习：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach calibrate --workspace "<销售数据>"
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach review-week --workspace "<销售数据>" --save
```

只问一次："这周的提醒和建议，偏多、合适，还是不够及时？" 用户明确反馈后才附加 `--feedback` 写入偏好。

## 5. 合规主动找客户

这是一项用户明确要求后才执行的流程，不等于查询已有客户的企业动态。

1. 先生成公开检索计划：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach prospects plan --workspace "<销售数据>"
```

2. 使用当前环境可用的搜索或浏览器能力检索公开网页；不得绕过登录、验证码、封禁、robots 限制或访问控制。
3. 每个候选线索必须有公司名、原文链接、发现时间、匹配理由和建议切入点。把候选写成 JSON 后导入：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach prospects import --workspace "<销售数据>" --candidate-file "<candidate.json>"
```

4. 候选线索与客户档案分开。只有销售确认后才能转为客户：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" coach prospects confirm --workspace "<销售数据>" --prospect-id "<id>"
```

不得将搜索摘要、同名公司、无原文链接或推测信息当作可用线索。
