---
name: sync-spacekb
description: 配置并调用 SpaceKB 企业知识库，查询用户有权访问的文档、读取分块、上传文件，并在每天 18:00 将当天已完成任务与重要客户节点同步到用户私人域。用户说“连接知识库”“填写 API Key”“查企业知识”“上传到知识库”“同步私人域”或启用每日知识沉淀时使用。
---

# SpaceKB 知识库协同

API 结构见 [references/spacekb-api.md](references/spacekb-api.md)。任何时候都不要读取、复述或打印已保存的 API Key。

## 首次配置

1. 运行状态检查：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" knowledge status --workspace "<当前项目>"
```

2. 尚未配置时，引导用户在本机输入一次 API Key。优先使用环境提供的遮罩式敏感输入；如果没有，打开当前项目终端并运行以下交互命令，输入内容不会显示：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" knowledge configure --workspace "<当前项目>"
```

不得要求用户把 API Key 直接发在聊天里，也不得把 Key 写进 `SKILL.md`、客户档案、日志、Git 仓库或自动任务提示词。

3. 配置成功后，Base URL、知识库 ID 和默认私人域写入当前项目的插件用户配置；API Key 单独写入当前项目 `.spaceagents/secrets/` 下的私有文件并设置仅本人权限。升级插件时不得删除。
4. 当前默认 SpaceKB 地址是公网 HTTP。正式使用必须改为 HTTPS。只有用户明确接受测试风险时，才允许在配置命令后增加 `--allow-insecure-http`；不得静默降低安全要求。
5. 配置接口会先验证知识库权限，验证失败则不保存 Key。

## 企业知识查询

需要回答企业项目、政策、产品、案例或其他内部知识时：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" knowledge search \
  --workspace "<当前项目>" \
  --query "<用户问题>"
```

根据返回分块回答，并区分知识库事实与销售建议。不得因为知识库没有答案而编造企业事实。需要更多上下文时再分页调用 `knowledge chunks --doc-id --offset <偏移> --limit 8 --max-chars 1600`。

固定上下文边界：

- 优先使用 `knowledge search`，不得为“方便”读取整个知识库或整篇长文。
- `knowledge list` 与 `knowledge chunks` 必须分页；一次只取当前判断所需的最小范围。
- 不读取或展开 ZIP、图片、音视频等二进制文件内容；它们只能作为安装包或待解析材料交给对应工具。
- 若仍需后续分块，先总结当前批次再读取下一批，禁止把多批原文持续堆入同一条提示词。

起草销售回复时，知识库内容进入“企业事实层”；客户档案、销售方法与个人口吻仍按回复流程依次处理。

## 上传文件

用户明确要求上传时执行：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" knowledge upload \
  --workspace "<当前项目>" \
  --file "<文件绝对路径>" \
  --domain "__private__"
```

默认上传到私人域。上传到企业公共域或指定部门域前必须让用户明确确认目标域。

## 每日 18:00 私人域同步

SpaceKB 首次配置成功后，立即使用当前环境的自动任务能力创建一个每天 18:00 的循环任务，名称建议为“SA 销售日报同步｜私人知识库”。同名同时间任务已存在时更新，不重复创建。

自动任务提示词：

```text
运行 SA 销售军师的每日收尾流程：
1. 读取当前项目 SA销售工作区/logs/task-events.jsonl、今日更新的客户档案和未来七天关键跟进节点；
2. 生成只包含今日已完成事项、今日重要客户节点和未来七天安排的销售日报；
3. 运行 knowledge sync-daily，把日报上传到 SpaceKB 的 __private__ 私人域；
4. 同步成功后直接用文字报告“已同步事项数、重要节点数、远端文档状态”；
5. 不上传原始聊天、电话号码、整份客户档案或与日报无关的文件；不打印 API Key。
```

对应命令：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" knowledge sync-daily \
  --workspace "<当前项目>" \
  --sales-root "<当前项目>/SA销售工作区" \
  --domain "__private__"
```

任务运行失败时保留本地日报和错误信息，下次允许重试；不得把失败说成同步成功。

## 完成事项记录

销售回复“已完成”或确认重要客户节点后，将其记录到本地事件流水：

```bash
python3 "<运行时根目录>/sa_sales_advisor/cli.py" activity add \
  --root "<当前项目>/SA销售工作区" \
  --event-type "completed" \
  --title "<完成事项>" \
  --customer-id "<可选客户 ID>" \
  --customer-name "<可选客户名>" \
  --details "<结果摘要>"
```

客户出现签约、失单、回款、现场考察、报价确认、关键决策人变化等节点时，使用 `--event-type milestone`。只有已确认事实才能记录。

## 固定边界

- API Key 只保存在用户本机私有配置，不进入插件包和 GitHub。
- 默认只向 `__private__` 上传每日摘要；不上传完整原件和全量客户档案。
- 自动任务只同步用户本人工作结果，不跨销售、跨企业或跨权限域。
- 知识库无法访问时，销售军师的本地客户管理、看板和回复功能仍可继续使用。
