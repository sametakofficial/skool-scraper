#!/usr/bin/env bash
# Skool downloader launcher — run this in YOUR terminal so the browser window
# opens on your Wayland session (not in a sandboxed root context).
#
# Usage:
#   ./run.sh                 # --list (default: just list courses)
#   ./run.sh --dry-run       # show what would download
#   ./run.sh download        # actually download all courses
#   ./run.sh --course "Hafta 1"
set -e
cd "$(dirname "$0")"

URL="https://www.skool.com/farkindalikakademisi/classroom/26799902?md=141d026f380a41f8a6c4f5b82d2be5ba"

if [ "$1" = "download" ]; then
  shift
  exec .venv/bin/python skool_download.py "$URL" "$@"
elif [ "$1" = "" ]; then
  exec .venv/bin/python skool_download.py "$URL" --list
else
  exec .venv/bin/python skool_download.py "$URL" "$@"
fi
