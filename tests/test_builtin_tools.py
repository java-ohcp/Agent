import tempfile
import unittest
from pathlib import Path

from agent import SafetyPolicy
from agent.action import ActionExecutor, ToolRegistry
from agent.builtin_tools import FileTools, SubtaskDispatcher, register_file_tools


class BuiltinToolTests(unittest.TestCase):
    def test_file_tools_block_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tools = FileTools(directory)
            with self.assertRaises(PermissionError):
                tools.resolve("../outside.txt")

    def test_file_write_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry()
            register_file_tools(registry, directory, confirm_writes=True)
            executor = ActionExecutor(
                registry,
                SafetyPolicy.allow_only({"write_file"}),
                confirm=lambda _tool, _args: False,
            )
            result = executor.execute("write_file", {"filename": "x.txt", "content": "x"})
            self.assertFalse(result.success)
            self.assertIn("confirmation", result.error)

    def test_subtask_dispatch(self) -> None:
        registry = ToolRegistry()
        dispatcher = SubtaskDispatcher()
        dispatcher.register("square", lambda value: int(value) ** 2)
        dispatcher.install(registry)
        result = ActionExecutor(registry).execute(
            "dispatch_subtask",
            {"worker": "square", "payload": 9},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["output"], 81)


if __name__ == "__main__":
    unittest.main()