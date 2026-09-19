from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from image_converter.core.models import ConversionResult, ConversionSettings
from image_converter.ui.batch_worker import BatchWorker


def _human_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024.0 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024.0
    return f"{amount:.1f} TiB"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Image Converter")
        self.resize(920, 700)

        self._thread: QThread | None = None
        self._worker: BatchWorker | None = None
        self._paused = False
        self._close_when_finished = False

        self._total = 0
        self._processed = 0
        self._original_bytes = 0
        self._output_bytes = 0
        self._failed = 0

        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Image Converter")
        title.setObjectName("title")
        subtitle = QLabel(
            "Conversão em massa com orçamento de bytes e qualidade adaptativa."
        )
        subtitle.setObjectName("subtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        paths_card = self._card()
        paths_layout = QFormLayout(paths_card)
        paths_layout.setSpacing(12)

        self.input_edit = QLineEdit()
        self.output_edit = QLineEdit()

        paths_layout.addRow(
            "Pasta de entrada",
            self._path_picker(self.input_edit, self._choose_input),
        )
        paths_layout.addRow(
            "Pasta de saída",
            self._path_picker(self.output_edit, self._choose_output),
        )

        layout.addWidget(paths_card)

        settings_card = self._card()
        settings = QGridLayout(settings_card)
        settings.setHorizontalSpacing(24)
        settings.setVerticalSpacing(12)

        self.target_spin = QSpinBox()
        self.target_spin.setRange(1, 1024 * 1024)
        self.target_spin.setValue(10)
        self.target_spin.setSuffix(" KiB")

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, max(1, os.cpu_count() or 1))
        self.workers_spin.setValue(min(4, max(1, (os.cpu_count() or 4) // 2)))

        self.downscale_check = QCheckBox("Reduzir resolução apenas se necessário")
        self.downscale_check.setChecked(True)

        self.skip_check = QCheckBox("Ignorar AVIF já convertido dentro do alvo")
        self.skip_check.setChecked(True)

        settings.addWidget(QLabel("Tamanho máximo por imagem"), 0, 0)
        settings.addWidget(self.target_spin, 0, 1)
        settings.addWidget(QLabel("Conversões paralelas"), 0, 2)
        settings.addWidget(self.workers_spin, 0, 3)
        settings.addWidget(self.downscale_check, 1, 0, 1, 2)
        settings.addWidget(self.skip_check, 1, 2, 1, 2)

        layout.addWidget(settings_card)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Iniciar conversão")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self._start)

        self.pause_button = QPushButton("Pausar")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._toggle_pause)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)

        actions.addWidget(self.start_button)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        progress_card = self._card()
        progress_layout = QVBoxLayout(progress_card)

        self.status_label = QLabel("Pronto.")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        stats = QGridLayout()
        self.processed_value = QLabel("0 / 0")
        self.input_value = QLabel("0 B")
        self.output_value = QLabel("0 B")
        self.average_value = QLabel("0 B")
        self.failed_value = QLabel("0")

        stats.addWidget(QLabel("Processadas"), 0, 0)
        stats.addWidget(self.processed_value, 1, 0)
        stats.addWidget(QLabel("Entrada acumulada"), 0, 1)
        stats.addWidget(self.input_value, 1, 1)
        stats.addWidget(QLabel("Saída acumulada"), 0, 2)
        stats.addWidget(self.output_value, 1, 2)
        stats.addWidget(QLabel("Média de saída"), 0, 3)
        stats.addWidget(self.average_value, 1, 3)
        stats.addWidget(QLabel("Falhas"), 0, 4)
        stats.addWidget(self.failed_value, 1, 4)

        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress)
        progress_layout.addLayout(stats)

        layout.addWidget(progress_card)

        self.log = QListWidget()
        self.log.setAlternatingRowColors(True)
        layout.addWidget(self.log, 1)

    @staticmethod
    def _card() -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        return frame

    @staticmethod
    def _path_picker(edit: QLineEdit, callback) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        button = QPushButton("Procurar")
        button.clicked.connect(callback)

        row.addWidget(edit, 1)
        row.addWidget(button)
        return widget

    def _choose_input(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Pasta de entrada")
        if path:
            self.input_edit.setText(path)
            if not self.output_edit.text().strip():
                self.output_edit.setText(str(Path(path).with_name(Path(path).name + "_avif")))

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Pasta de saída")
        if path:
            self.output_edit.setText(path)

    def _start(self) -> None:
        input_text = self.input_edit.text().strip()
        output_text = self.output_edit.text().strip()

        if not input_text:
            QMessageBox.warning(self, "Entrada inválida", "Escolha uma pasta de entrada.")
            return

        if not output_text:
            QMessageBox.warning(self, "Saída inválida", "Escolha uma pasta de saída.")
            return

        input_dir = Path(input_text).expanduser()
        output_dir = Path(output_text).expanduser()

        if not input_dir.is_dir():
            QMessageBox.warning(self, "Entrada inválida", "Escolha uma pasta de entrada.")
            return

        try:
            if output_dir.resolve().is_relative_to(input_dir.resolve()):
                QMessageBox.warning(
                    self,
                    "Saída dentro da entrada",
                    "Use uma pasta de saída fora da árvore de entrada para evitar "
                    "que resultados sejam reencontrados em execuções futuras.",
                )
                return
        except FileNotFoundError:
            pass

        settings = ConversionSettings(
            input_dir=input_dir.resolve(),
            output_dir=output_dir.resolve(),
            target_bytes=self.target_spin.value() * 1024,
            workers=self.workers_spin.value(),
            allow_downscale=self.downscale_check.isChecked(),
            skip_existing=self.skip_check.isChecked(),
        )

        self._reset_stats()
        self._set_running(True)

        thread = QThread(self)
        worker = BatchWorker(settings)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.batch_started.connect(self._on_batch_started)
        worker.file_finished.connect(self._on_file_finished)
        worker.status_changed.connect(self.status_label.setText)
        worker.finished.connect(self._on_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _toggle_pause(self) -> None:
        if self._worker is None:
            return

        if self._paused:
            self._worker.resume()
            self._paused = False
            self.pause_button.setText("Pausar")
        else:
            self._worker.pause()
            self._paused = True
            self.pause_button.setText("Retomar")

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.cancel_button.setEnabled(False)

    def _on_batch_started(self, total: int) -> None:
        self._total = total
        self.processed_value.setText(f"0 / {total:,}".replace(",", "."))
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(0)

    def _on_file_finished(self, result: ConversionResult) -> None:
        self._processed += 1
        self._original_bytes += result.original_bytes

        if result.final_bytes is not None:
            self._output_bytes += result.final_bytes

        if result.status == "failed":
            self._failed += 1

        self.progress.setValue(self._processed)
        self._refresh_stats()

        if result.status == "ok":
            line = (
                f"{result.source.name}  •  "
                f"{_human_bytes(result.original_bytes)} → {_human_bytes(result.final_bytes or 0)}"
                f"  •  CRF {result.crf}  •  {result.width}×{result.height}"
            )
        elif result.status == "skipped":
            line = f"{result.source.name}  •  já convertido"
        else:
            line = f"{result.source.name}  •  FALHA: {result.error or result.status}"

        self.log.insertItem(0, line)
        while self.log.count() > 250:
            self.log.takeItem(self.log.count() - 1)

    def _on_finished(self, success: bool, message: str) -> None:
        self.status_label.setText(message)

        if not success and "cancelada" not in message.lower():
            QMessageBox.warning(self, "Conversão", message)

    def _on_thread_finished(self) -> None:
        self._set_running(False)
        self._worker = None
        self._thread = None
        self._paused = False
        self.pause_button.setText("Pausar")

        if self._close_when_finished:
            self._close_when_finished = False
            self.close()

    def _refresh_stats(self) -> None:
        total_text = f"{self._processed:,} / {self._total:,}".replace(",", ".")
        self.processed_value.setText(total_text)
        self.input_value.setText(_human_bytes(self._original_bytes))
        self.output_value.setText(_human_bytes(self._output_bytes))

        average = self._output_bytes // self._processed if self._processed else 0
        self.average_value.setText(_human_bytes(average))
        self.failed_value.setText(str(self._failed))

    def _reset_stats(self) -> None:
        self._total = 0
        self._processed = 0
        self._original_bytes = 0
        self._output_bytes = 0
        self._failed = 0
        self.log.clear()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._refresh_stats()

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.cancel_button.setEnabled(running)
        self.input_edit.setEnabled(not running)
        self.output_edit.setEnabled(not running)
        self.target_spin.setEnabled(not running)
        self.workers_spin.setEnabled(not running)
        self.downscale_check.setEnabled(not running)
        self.skip_check.setEnabled(not running)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: palette(window);
            }
            QLabel#title {
                font-size: 28px;
                font-weight: 700;
            }
            QLabel#subtitle {
                font-size: 14px;
                color: palette(mid);
            }
            QFrame#card {
                border: 1px solid palette(midlight);
                border-radius: 12px;
                background: palette(base);
                padding: 12px;
            }
            QPushButton {
                min-height: 34px;
                padding: 0 14px;
                border-radius: 8px;
            }
            QPushButton#primaryButton {
                font-weight: 700;
                min-width: 150px;
            }
            QLineEdit, QSpinBox {
                min-height: 32px;
                padding: 0 8px;
                border-radius: 7px;
                border: 1px solid palette(midlight);
            }
            QProgressBar {
                min-height: 16px;
                border-radius: 8px;
                text-align: center;
            }
            QListWidget {
                border: 1px solid palette(midlight);
                border-radius: 10px;
                padding: 6px;
            }
            """
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._worker is None:
            event.accept()
            return

        answer = QMessageBox.question(
            self,
            "Conversão em andamento",
            "Cancelar a conversão e fechar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer == QMessageBox.StandardButton.Yes:
            self._close_when_finished = True
            self._worker.cancel()
            self.status_label.setText("Cancelando antes de fechar…")
            event.ignore()
        else:
            event.ignore()
