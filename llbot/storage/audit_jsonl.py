"""Audit JSONL persistence for deterministic replay and paper decisions."""

import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class JsonlAuditWriter:
    """Append JSONL audit records as they are produced."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._file = None

    def __enter__(self) -> "JsonlAuditWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def append(self, record: Any) -> None:
        if self._file is None:
            raise RuntimeError("JsonlAuditWriter must be used as a context manager")
        self._file.write(_jsonl_line(record))
        self._file.write("\n")
        self._file.flush()


def write_audit_records(path: str | Path, records: Iterable[Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(_jsonl_line(record))
            f.write("\n")


def write_json(path: str | Path, payload: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )


def audit_record_to_dict(record: Any) -> Any:
    return _jsonable(record)


def _jsonl_line(record: Any) -> str:
    return json.dumps(audit_record_to_dict(record), ensure_ascii=True, separators=(",", ":"))


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
