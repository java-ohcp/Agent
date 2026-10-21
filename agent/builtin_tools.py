"""Practical tools for APIs, files, code-like computation and subtask dispatch."""

from __future__ import annotations

import fnmatch
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .action import RetryableToolError, ToolRegistry


def register_core_tools(registry: ToolRegistry) -> None:
    """Register safe, dependency-free demonstration tools."""

    def text_stats(args: Mapping[str, Any]) -> dict[str, Any]:
        text = str(args.get("text", ""))
        if not text:
            raise ValueError("text is required")
        stripped = text.strip()
        return {
            "characters": len(text),
            "characters_no_space": len("".join(text.split())),
            "words": len(stripped.split()) if stripped else 0,
            "lines": text.count("\n") + 1,
            "non_empty_lines": sum(1 for line in text.splitlines() if line.strip()),
        }

    def current_time(args: Mapping[str, Any]) -> dict[str, Any]:
        pattern = str(args.get("format", "%Y-%m-%d %H:%M:%S"))
        now = datetime.now()
        return {"iso": now.isoformat(timespec="seconds"), "formatted": now.strftime(pattern)}

    def echo(args: Mapping[str, Any]) -> Any:
        return args.get("value")

    registry.add("text_stats", text_stats, description="Count characters, words and lines.")
    registry.add("current_time", current_time, description="Return the current local time.")
    registry.add("echo", echo, description="Echo a value; useful for pipeline tests.")


class FileTools:
    """Filesystem actions constrained to one workspace directory."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).resolve()

    def resolve(self, relative_path: str) -> Path:
        candidate_text = str(relative_path)
        if not candidate_text or Path(candidate_text).is_absolute():
            raise PermissionError("absolute paths are not allowed")
        candidate = (self.base_dir / candidate_text).resolve()
        if candidate != self.base_dir and self.base_dir not in candidate.parents:
            raise PermissionError("path escapes the configured workspace")
        return candidate

    def read_text(self, args: Mapping[str, Any]) -> dict[str, Any]:
        path = self.resolve(str(args.get("filename", "")))
        encoding = str(args.get("encoding", "utf-8"))
        return {"filename": args.get("filename"), "content": path.read_text(encoding=encoding)}

    def write_text(self, args: Mapping[str, Any]) -> dict[str, Any]:
        path = self.resolve(str(args.get("filename", "")))
        content = str(args.get("content", ""))
        encoding = str(args.get("encoding", "utf-8"))
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if bool(args.get("append", False)) else "w"
        with path.open(mode, encoding=encoding) as handle:
            handle.write(content)
        return {"filename": args.get("filename"), "bytes": len(content.encode(encoding))}

    def list_files(self, args: Mapping[str, Any]) -> list[str]:
        pattern = str(args.get("pattern", "*"))
        return sorted(
            str(path.relative_to(self.base_dir))
            for path in self.base_dir.rglob("*")
            if path.is_file() and fnmatch.fnmatch(str(path.relative_to(self.base_dir)), pattern)
        )


def register_file_tools(
    registry: ToolRegistry,
    base_dir: str | Path,
    *,
    confirm_writes: bool = True,
) -> FileTools:
    tools = FileTools(base_dir)
    registry.add("read_file", tools.read_text, description="Read a UTF text file inside the workspace.")
    registry.add(
        "write_file",
        tools.write_text,
        description="Write a text file inside the workspace.",
        requires_confirmation=confirm_writes,
    )
    registry.add("list_files", tools.list_files, description="List workspace files by glob pattern.")
    return tools


def register_http_json_tool(
    registry: ToolRegistry,
    *,
    allowed_hosts: tuple[str, ...],
    timeout_seconds: float = 10.0,
    require_confirmation: bool = True,
) -> None:
    """Register an HTTP JSON request tool with an explicit host allowlist."""

    if not allowed_hosts:
        raise ValueError("allowed_hosts cannot be empty; HTTP access is deny-by-default")
    if timeout_seconds <= 0 or timeout_seconds > 30:
        raise ValueError("timeout_seconds must be in (0, 30]")

    def http_json(args: Mapping[str, Any]) -> dict[str, Any]:
        url = str(args.get("url", ""))
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise PermissionError("only http/https URLs are allowed")
        if parsed.hostname not in allowed_hosts:
            raise PermissionError(f"host is not allowlisted: {parsed.hostname}")
        method = str(args.get("method", "GET")).upper()
        if method not in {"GET", "POST"}:
            raise PermissionError("only GET and POST are supported")
        body = args.get("json_body")
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                payload: Any
                try:
                    payload = json.loads(raw)
                except ValueError:
                    payload = raw
                return {"status": response.status, "body": payload}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RetryableToolError(f"network error: {exc.reason}") from exc

    registry.add(
        "http_json",
        http_json,
        description=f"Send GET/POST JSON request to allowlisted hosts: {', '.join(allowed_hosts)}",
        requires_confirmation=require_confirmation,
        max_retries=1,
    )


Worker = Callable[[Any], Any]


class SubtaskDispatcher:
    """Registry for worker/sub-agent style task dispatch."""

    def __init__(self) -> None:
        self._workers: dict[str, Worker] = {}

    def register(self, name: str, worker: Worker, *, replace: bool = False) -> None:
        if not name:
            raise ValueError("worker name cannot be empty")
        if name in self._workers and not replace:
            raise ValueError(f"worker already registered: {name}")
        self._workers[name] = worker

    def dispatch(self, args: Mapping[str, Any]) -> dict[str, Any]:
        name = str(args.get("worker", ""))
        worker = self._workers.get(name)
        if worker is None:
            raise KeyError(f"unknown worker: {name}")
        output = worker(args.get("payload"))
        return {"worker": name, "output": output}

    def install(self, registry: ToolRegistry, *, replace: bool = False) -> None:
        registry.add(
            "dispatch_subtask",
            self.dispatch,
            description="Dispatch one subtask to a registered worker/sub-agent.",
            replace=replace,
        )