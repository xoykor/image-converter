# image-converter

Desktop batch image converter focused on fitting **large image collections into a predictable storage budget**. Instead of applying one fixed quality setting to every file, the encoder searches per image for a configuration that stays within a requested size target whenever possible.

The first milestone targets the use case that motivated the project: hundreds of thousands of card images that need to be converted to AVIF while keeping each file near a configurable size budget, such as 10 KiB.

## Quick start

Requirements:

- Python 3.11+;
- PySide6;
- FFmpeg with an AVIF-capable encoder available.

Development install:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
image-converter
```

On fish, activate the environment with:

```fish
source .venv/bin/activate.fish
```

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

## How target-size encoding works

For each input image, the converter attempts to preserve the original dimensions while searching the encoder quality range for the best candidate that fits the configured byte budget. If the target cannot be reached at the current dimensions and progressive downscaling is enabled, the process retries at smaller dimensions.

This makes the target a **budget**, not a promise of identical visual quality across unrelated source images.

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

## AppImage

Every AppImage workflow run produces a portable x86_64 artifact containing the
application, PySide6 runtime and FFmpeg/ffprobe runtime required by the encoder.

To build it locally on CachyOS:

```fish
sudo pacman -S ffmpeg python
python -m pip install -e . pyinstaller
bash scripts/build-appimage.sh
```

The result is written to:

```text
dist-appimage/ImageConverter-x86_64.AppImage
```

Run it with:

```fish
chmod +x dist-appimage/ImageConverter-x86_64.AppImage
./dist-appimage/ImageConverter-x86_64.AppImage
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


## Limitations

- Extremely small targets can require substantial downscaling or visible quality loss.
- Encoding speed depends heavily on FFmpeg/libaom settings, image dimensions and worker count.
- A successful conversion within a byte target does not imply equivalent perceptual quality between different images.
- Keep source files until a batch has been inspected and the CSV report reviewed.

## License

GNU General Public License v3.0. See [LICENSE](LICENSE).
