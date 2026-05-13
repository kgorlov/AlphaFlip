"""Manual kill-switch helpers."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileKillSwitch:
    path: Path

    def active(self) -> bool:
        return self.path.exists()

    def reason(self) -> str:
        if self.active():
            return f"kill-switch file exists: {self.path}"
        return "ok"

