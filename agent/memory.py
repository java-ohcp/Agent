"""Module 4: short-term context, long-term persistence and state helpers."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


def _now() -> float:
    return time.time()


@dataclass
class MemoryItem:
    """One unit of context shared by short- and long-term memory."""

    content: Any
    kind: str = "observation"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=_now)
    ttl_seconds: float | None = None
    salience: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def expired(self, now: float | None = None) -> bool:
        if self.ttl_seconds is None:
            return False
        current = _now() if now is None else now
        return current >= self.created_at + self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        known = {
            "content",
            "kind",
            "id",
            "created_at",
            "ttl_seconds",
            "salience",
            "metadata",
        }
        return cls(**{key: value for key, value in data.items() if key in known})


class ShortTermMemory:
    """Bounded working context used inside one task run."""

    def __init__(
        self,
        *,
        max_items: int = 40,
        max_chars: int = 24_000,
        kind_order: Iterable[str] | None = None,
    ) -> None:
        if max_items <= 0 or max_chars <= 0:
            raise ValueError("memory limits must be positive")
        self.max_items = max_items
        self.max_chars = max_chars
        self.kind_order = tuple(
            kind_order or ("goal", "observation", "action", "feedback", "final")
        )
        self._items: list[MemoryItem] = []

    def add(
        self,
        content: Any,
        *,
        kind: str = "observation",
        salience: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        if not 0.0 <= salience <= 1.0:
            raise ValueError("salience must be between 0 and 1")
        item = MemoryItem(
            content=content,
            kind=kind,
            salience=salience,
            metadata=dict(metadata or {}),
        )
        self._items.append(item)
        self._trim()
        return item

    def recent(self, limit: int | None = None) -> list[MemoryItem]:
        if limit is None:
            return list(self._items)
        if limit < 0:
            raise ValueError("limit must be >= 0")
        return list(self._items[-limit:])

    def as_context(self, limit: int | None = None) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.recent(limit)]

    def clear(self) -> None:
        self._items.clear()

    def _trim(self) -> None:
        while len(self._items) > self.max_items:
            self._items.pop(0)

        def rendered(item: MemoryItem) -> str:
            try:
                return json.dumps(item.to_dict(), ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                return str(item.to_dict())

        while len(self._items) > 1:
            total = sum(len(rendered(item)) for item in self._items)
            if total <= self.max_chars:
                break
            index = min(
                range(len(self._items)),
                key=lambda i: (self._items[i].salience, self._items[i].created_at),
            )
            self._items.pop(index)


class LongTermMemory:
    """File-backed memory with TTL, keyword search and atomic saves."""

    def __init__(self, path: str | Path, *, max_items: int = 1_000) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.path = Path(path)
        self.max_items = max_items
        self._items: list[MemoryItem] = []
        self.load()

    def __len__(self) -> int:
        return len(self._items)

    def remember(
        self,
        content: Any,
        *,
        kind: str = "fact",
        ttl_seconds: float | None = None,
        salience: float = 0.5,
        metadata: dict[str, Any] | None = None,
        save: bool = True,
    ) -> MemoryItem:
        if not 0.0 <= salience <= 1.0:
            raise ValueError("salience must be between 0 and 1")
        item = MemoryItem(
            content=content,
            kind=kind,
            ttl_seconds=ttl_seconds,
            salience=salience,
            metadata=dict(metadata or {}),
        )
        self._items.append(item)
        self._prune()
        self._trim_to_limit()
        if save:
            self.save()
        return item

    def recall(self, query: str = "", *, kind: str | None = None) -> list[MemoryItem]:
        self._prune()
        needle = query.casefold().strip()
        results: list[MemoryItem] = []
        for item in self._items:
            if kind is not None and item.kind != kind:
                continue
            if needle:
                haystack = json.dumps(item.to_dict(), ensure_ascii=False, default=str)
                if needle not in haystack.casefold():
                    continue
            results.append(item)
        results.sort(key=lambda item: (item.salience, item.created_at), reverse=True)
        return results

    def delete(self, item_id: str, *, save: bool = True) -> bool:
        before = len(self._items)
        self._items = [item for item in self._items if item.id != item_id]
        removed = len(self._items) != before
        if removed and save:
            self.save()
        return removed

    def clear(self, *, save: bool = True) -> None:
        self._items.clear()
        if save:
            self.save()

    def load(self) -> None:
        if not self.path.exists():
            self._items = []
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            records = raw.get("items", []) if isinstance(raw, dict) else []
            self._items = [
                MemoryItem.from_dict(record)
                for record in records
                if isinstance(record, dict)
            ]
        except (OSError, ValueError, TypeError):
            self._items = []
        self._prune()
        self._trim_to_limit()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "saved_at": _now(),
            "items": [item.to_dict() for item in self._items],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def _prune(self, now: float | None = None) -> None:
        current = _now() if now is None else now
        self._items = [item for item in self._items if not item.expired(current)]

    def _trim_to_limit(self) -> None:
        if len(self._items) <= self.max_items:
            return
        self._items.sort(key=lambda item: (item.salience, item.created_at), reverse=True)
        self._items = self._items[: self.max_items]