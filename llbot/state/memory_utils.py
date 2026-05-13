"""Atomic helpers for compact project memory."""

import json
import tempfile
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_memory(path: str | Path) -> dict[str, Any]:
    memory_path = Path(path)
    with memory_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported memory schema_version={version!r}")
    return data


def update_memory(
    path: str | Path,
    mutator: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any]:
    current = load_memory(path)
    working = deepcopy(current)
    result = mutator(working)
    next_state = working if result is None else result
    next_state = prune_memory(next_state)
    _atomic_write_json(Path(path), next_state)
    return next_state


def prune_memory(data: dict[str, Any]) -> dict[str, Any]:
    pruned = deepcopy(data)
    retention = pruned.get("retention", {})
    max_recent_errors = int(retention.get("max_recent_errors", 100))
    max_symbol_entries = int(retention.get("max_symbol_entries", 500))

    recent_errors = list(pruned.get("recent_errors", []))
    pruned["recent_errors"] = recent_errors[-max_recent_errors:]

    symbol_state = pruned.get("symbol_state", {})
    if isinstance(symbol_state, dict) and len(symbol_state) > max_symbol_entries:
        ordered = sorted(
            symbol_state.items(),
            key=lambda item: str(item[1].get("last_signal_utc", "")) if isinstance(item[1], dict) else "",
            reverse=True,
        )
        pruned["symbol_state"] = dict(ordered[:max_symbol_entries])

    pruned["updated_at_utc"] = utc_now_iso()
    return pruned


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as tmp:
        json.dump(payload, tmp, ensure_ascii=True, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)

