"""Runnable end-to-end demo for Agent modules 3 and 4."""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import AgentLoop, Decision, LongTermMemory, SafetyPolicy
from agent.action import ActionExecutor, ToolRegistry
from agent.builtin_tools import SubtaskDispatcher, register_core_tools, register_file_tools


def build_demo() -> AgentLoop:
    registry = ToolRegistry()
    register_core_tools(registry)
    register_file_tools(registry, ROOT, confirm_writes=False)

    dispatcher = SubtaskDispatcher()
    dispatcher.register(
        "summarize",
        lambda payload: {"summary": f"已完成摘要：{str(payload)[:40]}", "items": 3},
    )
    dispatcher.install(registry)

    executor = ActionExecutor(
        registry,
        SafetyPolicy.allow_only({"text_stats", "dispatch_subtask", "current_time"}),
    )

    def thinker(context: dict) -> Decision:
        history = context["history"]
        if not history:
            return Decision.call(
                "text_stats",
                {"text": "感知 -> 思考 -> 行动 -> 记忆闭环\n智能体工程落地示例"},
                reason="先统计任务文本",
            )
        if len(history) == 1:
            return Decision.call(
                "dispatch_subtask",
                {"worker": "summarize", "payload": "模块 3 工具调用 + 模块 4 记忆反馈"},
                reason="把摘要交给子任务执行器",
            )
        return Decision.finish(
            answer={"status": "ok", "completed_steps": len(history)},
            reason="两个动作均已收到反馈",
        )

    runtime = ROOT / ".runtime"
    return AgentLoop(
        thinker,
        executor,
        long_term=LongTermMemory(runtime / "memory.json"),
        max_steps=6,
        persist_feedback=True,
        checkpoint_path=runtime / "checkpoint.json",
    )


def main() -> None:
    loop = build_demo()
    result = loop.run("验证行动执行与记忆反馈闭环")
    print("complete:", result.complete)
    print("reason:", result.reason)
    print("steps:", result.steps)
    print("answer:", result.answer)
    print("trace:")
    for entry in result.trace:
        print(" ", entry)
    print("long_term_items:", len(loop.long_term) if loop.long_term else 0)


if __name__ == "__main__":
    main()