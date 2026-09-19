from __future__ import annotations

import os
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Iterator

from image_converter.core.converter import TargetSizeEncoder
from image_converter.core.models import ConversionResult, ConversionSettings


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


def discover_images(root: Path) -> list[Path]:
    """Discover input images deterministically.

    600k Path objects are acceptable for the first milestone and give the UI an
    exact progress denominator. A persistent/streaming manifest is planned.
    """

    images: list[Path] = []

    for current_root, _dirs, files in os.walk(root):
        current = Path(current_root)
        for filename in files:
            path = current / filename
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                images.append(path)

    images.sort()
    return images


def output_path_for(source: Path, settings: ConversionSettings) -> Path:
    relative = source.relative_to(settings.input_dir)
    return (settings.output_dir / relative).with_suffix(".avif")


class BatchConverter:
    """Bounded concurrent batch conversion.

    Only a small number of Future objects are in flight. This matters for the
    intended hundreds-of-thousands-of-files workload.
    """

    def __init__(
        self,
        settings: ConversionSettings,
        *,
        pause_event: threading.Event,
        cancel_event: threading.Event,
    ) -> None:
        self.settings = settings
        self.pause_event = pause_event
        self.cancel_event = cancel_event
        self.encoder = TargetSizeEncoder(settings)

    def discover(self) -> list[Path]:
        return discover_images(self.settings.input_dir)

    def convert_all(self, images: list[Path]) -> Iterator[ConversionResult]:
        workers = max(1, self.settings.workers)
        max_pending = max(workers, workers * 2)

        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="image-converter",
        ) as executor:
            source_iter = iter(images)
            pending: set[Future[ConversionResult]] = set()

            def submit_next() -> bool:
                if self.cancel_event.is_set():
                    return False

                try:
                    source = next(source_iter)
                except StopIteration:
                    return False

                pending.add(executor.submit(self._convert_one, source))
                return True

            while len(pending) < max_pending and submit_next():
                pass

            while pending:
                done, still_pending = wait(
                    pending,
                    return_when=FIRST_COMPLETED,
                )
                pending = set(still_pending)

                for future in done:
                    yield future.result()

                    if not self.cancel_event.is_set():
                        submit_next()

                if self.cancel_event.is_set():
                    for future in pending:
                        future.cancel()
                    break

    def _convert_one(self, source: Path) -> ConversionResult:
        # A cleared event means "paused". Running FFmpeg processes finish, but
        # no new file begins encoding until resume() sets the event again.
        self.pause_event.wait()

        if self.cancel_event.is_set():
            return ConversionResult(
                source=source,
                output=output_path_for(source, self.settings),
                status="cancelled",
                original_bytes=source.stat().st_size,
            )

        output = output_path_for(source, self.settings)
        return self.encoder.convert(source, output)
