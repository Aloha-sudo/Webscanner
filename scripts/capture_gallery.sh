#!/bin/sh
# Capture the actual local frontend using intercepted synthetic API fixtures.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
gallery_output="$project_dir/docs/images"
playwright_version=1.64.0
if ! command -v docker >/dev/null 2>&1; then
  echo 'Docker is required for the isolated screenshot browser.' >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 is required to prepare the GitHub gallery archive.' >&2
  exit 1
fi
mkdir -p "$gallery_output"
echo 'Capturing 14 WebScanner screens in dark mode. The app must already be open at http://127.0.0.1:3000.'
echo 'Only synthetic API responses are used. No real projects or scan jobs are changed.'
docker run --rm --init --network host --ipc host \
  --user "$(id -u):$(id -g)" \
  -v "$project_dir:/work:ro" \
  -v "$gallery_output:/output" \
  -e "GALLERY_URL=${GALLERY_URL:-http://127.0.0.1:3000}" \
  -e GALLERY_OUTPUT=/output/gallery \
  -e "PLAYWRIGHT_VERSION=$playwright_version" \
  "mcr.microsoft.com/playwright:v${playwright_version}-noble" \
  /bin/bash -ec 'npm install --prefix /tmp/webscanner-gallery-tools --cache /tmp/webscanner-gallery-cache --no-save --package-lock=false --ignore-scripts "playwright@$PLAYWRIGHT_VERSION"; NODE_PATH=/tmp/webscanner-gallery-tools/node_modules node /work/scripts/gallery/capture.cjs'
python3 "$project_dir/scripts/gallery/publish.py"
