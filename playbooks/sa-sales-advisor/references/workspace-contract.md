# 工作区契约

```text
SA销售工作区/
├── config/
│   ├── company-profile.md
│   ├── sales-soul.md
│   ├── sales-method-library.md
│   └── reminder-settings.json
├── inbox/{pending,confirmed,rejected}/
├── indexes/
│   ├── customer-index.json
│   ├── material-index.json
│   └── ingestion-ledger.jsonl
├── customers/{customer-folder}/
│   ├── customer.json
│   ├── customer-card.md
│   ├── current-status.md
│   ├── follow-up-plan.md
│   ├── evidence-index.md
│   ├── sources/{original,markdown}/
│   └── timeline/
├── dashboard/
│   ├── dashboard-data.json
│   └── index.html
├── growth/
│   ├── weekly-focus.md
│   └── reviews/
└── logs/
```

`customer.json` 是机器状态源；Markdown 是人和 AI 可读视图；原始文件是证据；HTML 只负责展示。
