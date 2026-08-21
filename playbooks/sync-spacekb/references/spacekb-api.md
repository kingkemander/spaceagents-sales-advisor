# SpaceKB API 参考

默认配置来自用户提供的 SpaceKB 技能说明，不包含任何 API Key。

```text
Base URL: http://123.56.18.172:30000
Knowledge Base ID: ecec0261-5cfc-4aae-af76-605c98b3fd59
Default domain: __private__
Authentication: Authorization: Bearer <user-api-key>
```

公网 HTTP 会明文传输认证信息，运行时默认拒绝。正式环境应提供 HTTPS 地址。

## 接口

- `GET /api/knowledge-bases/{knowledge_base_id}`：知识库信息。
- `GET /api/knowledge-bases/{knowledge_base_id}/documents?domain={domain}`：有权访问的文档列表。
- `GET /api/knowledge-bases/{knowledge_base_id}/documents/{doc_id}/chunks`：文档分块。
- `POST /api/knowledge-bases/{knowledge_base_id}/documents`：单文件上传，`multipart/form-data` 字段为 `file` 和 `target_domain`。
- `POST /api/knowledge-bases/{knowledge_base_id}/documents/batch`：批量上传，文件字段为 `files`。

上传响应的 `status` 可能为 `pending`，表示仍在异步解析；`completed` 表示可检索，`failed` 表示处理失败。

## 权限域

- `__private__`：仅当前 API Key 所属用户可见。
- 其他权限域：由 API Key 的账号权限决定。
- 查询和上传不得绕过服务端权限过滤。
