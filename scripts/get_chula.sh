#!/usr/bin/env bash
# Download the Chula RBC-12 dataset into external/ (git-ignored) and check its license.
# Usage: bash scripts/get_chula.sh
set -euo pipefail

REPO_URL="https://github.com/Chula-PIC-Lab/Chula-RBC-12-Dataset"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/external/Chula-RBC-12-Dataset"

mkdir -p "$ROOT/external"
if [ -d "$DEST/.git" ]; then
  echo "[get_chula] already present: $DEST (pulling latest)"
  git -C "$DEST" pull --ff-only 2>/dev/null || echo "[get_chula] pull failed, keeping local copy"
else
  echo "[get_chula] cloning $REPO_URL"
  git clone --depth 1 "$REPO_URL" "$DEST"
fi

# License check: the dataset is published under the MIT License (Chula PIC Lab, 2021).
if [ ! -f "$DEST/LICENSE" ]; then
  echo "[get_chula] ERROR: no LICENSE file found, do not use the data" >&2
  exit 1
fi
if grep -q "MIT License" "$DEST/LICENSE"; then
  echo "[get_chula] license OK: $(head -1 "$DEST/LICENSE") / $(grep -m1 Copyright "$DEST/LICENSE")"
else
  echo "[get_chula] WARNING: license is not MIT, read $DEST/LICENSE before using the data" >&2
  exit 1
fi

n_img=$(find "$DEST/Dataset" -maxdepth 1 -iname '*.jpg' | wc -l | tr -d ' ')
n_lab=$(find "$DEST/Label" -maxdepth 1 -name '*.txt' | wc -l | tr -d ' ')
echo "[get_chula] images: $n_img, label files: $n_lab"
echo "[get_chula] citation: Naruenatthanaset et al., arXiv:2012.01321 (2021)"
