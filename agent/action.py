"""Module 3: action execution.

This module owns tool invocation, retries, execution audit and action safety.
It is intentionally tool-agnostic: APIs, file operations, code execution and
multi-agent subtask dispatch can all be registered as tools.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

Handler = Callable[[Mapping[str, Any]], Any]
ConfirmationCheck = Callable[[str, Mapping[str, Any]], bool]


class ActionDenied(RuntimeError):
    """Raised when a safety rule blocks an action."""


class RetryableToolError(RuntimeError):
    """A tool can explicitly mark its failure as retryable."""


@dataclass(frozen=True)
class ToolSpec:
    """Metadata for a callable action."""

    name: str
    handler: Handler
    description: str = ""
    requires_confirmation: bool = False
    max_retries: int = 0

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("tool name cannot be empty")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")


@dataclass(frozen=True)
class SafetyPolicy:
    """Small, explicit guardrail layer applied before every tool call."""

    allowed_tools: frozenset[str] | None = None
    blocked_tools: frozenset[str] = frozenset()
    deny_unknown_tools: bool = True

    @classmethod
    def allow_only(cls, names: Iterable[str]) -> "SafetyPolicy":
        return cls(allowed_tools=frozenset(names))

    @classmethod
    def deny(cls, names: Iterable[str]) -> "SafetyPolicy":
        return cls(blocked_tools=frozenset(names))

    def validate(self, tool_name: str, known: bool) -> None:
        if not known and self.deny_unknown_tools:
            raise ActionDenied(f"unknown tool is disabled: {tool_name}")
        if tool_name in self.blocked_tools:
            raise ActionDenied(f"tool is blocked by safety policy: {tool_name}")
        if self.allowed_tools is not None and tool_name not in self.allowed_tools:
            raise ActionDenied(f"tool is not in allowlist: {tool_name}")


@dataclass
class ActionResult:
    """Uniform result returned to the memory/feedback layer."""

    success: bool
    tool: str
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    attempts: int = 1
    confirmed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_feedback(self) -> dict[str, Any]:
        """Compact, JSON-safe representation for model context."""
        payload: dict[str, Any] = {
            "success": self.success,
            "tool": self.tool,
            "duration_ms": round(self.duration_ms, 3),
            "attempts": self.attempts,
        }
        if self.success:
            payload["output"] = self.output
        else:
            payload["error"] = self.error
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


class ToolRegistry:
    """Registry used to map stable action names to executable tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec, *, replace: bool = False) -> None:
        if spec.name in self._tools and not replace:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def add(
        self,
        name: str,
        handler: Handler,
        *,
        description: str = "",
        requires_confirmation: bool = False,
        max_retries: int = 0,
        replace: bool = False,
    ) -> None:
        self.register(
            ToolSpec(
                name=name,
                handler=handler,
                description=description,
                requires_confirmation=requires_confirmation,
                max_retries=max_retries,
            ),
            replace=replace,
        )

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> Sequence[str]:
        return tuple(sorted(self._tools))

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "requires_confirmation": spec.requires_confirmation,
                "max_retries": spec.max_retries,
            }
            for spec in sorted(self._tools.values(), key=lambda item: item.name)
        ]


class ActionExecutor:
    """Executes one requested action with safety checks and bounded retries."""

    def __init__(
        self,
        registry: ToolRegistry,
        policy: SafetyPolicy | None = None,
        *,
        confirm: ConfirmationCheck | None = None,
    ) -> None:
        self.registry = registry
        self.policy = policy or SafetyPolicy()
        self.confirm = confirm or (lambda _tool, _args: True)

    def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> ActionResult:
        args = dict(arguments or {})
        context = dict(context or {})
        started = time.perf_counter()

        try:
            spec = self.registry.get(tool_name)
            self.policy.validate(tool_name, known=spec is not None)
            if spec is None:
                raise ActionDenied(f"unknown tool: {tool_name}")

            confirmed = True
            if spec.requires_confirmation:
                confirmed = bool(self.confirm(tool_name, args))
                if not confirmed:
                    raise ActionDenied(f"user confirmation rejected: {tool_name}")

            output = None
            last_error: Exception | None = None
            attempts = 0
            for attempt in range(spec.max_retries + 1):
                attempts += 1
                try:
                    output = spec.handler(args)
                    last_error = None
                    break
                except RetryableToolError as exc:
                    last_error = exc
                    if attempt >= spec.max_retries:
                        break
                except Exception as exc:
                    last_error = exc
                    break

            if last_error is not None:
                return ActionResult(
                    success=False,
                    tool=tool_name,
                    error=f"{type(last_error).__name__}: {last_error}",
                    duration_ms=(time.perf_counter() - started) * 1000,
                    attempts=attempts,
                    confirmed=confirmed,
                    metadata=dict(context),
                )

            return ActionResult(
                success=True,
                tool=tool_name,
                output=output,
                duration_ms=(time.perf_counter() - started) * 1000,
                attempts=attempts,
                confirmed=confirmed,
                metadata=dict(context),
            )
        except ActionDenied as exc:
            return ActionResult(
                success=False,
                tool=tool_name,
                error=f"ActionDenied: {exc}",
                duration_ms=(time.perf_counter() - started) * 1000,
                attempts=0,
                confirmed=False,
                metadata=dict(context),
            )