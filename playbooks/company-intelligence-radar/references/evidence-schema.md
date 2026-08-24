# 企业动态证据规范

导入文件使用 `{"records": [...]}`。每条记录至少包含：

```json
{
  "title": "公告标题",
  "event_type": "招标|采购|中标|备案|环评|土地|许可|处罚|工商|融资|招聘|扩产|司法|执行|破产|知识产权|官方新闻|其他",
  "company_name": "公告中的企业法定名称",
  "credit_code": "公告中的统一社会信用代码；没有则为空",
  "company_role": "采购人|招标人|候选人|中标人|供应商|投资方|被投资方|被许可人|被处罚人|原告|被告|招聘主体|其他",
  "summary": "只写原文可支持的事实摘要",
  "amount": "金额和币种；没有则为空",
  "region": "公告对应地区",
  "published_at": "YYYY-MM-DD",
  "source_name": "来源名称",
  "source_url": "原文绝对链接",
  "source_level": "official_original|official_aggregate|company_official|authoritative_media|search_lead",
  "original_accessible": true
}
```

## 核验规则

- `verified`：原文可访问、有发布日期，并且统一社会信用代码精确匹配；或企业法定全称与注册地区同时匹配。
- `pending`：只有简称、搜索摘要、转载、无发布日期、原文无法访问或企业地区不清楚。
- `rejected`：统一社会信用代码冲突，或原文主体明确是另一家公司。

`pending` 和 `rejected` 不得进入正式客户时间线。
