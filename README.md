# image-converter

Desktop batch image converter focused on fitting large image collections into a predictable storage budget.

The first milestone targets the use case that motivated the project: hundreds of thousands of card images that need to be converted to AVIF while keeping each file near a configurable size budget, such as 10 KiB.

## Current features

- Qt desktop interface with folder pickers and batch progress.
- AVIF output through FFmpeg/libaom.
- Per-image binary search for the **best CRF that fits the requested size**.
- Keeps the original resolution first; optional progressive downscaling is only used when required.
- Parallel conversion with a configurable worker count.
- Pause, resume and cancel controls.
- Skips already converted files when requested.
- Preserves the input directory structure.
- Incremental CSV report so long jobs can be inspected after interruption.
- Removes source metadata from generated files.

## Architecture

The UI does not perform media encoding. It delegates to a small conversion core:

```text
PySide6 UI
   |
   v
BatchWorker (QThread)
   |
   v
BatchConverter
   |
   +--> TargetSizeEncoder
          |
          +--> FFmpeg/libaom
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and roadmap.

## CachyOS / Arch Linux

Install the system dependency:

```fish
sudo pacman -S ffmpeg python
```

Create a virtual environment and install the app:

```fish
python -m venv .venv
source .venv/bin/activate.fish
python -m pip install -e .
```

Run:

```fish
image-converter
```

You can verify that FFmpeg has the required AV1 encoder with:

```fish
ffmpeg -hide_banner -encoders | grep libaom-av1
```

## Size target

A target of `10 KiB` means the encoder searches for the lowest CRF (highest quality) whose generated AVIF is at or below `10 * 1024` bytes.

This is deliberately different from applying one quality setting to every image: simple images retain more quality, while complex images are compressed more aggressively.

## Status

This is an initial working architecture/MVP. The next milestones are visual before/after previews, global-average budget mode, resumable manifests and packaged Linux builds.
