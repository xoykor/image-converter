from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from image_converter.core.ffmpeg import encode_avif, probe_dimensions
from image_converter.core.models import ConversionResult, ConversionSettings


class TargetSizeEncoder:
    """Find the highest AVIF quality that fits a byte ceiling."""

    # Downscale progressively instead of stopping after a few percentages.
    # This matters for multi-megapixel inputs: 66% of a 4000 px image is still
    # far too large for a 10 KiB budget.
    DOWNSCALE_FACTOR = 0.82
    MIN_FALLBACK_WIDTH = 320

    def __init__(self, settings: ConversionSettings) -> None:
        self.settings = settings

    def convert(self, source: Path, output: Path) -> ConversionResult:
        original_bytes = source.stat().st_size

        if self.settings.skip_existing and output.exists():
            existing_size = output.stat().st_size
            if 0 < existing_size <= self.settings.target_bytes:
                width, height = probe_dimensions(output)
                return ConversionResult(
                    source=source,
                    output=output,
                    status="skipped",
                    original_bytes=original_bytes,
                    final_bytes=existing_size,
                    width=width,
                    height=height,
                )

        # Never leave an old, oversized result in place. Otherwise a failed
        # retry can look like it produced that stale file.
        if output.exists():
            output.unlink()

        source_width, _source_height = probe_dimensions(source)
        candidate_widths = self._candidate_widths(source_width)

        try:
            for width in candidate_widths:
                attempt = self._best_for_width(source, width)
                if attempt is None:
                    continue

                temp_file, final_size, crf = attempt

                # Belt-and-suspenders check: a successful result must never be
                # committed when it exceeds the requested byte ceiling.
                if final_size > self.settings.target_bytes:
                    temp_file.unlink(missing_ok=True)
                    continue

                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(temp_file), output)

                final_width, final_height = probe_dimensions(output)
                return ConversionResult(
                    source=source,
                    output=output,
                    status="ok",
                    original_bytes=original_bytes,
                    final_bytes=final_size,
                    crf=crf,
                    width=final_width,
                    height=final_height,
                )

            return ConversionResult(
                source=source,
                output=output,
                status="failed",
                original_bytes=original_bytes,
                error=(
                    "Não foi possível atingir o tamanho alvo mesmo no CRF máximo "
                    f"e reduzindo progressivamente até {self.MIN_FALLBACK_WIDTH}px."
                ),
            )
        except Exception as exc:
            output.unlink(missing_ok=True)
            return ConversionResult(
                source=source,
                output=output,
                status="failed",
                original_bytes=original_bytes,
                error=str(exc),
            )

    def _candidate_widths(self, source_width: int) -> list[int | None]:
        """Return original size followed by progressively smaller widths."""

        widths: list[int | None] = [None]

        if not self.settings.allow_downscale or source_width <= self.MIN_FALLBACK_WIDTH:
            return widths

        width = source_width

        while width > self.MIN_FALLBACK_WIDTH:
            next_width = int(width * self.DOWNSCALE_FACTOR)
            next_width -= next_width % 2
            next_width = max(self.MIN_FALLBACK_WIDTH, next_width)

            if next_width >= width:
                break

            if next_width not in widths:
                widths.append(next_width)

            width = next_width

        if widths[-1] != self.MIN_FALLBACK_WIDTH:
            widths.append(self.MIN_FALLBACK_WIDTH)

        return widths

    def _best_for_width(
        self,
        source: Path,
        width: int | None,
    ) -> tuple[Path, int, int] | None:
        """Find the lowest CRF that fits at one resolution.

        We first test max_crf. If even the smallest/lowest-quality encoding at
        this resolution is still too large, there is no reason to perform a
        full binary search; the caller can immediately try a smaller width.
        """

        low = self.settings.min_crf
        high = self.settings.max_crf

        best_crf: int | None = None
        best_size: int | None = None
        best_bytes: bytes | None = None

        with tempfile.TemporaryDirectory(prefix="image-converter-") as temp_dir:
            temp_root = Path(temp_dir)

            max_candidate = temp_root / f"candidate-{high}.avif"
            encode_avif(
                source,
                max_candidate,
                crf=high,
                width=width,
                cpu_used=self.settings.cpu_used,
            )

            max_size = max_candidate.stat().st_size
            if max_size > self.settings.target_bytes:
                return None

            # max_crf fits, so at least one valid result exists.
            best_crf = high
            best_size = max_size
            best_bytes = max_candidate.read_bytes()

            # Search only the range with potentially better quality.
            high -= 1

            while low <= high:
                crf = (low + high) // 2
                candidate = temp_root / f"candidate-{crf}.avif"

                encode_avif(
                    source,
                    candidate,
                    crf=crf,
                    width=width,
                    cpu_used=self.settings.cpu_used,
                )

                size = candidate.stat().st_size

                if size <= self.settings.target_bytes:
                    # It fits. Keep it, then lower CRF to spend more bytes on
                    # quality without crossing the configured ceiling.
                    best_crf = crf
                    best_size = size
                    best_bytes = candidate.read_bytes()
                    high = crf - 1
                else:
                    low = crf + 1

        if best_crf is None or best_size is None or best_bytes is None:
            return None

        fd, temporary_name = tempfile.mkstemp(suffix=".avif")
        os.close(fd)
        persistent = Path(temporary_name)
        persistent.write_bytes(best_bytes)
        return persistent, best_size, best_crf
