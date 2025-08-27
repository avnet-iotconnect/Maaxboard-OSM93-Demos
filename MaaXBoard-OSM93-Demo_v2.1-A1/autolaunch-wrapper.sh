#!/bin/sh
# Robust single-instance autolaunch wrapper for MaaXBoard OSM93 demos
set -eu

DEMO_DIR="/home/root/MaaXBoard-OSM93-Demo-v2.1-A1"
cd "$DEMO_DIR" || exit 1

LOCK="/var/run/maax-demo-launch.lock"
PIDFILE="/var/run/maax-demo-launch.pid"

# Try to acquire the lock atomically using a symlink; the symlink target stores our PID
if ln -s "$$" "$LOCK" 2>/dev/null; then
  trap 'rm -f "$LOCK" "$PIDFILE"' EXIT INT TERM
  echo "$$" > "$PIDFILE"
else
  other="$(readlink "$LOCK" 2>/dev/null || true)"
  if [ -n "$other" ] && kill -0 "$other" 2>/dev/null; then
    echo "[LAUNCH] Another launcher instance is running (PID=$other, lock: $LOCK)"
    exit 0
  fi
  echo "[LAUNCH] Stale lock detected at $LOCK; cleaning it up..."
  rm -f "$LOCK" "$PIDFILE"
  ln -s "$$" "$LOCK" 2>/dev/null || { echo "[LAUNCH] Could not acquire lock after cleanup"; exit 1; }
  trap 'rm -f "$LOCK" "$PIDFILE"' EXIT INT TERM
  echo "$$" > "$PIDFILE"
fi

echo "[LAUNCH] Stopping previous app/IOTCONNECT/camera users (if any)..."
pkill -9 -f 'python.*(webui\.py|app\.py|iotc_client\.py|avnet\.iotconnect)' 2>/dev/null || true
# Free /dev/video0 if held
if command -v fuser >/dev/null 2>&1; then
  fuser -k /dev/video0 2>/dev/null || true
fi
rm -f /tmp/tendo* /tmp/*SingleInstance* /tmp/singleton_* 2>/dev/null || true

# Environment expected by the app
export XDG_RUNTIME_DIR=/run
export PYTHONUNBUFFERED=1
export PYTHONPATH="$DEMO_DIR"
export ETHOSU_TIMEOUT_NS="${ETHOSU_TIMEOUT_NS:-5000000000}"  # 5s
export IOTC_CONFIG_DIR="$DEMO_DIR"
export IOTC_PROCESS_LOCK_PATH="${IOTC_PROCESS_LOCK_PATH:-/var/run/iotc_device.lock}"
export USE_GSTREAMER="${USE_GSTREAMER:-0}"  # 0=V4L2 first; set 1 to prefer GStreamer
export MICRODOT_DEBUG=0

echo "[LAUNCH] Waiting for weston (up to 30s if present)..."
for i in $(seq 1 30); do [ -S /run/wayland-0 ] && break || sleep 1; done

echo "[LAUNCH] Waiting for network (up to 5s)..."
for i in $(seq 1 5); do ip -4 addr show | grep -q 'inet ' && break || sleep 1; done

echo "[LAUNCH] Waiting for camera node (up to 30s; will continue if missing)..."
for i in $(seq 1 30); do [ -e /dev/video0 ] && break || sleep 1; done

echo "[LAUNCH] Starting application..."
exec ./launch.sh
