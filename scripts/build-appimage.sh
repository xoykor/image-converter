#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ARCH="${ARCH:-x86_64}"
APP_NAME="ImageConverter"
APPDIR="$ROOT_DIR/build/${APP_NAME}.AppDir"
PYINSTALLER_DIST="$ROOT_DIR/dist/image-converter"
OUTPUT_DIR="$ROOT_DIR/dist-appimage"
OUTPUT_FILE="${OUTPUT_FILE:-$OUTPUT_DIR/${APP_NAME}-${ARCH}.AppImage}"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg is required" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe is required" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required" >&2; exit 1; }

python3 -c "import PyInstaller" >/dev/null 2>&1 || {
    echo "PyInstaller is required. Install it with: python -m pip install pyinstaller" >&2
    exit 1
}

rm -rf "$APPDIR" "$PYINSTALLER_DIST"
mkdir -p     "$APPDIR/usr/bin"     "$APPDIR/usr/lib/image-converter"     "$APPDIR/usr/lib/ffmpeg"     "$APPDIR/usr/lib/ffmpeg-deps"     "$APPDIR/usr/share/applications"     "$APPDIR/usr/share/icons/hicolor/scalable/apps"     "$OUTPUT_DIR"

python3 -m PyInstaller     --noconfirm     --clean     --windowed     --onedir     --name image-converter     --paths "$ROOT_DIR/src"     "$ROOT_DIR/src/image_converter/app.py"

cp -a "$PYINSTALLER_DIST/." "$APPDIR/usr/lib/image-converter/"

cp -L "$(command -v ffmpeg)" "$APPDIR/usr/lib/ffmpeg/ffmpeg.real"
cp -L "$(command -v ffprobe)" "$APPDIR/usr/lib/ffmpeg/ffprobe.real"

copy_ffmpeg_dependencies() {
    local executable="$1"

    ldd "$executable"         | awk '/=> \/[^ ]+/ {print $3} /^\// {print $1}'         | sort -u         | while IFS= read -r library; do
            [[ -n "$library" ]] || continue

            case "$(basename "$library")" in
                libc.so.*|libm.so.*|libdl.so.*|libpthread.so.*|librt.so.*|ld-linux-*.so.*)
                    continue
                    ;;
            esac

            cp -L -n "$library" "$APPDIR/usr/lib/ffmpeg-deps/" || true
        done
}

copy_ffmpeg_dependencies "$(command -v ffmpeg)"
copy_ffmpeg_dependencies "$(command -v ffprobe)"

cat > "$APPDIR/usr/bin/ffmpeg" <<'EOF'
#!/bin/sh
APPDIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
export LD_LIBRARY_PATH="$APPDIR/usr/lib/ffmpeg-deps${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$APPDIR/usr/lib/ffmpeg/ffmpeg.real" "$@"
EOF

cat > "$APPDIR/usr/bin/ffprobe" <<'EOF'
#!/bin/sh
APPDIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
export LD_LIBRARY_PATH="$APPDIR/usr/lib/ffmpeg-deps${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$APPDIR/usr/lib/ffmpeg/ffprobe.real" "$@"
EOF

chmod +x "$APPDIR/usr/bin/ffmpeg" "$APPDIR/usr/bin/ffprobe"

install -Dm644     "$ROOT_DIR/packaging/appimage/image-converter.desktop"     "$APPDIR/usr/share/applications/image-converter.desktop"

install -Dm644     "$ROOT_DIR/packaging/appimage/image-converter.svg"     "$APPDIR/usr/share/icons/hicolor/scalable/apps/image-converter.svg"

cp "$ROOT_DIR/packaging/appimage/image-converter.desktop" "$APPDIR/image-converter.desktop"
cp "$ROOT_DIR/packaging/appimage/image-converter.svg" "$APPDIR/image-converter.svg"
ln -sfn image-converter.svg "$APPDIR/.DirIcon"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export PATH="$HERE/usr/bin:$PATH"
exec "$HERE/usr/lib/image-converter/image-converter" "$@"
EOF
chmod +x "$APPDIR/AppRun"

APPIMAGETOOL="$ROOT_DIR/build/appimagetool-${ARCH}.AppImage"
if [[ ! -x "$APPIMAGETOOL" ]]; then
    case "$ARCH" in
        x86_64)
            TOOL_NAME="appimagetool-x86_64.AppImage"
            ;;
        aarch64)
            TOOL_NAME="appimagetool-aarch64.AppImage"
            ;;
        *)
            echo "Unsupported AppImage architecture: $ARCH" >&2
            exit 1
            ;;
    esac

    curl -L --fail --retry 3         "https://github.com/AppImage/AppImageKit/releases/download/continuous/$TOOL_NAME"         -o "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

rm -f "$OUTPUT_FILE"
ARCH="$ARCH" "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT_FILE"

chmod +x "$OUTPUT_FILE"
echo
echo "AppImage created: $OUTPUT_FILE"
du -h "$OUTPUT_FILE"
