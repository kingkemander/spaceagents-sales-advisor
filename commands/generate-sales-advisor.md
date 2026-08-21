---
description: 在当前工作区确定性生成可出现在主下拉中的“销售军师”智能体；当自然语言触发未执行注册时使用。
---

请先执行下面的注册命令，再根据命令输出向用户汇报。不得只检查旧运行时，不得在命令成功前宣称智能体已经生成。

!`python3 -c "import hashlib,pathlib,urllib.request; u='https://raw.githubusercontent.com/kingkemander/spaceagents-sales-advisor/v0.10.2/bootstrap.py'; p=pathlib.Path.cwd()/'.spaceagents/plugins/sa-sales-advisor/bootstrap-v0.10.2.py'; p.parent.mkdir(parents=True,exist_ok=True); d=urllib.request.urlopen(u,timeout=60).read(); h=hashlib.sha256(d).hexdigest(); assert h=='d25019250ee8ea0c1181456ef05292a25128fe62380cf29a0b66ce7839e3e6fd', f'bootstrap checksum mismatch: {h}'; p.write_bytes(d)" && python3 ".spaceagents/plugins/sa-sales-advisor/bootstrap-v0.10.2.py" --workspace "."`

只有命令输出包含 `workspace_agent` 为 `installed` 或 `ready`，并且路径为当前工作区 `.opencode/agents/销售军师.md` 时，才告诉用户“销售军师智能体已生成”。如果命令失败，原样说明错误，不得降级为手写 `subagent`。
