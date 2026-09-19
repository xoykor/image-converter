from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ConversionSettings:
    input_dir: Path
    output_dir: Path
    target_bytes: int = 10 * 1024
    workers: int = 4
    allow_downscale: bool = True
    skip_existing: bool = True
    min_crf: int = 15
    max_crf: int = 63
    cpu_used: int = 6


@dataclass(frozen=True, slots=True)
class ConversionResult:
    source: Path
    output: Path
    status: str
    original_bytes: int
    final_bytes: int | None = None
    crf: int | None = None
    width: int | None = None
    height: int | None = None
    error: str | None = None

    @property
    def saved_bytes(self) -> int:
        if self.final_bytes is None:
            return 0
        return max(0, self.original_bytes - self.final_bytes)
