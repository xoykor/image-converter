from __future__ import annotations

import csv
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from image_converter.core.batch import BatchConverter
from image_converter.core.models import ConversionResult, ConversionSettings


class BatchWorker(QObject):
    batch_started = Signal(int)
    file_finished = Signal(object)
    status_changed = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, settings: ConversionSettings) -> None:
        super().__init__()
        self.settings = settings

        self._pause_event = threading.Event()
        self._pause_event.set()

        self._cancel_event = threading.Event()

    @Slot()
    def run(self) -> None:
        report_path = self.settings.output_dir / "conversion_report.csv"

        try:
            self.settings.output_dir.mkdir(parents=True, exist_ok=True)

            converter = BatchConverter(
                self.settings,
                pause_event=self._pause_event,
                cancel_event=self._cancel_event,
            )

            self.status_changed.emit("Procurando imagens…")
            images = converter.discover()
            self.batch_started.emit(len(images))

            if not images:
                self.finished.emit(True, "Nenhuma imagem compatível encontrada.")
                return

            self.status_changed.emit("Convertendo…")

            with report_path.open("w", newline="", encoding="utf-8") as report_file:
                writer = csv.writer(report_file)
                writer.writerow(
                    [
                        "status",
                        "source",
                        "output",
                        "original_bytes",
                        "final_bytes",
                        "crf",
                        "width",
                        "height",
                        "error",
                    ]
                )
                report_file.flush()

                for result in converter.convert_all(images):
                    self._write_result(writer, result)
                    report_file.flush()
                    self.file_finished.emit(result)

                    if self._cancel_event.is_set():
                        self.finished.emit(False, "Conversão cancelada.")
                        return

            self.finished.emit(True, f"Concluído. Relatório: {report_path}")

        except Exception as exc:
            self.finished.emit(False, f"Erro: {exc}")

    def pause(self) -> None:
        self._pause_event.clear()
        self.status_changed.emit("Pausado — conversões já iniciadas podem terminar.")

    def resume(self) -> None:
        self._pause_event.set()
        self.status_changed.emit("Convertendo…")

    def cancel(self) -> None:
        self._cancel_event.set()
        # Release tasks currently blocked on pause so they can observe cancel.
        self._pause_event.set()
        self.status_changed.emit("Cancelando…")

    @staticmethod
    def _write_result(writer: csv.writer, result: ConversionResult) -> None:
        writer.writerow(
            [
                result.status,
                str(result.source),
                str(result.output),
                result.original_bytes,
                result.final_bytes or "",
                result.crf or "",
                result.width or "",
                result.height or "",
                result.error or "",
            ]
        )
