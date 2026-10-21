import tempfile
import unittest
from pathlib import Path

from agent import AgentLoop, Decision, LongTermMemory, SafetyViolation, ShortTermMemory
from agent.action import ActionExecutor, ToolRegistry


class MemoryTests(unittest.TestCase):
    def test_short_term_respects_item_limit(self) -> None:
        memory = ShortTermMemory(max_items=2)
        memory.add("one")
        memory.add("two")
        memory.add("three")

        self.assertEqual([item.content for item in memory.recent()], ["two", "three"])

    def test_long_term_persists_and_searches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            first = LongTermMemory(path)
            first.remember("用户偏好中文回复", kind="preference")

            second = LongTermMemory(path)
            matches = second.recall("中文")

            self.assertEqual(len(second), 1)
            self.assertEqual(matches[0].content, "用户偏好中文回复")


class LoopTests(unittest.TestCase):
    def _loop(self, thinker, *, max_identical_actions: int = 3) -> AgentLoop:
        registry = ToolRegistry()
        registry.add("echo", lambda args: args.get("value"))
        return AgentLoop(
            thinker,
            ActionExecutor(registry),
            max_steps=6,
            max_identical_actions=max_identical_actions,
        )

    def test_loop_returns_feedback_and_completes(self) -> None:
        def thinker(context):
            if context["history"]:
                return Decision.finish(context["history"][0]["feedback"]["output"])
            return Decision.call("echo", {"value": "反馈成功"})

        result = self._loop(thinker).run("test")

        self.assertTrue(result.complete)
        self.assertEqual(result.answer, "反馈成功")
        self.assertEqual(result.memory[-1]["kind"], "final")

    def test_loop_guard_detects_repetition(self) -> None:
        def thinker(_context):
            return Decision.call("echo", {"value": "loop"})

        with self.assertRaises(SafetyViolation):
            self._loop(thinker, max_identical_actions=2).run("test")


if __name__ == "__main__":
    unittest.main()