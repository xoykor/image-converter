from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    """Raised when FFmpeg/ffprobe cannot perform the requested operation."""


def ensure_ffmpeg_available() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise FFmpegError(
            "Dependência ausente: " + ", ".join(missing)
        )


def probe_dimensions(path: Path) -> tuple[int, int]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(path),
    ]

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        raise FFmpegError(completed.stderr.strip() or f"Falha ao ler {path}")

    try:
        data = json.loads(completed.stdout)
        stream = data["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FFmpegError(f"Dimensões inválidas em {path}") from exc


def encode_avif(
    source: Path,
    destination: Path,
    *,
    crf: int,
    width: int | None,
    cpu_used: int,
) -> None:
    """Encode one still image with libaom AV1.

    Width is optional. When provided, FFmpeg keeps the source aspect ratio and
    rounds the generated height to a codec-friendly even number.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map_metadata",
        "-1",
        "-frames:v",
        "1",
    ]

    if width is not None:
        command += [
            "-vf",
            f"scale={width}:-2:flags=lanczos",
        ]

    command += [
        "-c:v",
        "libaom-av1",
        "-still-picture",
        "1",
        "-cpu-used",
        str(cpu_used),
        "-row-mt",
        "1",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        str(crf),
        "-b:v",
        "0",
        str(destination),
    ]

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        message = completed.stderr.strip() or "FFmpeg encerrou com erro."
        raise FFmpegError(message)
