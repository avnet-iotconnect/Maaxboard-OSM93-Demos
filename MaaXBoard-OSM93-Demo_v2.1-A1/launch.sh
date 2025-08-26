#!/bin/sh
export ETHOSU_TIMEOUT_NS=${ETHOSU_TIMEOUT_NS:-5000000000}
pkill -f 'python.*(webui\.py|app\.py|MaaXBoard-OSM93-Demo)' 2>/dev/null || true
sleep 0.5
export XDG_RUNTIME_DIR=/run

if test -z "$XDG_RUNTIME_DIR"; then
    export XDG_RUNTIME_DIR=/run
    if ! test -d "$XDG_RUNTIME_DIR"; then
        mkdir --parents $XDG_RUNTIME_DIR
        chmod 0700 $XDG_RUNTIME_DIR
    fi
fi

echo Waiting for weston
echo XDG_RUNTIME_DIR: $XDG_RUNTIME_DIR
while [ ! -e  $XDG_RUNTIME_DIR/wayland-0 ] ; do sleep 0.1; done
sleep 1

echo Starting application

python3 /home/root/MaaXBoard-OSM93-Demo-v2.1-A1/webui.py

