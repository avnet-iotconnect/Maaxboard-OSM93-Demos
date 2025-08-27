#!/bin/sh
# Minimal launcher that starts the Python app exactly once
set -eu
cd "$(dirname "$0")"
echo "Starting application"
exec python3 webui.py
