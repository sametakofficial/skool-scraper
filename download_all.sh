#!/bin/bash
set -e
cd /opt/homelab/skool-dl
URL="https://www.skool.com/is-guc-yapayzeka/classroom"
OUT="/data/srv/downloads"
LOG="/opt/homelab/skool-dl/full_download.log"

echo "======== $(date) ========" | tee -a "$LOG"
echo "🎬 VIDEO download..." | tee -a "$LOG"
.venv/bin/python -u skool_download.py "$URL" --server --output "$OUT" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "📚 EXTRAS download..." | tee -a "$LOG"
.venv/bin/python -u extras_download.py "$URL" --server --output "$OUT" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "✅ ALL DONE at $(date)" | tee -a "$LOG"
