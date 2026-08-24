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
│   ├── company-identity-index.json
│   ├── company-intelligence.jsonl
│   ├── reminder-index.json
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
├── plans/
│   └── sales-plan-YYYY-MM-DD.md
├── exports/spacekb/
│   └── SA销售日报-YYYY-MM-DD.md
├── growth/
│   ├── strategy-notes.md
│   └── reviews/
└── logs/
    ├── task-events.jsonl
    ├── automation-runs.jsonl
    └── spacekb-sync.jsonl
```

`customer.json` 是机器状态源；Markdown 是人和智能体可读视图；原始文件是证据；HTML 只负责展示。SpaceKB API Key 不在该目录中，单独保存在项目级 `.spaceagents/secrets/`。
