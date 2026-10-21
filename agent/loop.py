"""Module 4: feedback loop connecting decisions, actions and memory."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .action import ActionExecutor
from .memory import LongTermMemory, ShortTermMemory


class SafetyViolation(RuntimeError):
    """Raised when the loop exceeds configured safety limits."""


@dataclass
class Decision:
    """Output expected from the thinking module (module 2)."""

    action: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    done: bool = False
    answer: Any = None

    @classmethod
    def finish(cls, answer: Any, reason: str = "task completed") -> "Decision":
        return cls(done=True, answer=answer, reason=reason)

    @classmethod
    def call(cls, action: str, arguments: Mapping[str, Any] | None = None, reason: str = "") -> "Decision":
        return cls(action=action, arguments=dict(arguments or {}), reason=reason)


@dataclass
class RunResult:
    complete: bool
    reason: str
    steps: int
    answer: Any
    trace: list[dict[str, Any]]
    memory: list[dict[str, Any]]


Thinker = Callable[[dict[str, Any]], Decision]


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except (TypeError, ValueError):
        return str(value)


class AgentLoop:
    """Runs think -> act -> observe -> remember until done or safely stopped."""

    def __init__(
        self,
        thinker: Thinker,
        executor: ActionExecutor,
        *,
        short_term: ShortTermMemory | None = None,
        long_term: LongTermMemory | None = None,
        max_steps: int = 12,
        max_identical_actions: int = 3,
        persist_feedback: bool = False,
        checkpoint_path: str | Path | None = None,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if max_identical_actions <= 0:
            raise ValueError("max_identical_actions must be positive")
        self.thinker = thinker
        self.executor = executor
        self.short_term = short_term or ShortTermMemory()
        self.long_term = long_term
        self.max_steps = max_steps
        self.max_identical_actions = max_identical_actions
        self.persist_feedback = persist_feedback
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None

    def run(self, goal: str, *, initial_context: Mapping[str, Any] | None = None) -> RunResult:
        self.short_term.clear()
        self.short_term.add(goal, kind="goal", salience=1.0)
        base_context = dict(initial_context or {})
        trace: list[dict[str, Any]] = []
        action_counts: Counter[tuple[str, str]] = Counter()
        complete = False
        reason = "max_steps_reached"
        answer: Any = None

        for step in range(1, self.max_steps + 1):
            context = self._build_context(goal, step, base_context, trace)
            decision = self.thinker(context)
            if not isinstance(decision, Decision):
                raise TypeError("thinker must return agent.loop.Decision")

            if decision.done:
                complete = True
                reason = decision.reason or "completed"
                answer = decision.answer
                self.short_term.add(
                    {"answer": _json_safe(answer), "reason": reason},
                    kind="final",
                    salience=1.0,
                )
                break

            if not decision.action:
                raise SafetyViolation("non-terminal decision must include an action")

            signature = (
                decision.action,
                json.dumps(decision.arguments, sort_keys=True, ensure_ascii=False, default=str),
            )
            action_counts[signature] += 1
            if action_counts[signature] >= self.max_identical_actions:
                raise SafetyViolation(
                    "loop guard triggered: repeated identical action "
                    f"{decision.action!r}"
                )

            self.short_term.add(
                {"action": decision.action, "arguments": decision.arguments, "reason": decision.reason},
                kind="action",
                salience=0.7,
            )
            result = self.executor.execute(
                decision.action,
                decision.arguments,
                context={"step": step, "goal": goal},
            )
            feedback = result.as_feedback()
            trace.append({"step": step, "decision": decision.reason, "feedback": feedback})
            self.short_term.add(feedback, kind="feedback", salience=0.8 if result.success else 0.95)

            if self.persist_feedback or not result.success:
                if self.long_term is not None:
                    self.long_term.remember(
                        feedback,
                        kind="action_result",
                        salience=0.8 if result.success else 0.95,
                        metadata={"step": step, "goal": goal},
                    )
            self._write_checkpoint(goal, step, trace)

        result = RunResult(
            complete=complete,
            reason=reason,
            steps=len(trace),
            answer=_json_safe(answer),
            trace=trace,
            memory=self.short_term.as_context(),
        )
        if self.long_term is not None and complete:
            self.long_term.remember(
                {"goal": goal, "answer": result.answer},
                kind="run_summary",
                salience=1.0,
            )
        self._write_checkpoint(goal, len(trace), trace, final=True)
        return result

    def _build_context(
        self,
        goal: str,
        step: int,
        base_context: dict[str, Any],
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        recalled: list[dict[str, Any]] = []
        if self.long_term is not None:
            recalled = [item.to_dict() for item in self.long_term.recall(goal, kind="run_summary")]
        return {
            "goal": goal,
            "step": step,
            "base": base_context,
            "history": trace,
            "short_term": self.short_term.as_context(limit=12),
            "long_term": recalled,
        }

    def _write_checkpoint(
        self,
        goal: str,
        step: int,
        trace: list[dict[str, Any]],
        *,
        final: bool = False,
    ) -> None:
        if self.checkpoint_path is None:
            return
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "goal": goal,
            "step": step,
            "final": final,
            "trace": trace,
        }
        temporary = self.checkpoint_path.with_suffix(self.checkpoint_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(self.checkpoint_path)