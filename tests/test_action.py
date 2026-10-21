import unittest

from agent.action import (
    ActionExecutor,
    RetryableToolError,
    SafetyPolicy,
    ToolRegistry,
)


class ActionExecutorTests(unittest.TestCase):
    def test_success_and_failure_are_captured(self) -> None:
        registry = ToolRegistry()
        registry.add("double", lambda args: int(args["value"]) * 2)
        registry.add("boom", lambda args: 1 / 0)
        executor = ActionExecutor(registry)

        success = executor.execute("double", {"value": 4})
        failure = executor.execute("boom", {})

        self.assertTrue(success.success)
        self.assertEqual(success.output, 8)
        self.assertFalse(failure.success)
        self.assertIn("ZeroDivisionError", failure.error)

    def test_retryable_failure_is_bounded(self) -> None:
        calls = 0

        def flaky(_args):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RetryableToolError("temporary")
            return "ok"

        registry = ToolRegistry()
        registry.add("flaky", flaky, max_retries=2)
        result = ActionExecutor(registry).execute("flaky")

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 3)

    def test_safety_policy_and_confirmation(self) -> None:
        registry = ToolRegistry()
        registry.add("safe", lambda args: "safe")
        registry.add("danger", lambda args: "danger", requires_confirmation=True)
        executor = ActionExecutor(
            registry,
            SafetyPolicy.deny({"danger"}),
            confirm=lambda _tool, _args: False,
        )

        self.assertFalse(executor.execute("danger").success)
        self.assertFalse(executor.execute("missing").success)

        allowed = ActionExecutor(
            registry,
            SafetyPolicy.allow_only({"safe"}),
            confirm=lambda _tool, _args: True,
        )
        self.assertTrue(allowed.execute("safe").success)


if __name__ == "__main__":
    unittest.main()