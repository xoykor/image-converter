from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from image_converter.core.ffmpeg import encode_avif, probe_dimensions
from image_converter.core.models import ConversionResult, ConversionSettings


class TargetSizeEncoder:
    """Find the highest AVIF quality that fits a byte ceiling."""

    # Original resolution is always attempted first. Downscaled widths are
    # generated from the source width only if the previous level cannot fit.
    DOWNSCALE_FACTORS = (0.90, 0.82, 0.74, 0.66)

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

        source_width, source_height = probe_dimensions(source)
        candidate_widths: list[int | None] = [None]

        if self.settings.allow_downscale:
            for factor in self.DOWNSCALE_FACTORS:
                width = max(2, int(source_width * factor))
                width -= width % 2
                if width < source_width and width not in candidate_widths:
                    candidate_widths.append(width)

        try:
            for width in candidate_widths:
                attempt = self._best_for_width(source, width)
                if attempt is None:
                    continue

                temp_file, final_size, crf = attempt
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
                    "Não foi possível atingir o tamanho alvo nem no CRF máximo "
                    "e com o menor fallback de resolução."
                ),
            )
        except Exception as exc:
            return ConversionResult(
                source=source,
                output=output,
                status="failed",
                original_bytes=original_bytes,
                error=str(exc),
            )

    def _best_for_width(
        self,
        source: Path,
        width: int | None,
    ) -> tuple[Path, int, int] | None:
        low = self.settings.min_crf
        high = self.settings.max_crf

        best_crf: int | None = None
        best_size: int | None = None
        best_bytes: bytes | None = None

        with tempfile.TemporaryDirectory(prefix="image-converter-") as temp_dir:
            temp_root = Path(temp_dir)

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
                    # It fits. Keep it, then lower CRF to see whether we can
                    # spend more bytes on quality without crossing the ceiling.
                    best_crf = crf
                    best_size = size
                    best_bytes = candidate.read_bytes()
                    high = crf - 1
                else:
                    low = crf + 1

            if best_crf is None or best_size is None or best_bytes is None:
                return None

        persistent = Path(tempfile.mkstemp(suffix=".avif")[1])
        persistent.write_bytes(best_bytes)
        return persistent, best_size, best_crf
