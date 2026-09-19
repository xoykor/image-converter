# Architecture

## Goals

image-converter is designed for very large batches, including collections with hundreds of thousands of images. The main constraint is not merely "compress images": it is to achieve a **storage budget while preserving as much useful visual information as possible**.

The initial implementation therefore treats target size as a first-class encoding parameter.

## Components

### `ui/main_window.py`

Qt presentation layer.

Responsibilities:

- collect input/output directories and encoding options;
- show progress and aggregate statistics;
- expose start, pause/resume and cancel controls;
- display recent per-file results.

It must not contain FFmpeg command construction or target-size search logic.

### `ui/batch_worker.py`

Adapter between Qt and the conversion core.

A long-running conversion lives in a dedicated `QThread`. The worker owns thread-safe pause/cancel events and emits coarse-grained UI signals.

The worker also writes `conversion_report.csv` incrementally. A crash after a long run therefore does not discard all conversion metadata.

### `core/ffmpeg.py`

Thin FFmpeg boundary.

Responsibilities:

- verify `ffmpeg` and `ffprobe` availability;
- probe source dimensions;
- invoke libaom AV1 still-image encoding;
- remove metadata;
- optionally rescale with Lanczos.

No Qt dependency is allowed here.

### `core/converter.py`

Conversion policy.

`TargetSizeEncoder` performs a binary search over CRF:

```text
target bytes
    |
    v
try CRF midpoint
    |
    +-- output too large --> raise CRF
    |
    +-- fits -----------> remember it, try lower CRF
```

The result is the highest quality encountered that still fits the requested byte ceiling.

Resolution policy is intentionally conservative:

1. original dimensions;
2. 90% width;
3. 82% width;
4. 74% width;
5. 66% width.

A lower resolution is only considered if no encoding at the previous resolution can fit the configured ceiling.

### `core/batch.py`

Batch orchestration.

- recursively discovers supported images;
- maps source paths to mirrored AVIF output paths;
- executes conversions concurrently;
- keeps only a bounded number of futures in flight so job scheduling does not itself scale to hundreds of thousands of Future objects;
- yields completed results to the UI worker.

## Data flow

```text
input tree
   |
scan
   v
Path list
   |
bounded ThreadPoolExecutor
   |
   +--> image A --> TargetSizeEncoder --> FFmpeg
   +--> image B --> TargetSizeEncoder --> FFmpeg
   +--> image C --> TargetSizeEncoder --> FFmpeg
   |
   v
ConversionResult
   |
   +--> CSV checkpoint
   +--> Qt signals
   +--> aggregate stats
```

## Why FFmpeg + libaom

FFmpeg is mature, available on Arch/CachyOS and exposes libaom AV1 still-image encoding without requiring the application to bundle a codec implementation.

The boundary is isolated so another backend (libavif, rav1e, SVT-AV1 or platform APIs) can be added later.

## Storage-budget roadmap

A strict 10 KiB ceiling for every image is useful, but it is not optimal for a collection where only the **total** size matters.

A future "global budget" mode will maintain a byte ledger:

```text
total budget = 8 GiB
processed output = 2.1 GiB
remaining images = 410,000

dynamic next-image allowance =
    remaining budget / remaining images
```

Complex images can consume more bytes while easy images compensate by consuming fewer. Quality floors and maximum per-image allowances will prevent pathological allocation.

## Large-batch considerations

For the intended ~600k-file workload:

- output folders mirror the source tree rather than flattening all names;
- already valid outputs can be skipped;
- scheduling is bounded to roughly `2 * worker_count` active futures;
- CSV rows are flushed as each file completes;
- the conversion core has no GUI dependency;
- pause/cancel flags are thread-safe.

Future work will add a persistent SQLite manifest so discovery can also resume without rescanning the entire tree.

## Planned milestones

1. Working target-size batch encoder and Qt shell.
2. Before/after preview with zoom for text-heavy images.
3. Global-average byte-budget mode.
4. SQLite resumable job manifest and duplicate hashing.
5. Additional output formats (WebP/JPEG/PNG).
6. Presets and per-format encoder tuning.
7. Linux packaging (AppImage/Flatpak).
