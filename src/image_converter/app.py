from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from image_converter.core.ffmpeg import FFmpegError, ensure_ffmpeg_available
from image_converter.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Image Converter")
    app.setOrganizationName("xoykor")

    try:
        ensure_ffmpeg_available()
    except FFmpegError as exc:
        # The main window can still explain the missing dependency, but starting
        # without an encoder would make the primary action unusable.
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "FFmpeg não encontrado",
            f"{exc}\n\nNo CachyOS/Arch: sudo pacman -S ffmpeg",
        )
        return 1

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
