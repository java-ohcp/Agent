# Agent Modules 3 + 4

这是给 `Agent` 仓库做的一次本地 vibecoding 实现，聚焦图中的两大版块：

1. **第 3 版块：行动执行**
   - 工具注册、工具调用、重试与执行耗时统计
   - 文件读写（限制在指定工作区）
   - HTTP API 请求（必须显式配置主机白名单）
   - 多智能体/Worker 子任务分发
   - 工具白名单、黑名单、危险操作确认
2. **第 4 版块：记忆与反馈闭环**
   - 短期上下文：数量与字符量双重限制
   - 长期记忆：JSON 持久化、TTL、关键词召回、原子保存
   - 状态检查点：每一步落盘，方便中断恢复
   - Think -> Act -> Observe -> Remember 循环
   - 步数上限、重复动作防死循环、安全异常

第 1、2 版块通过 `Decision` 注入：你以后可以替换成真实感知模块和 LLM 规划模块，核心闭环不用重写。

## 目录结构

```text
agent/
  action.py            # 第 3 版块：工具执行与安全
  builtin_tools.py     # 文件、HTTP、子任务等实用工具
  memory.py            # 第 4 版块：短期/长期记忆
  loop.py              # 第 4 版块：反馈闭环与检查点
examples/demo.py       # 端到端可运行演示
tests/                 # 标准库 unittest 测试
```

## 快速运行

Python 3.10+：

```powershell
cd C:\Users\ABC\AgentVibecoding
python examples\demo.py
python -m unittest discover -s tests -v
```

## 最小用法

```python
from agent import AgentLoop, Decision, ShortTermMemory
from agent.action import ActionExecutor, ToolRegistry

registry = ToolRegistry()
registry.add("echo", lambda args: args["value"])
executor = ActionExecutor(registry)

def thinker(context):
    if context["history"]:
        return Decision.finish("任务完成")
    return Decision.call("echo", {"value": "hello"}, reason="测试工具")

result = AgentLoop(thinker, executor, short_term=ShortTermMemory()).run("示例任务")
print(result.answer, result.memory)
```

## 设计边界

- `ActionExecutor` 只执行已注册、已授权的动作，不解析自然语言。
- `AgentLoop.thinker` 只负责决策；执行结果始终通过反馈记忆回到上下文。
- 文件工具采用目录穿越防护；HTTP 工具采用显式主机白名单。
- 长期记忆文件默认由调用者指定路径，示例写入 `.runtime/`，该目录已忽略提交。
## 自动合并配置

仓库新增两个工作流：

- `.github/workflows/ci.yml`：每次 push / PR 运行 `unittest`。
- `.github/workflows/auto-merge.yml`：当同一仓库的 PR 被加上 `automerge` 标签后，自动启用 squash auto-merge；分支保护规则和 CI 通过后才会合并。

使用方式：

1. 在 GitHub 仓库 Settings → General → Pull Requests 中打开 **Allow auto-merge**。
2. 在仓库 Rules → Rulesets 中设置 main 保护规则，至少要求 `CI / tests` 检查通过。
3. 给需要合并的 PR 添加 `automerge` 标签。

> `automerge` 工作流不会绕过分支保护，也不会替用户通过代码审查。真正的机器人“自动批准”需要配置独立 GitHub App 或具有 `pull_requests: write` 权限的机器账号令牌。
