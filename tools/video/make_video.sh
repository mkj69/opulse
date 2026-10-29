#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

SITE_DIR=${SITE_DIR:-tools/video/output/site}
FRAMES=${FRAMES:-tools/video/output/frames}
OUT=${OUT:-docs/assets/video}
SHEETS=${SHEETS:-tools/video/output/sheets}
PY=${PY:-$(command -v python3)}
read -r -a themes <<< "${THEMES:-light dark}"
if (( ${#themes[@]} == 0 )); then
    echo "THEMES must contain light, dark, or both" >&2
    exit 1
fi
for theme in "${themes[@]}"; do
    if [[ $theme != light && $theme != dark ]]; then
        echo "Unknown video theme: $theme" >&2
        exit 1
    fi
done

if [[ ${SKIP_BUILD:-0} != 1 ]]; then
    PYTHONPATH="$PWD/src" "$PY" tools/build_playground.py
    "$PY" -m mkdocs build -q -f mkdocs.local.yml -d "$SITE_DIR"
    "$PY" -m mkdocs build -q -f mkdocs.zh.yml -d "$SITE_DIR/zh"
    if [[ -n ${MASTER_TREE:-} ]]; then
        mkdir -p "$SITE_DIR/m"
        SITE_DIR=$(realpath "$SITE_DIR")
        MASTER_TREE=$(realpath "$MASTER_TREE")
        (cd "$MASTER_TREE" && PYTHONPATH="$MASTER_TREE/src" "$PY" -m mkdocs build -q -f mkdocs.local.yml -d "$SITE_DIR/m")
    fi
fi

server_pid=
stop_server() {
    if [[ -n $server_pid ]]; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
}
trap stop_server EXIT

if ! curl -sS --max-time 2 -o /dev/null http://localhost:8770/; then
    python3 -m http.server 8770 --directory "$SITE_DIR" >/dev/null 2>&1 &
    server_pid=$!
    for _ in {1..50}; do
        if curl -sS --max-time 2 -o /dev/null http://localhost:8770/; then
            break
        fi
        if ! kill -0 "$server_pid" 2>/dev/null; then
            echo "HTTP server on port 8770 exited" >&2
            exit 1
        fi
        sleep 0.1
    done
    curl -sS --max-time 2 -o /dev/null http://localhost:8770/
fi

for theme in "${themes[@]}"; do
    "$PY" tools/video/record.py --theme "$theme" --output "$FRAMES" "$@"
    "$PY" tools/video/compose.py --theme "$theme" --frames "$FRAMES" --output "$OUT"

    theme_sheets="$SHEETS/$theme"
    mkdir -p "$theme_sheets/frames"
    rm -f "$theme_sheets/frames/"*.png "$theme_sheets/"sheet*.png
    ffmpeg -hide_banner -loglevel error -y -i "$OUT/opulse-$theme.mp4" -vf fps=1 -start_number 0 "$theme_sheets/frames/%04d.png"

    mapfile -t extracted < <(find "$theme_sheets/frames" -maxdepth 1 -name '*.png' -printf '%f\n' | sort)
    if (( ${#extracted[@]} == 0 )); then
        echo "No frames extracted from $OUT/opulse-$theme.mp4" >&2
        exit 1
    fi
    for ((first = 0, sheet = 1; first < ${#extracted[@]}; first += 16, sheet++)); do
        ffmpeg -hide_banner -loglevel error -y -start_number "$first" -i "$theme_sheets/frames/%04d.png" \
            -vf "scale=480:-2,drawtext=text='%{eif\\:n+${first}\\:d}':x=12:y=12:fontcolor=white:fontsize=28:box=1:boxcolor=black@0.7,tile=4x4" \
            -frames:v 1 "$theme_sheets/sheet${sheet}.png"
    done

    printf '%s duration: ' "$theme"
    ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT/opulse-$theme.mp4"
    ls -lh "$OUT/opulse-$theme.mp4" "$OUT/opulse-$theme.webm" "$OUT/poster-$theme.jpg" "$theme_sheets/"sheet*.png
done
ls -lh "$OUT/captions.en.vtt" "$OUT/captions.zh.vtt"
