# MaaXBoard‑OSM93 Demos — /IOTCONNECT Integration

This repository runs three interactive demos on MaaXBoard‑OSM93 and streams live telemetry to **IOTCONNECT**. It also receives cloud‑to‑device commands to control each demo.

**Demos**
- **Driver Monitoring System (DMS)** — face/eyes/phone/yawn detection with inference metrics.
- **Fitness Trainer** — repetitions, range of motion (ROM), and a reset command.
- **CAN** — vehicle speed & trip distance with accelerate/brake commands.

**Highlights**
- Unified IOTCONNECT client used by all demos.
- 4‑second telemetry cadence per active demo (configurable).
- Cloud commands (reset reps, accelerate/brake for N seconds, lightweight OTA).
- Hardened camera capture: GStreamer first, V4L2 fallback, auto‑reopen on timeouts.
- Explicit Ethos‑U (NPU) delegate options with configurable timeout via `ETHOSU_TIMEOUT_NS`. Applied across DMS modules that use Ethos‑U.


---

## /IOTCONNECT Architecture Overview

- **UI + Microdot server**: Hosts the local UI and an MJPEG endpoint (`/video_feed`) for the camera stream.
- **Camera pipeline**: OpenCV uses a **GStreamer** pipeline (`v4l2src → videoconvert → appsink`) and falls back to raw V4L2 if needed; on repeated timeouts it **reopens** the device. This reduces bring‑up flakiness on MIPI‑CSI.
- **Inference**:
  - DMS models are executed via TFLite. On i.MX93 (NPU), the **Ethos‑U** delegate (`/usr/lib/libethosu_delegate.so`) is attached; on i.MX8MP a VX delegate may be used. The smoking/calling module demonstrates this split.
  - Eye and face subsystems also support an optional delegate and now pass **Ethos‑U options + timeout** whenever the delegate path contains “ethosu”. 
- **IOTCONNECT bridge**: Initializes the device from `iotcDeviceConfig.json` + certs, publishes telemetry for each demo, and handles cloud commands (reset reps, accelerate/brake, simple OTA).


---

## /IOTCONNECT Telemetry Model

**Cadence**: **every 4 seconds** while a demo is active on screen. You can tune this in `webui.py` via `_DMS_INTERVAL`, `_FIT_INTERVAL`, `_CAN_INTERVAL`.

### DMS Telemetry
Keys:
- `dms_driver_status`: `"OK" | "WARN" | "ALERT"` (derived from attention/penalty)
- `dms_attention`: `1.0 | 0.0` (eyes on road)
- `dms_yawning`: `true | false`
- `dms_eyes_on_road`: `true | false`
- `dms_phone_in_use`: `true | false`
- `dms_inference_fps`: float (from model latency)
- `dms_inference_target`: `"CPU" | "NPU"`
- `dms_inference_selection` *(optional)*: model or tag

Example:
```json
{
  "demo": "DMS",
  "dms_driver_status": "OK",
  "dms_attention": 1.0,
  "dms_yawning": false,
  "dms_eyes_on_road": true,
  "dms_phone_in_use": false,
  "dms_inference_fps": 38.2,
  "dms_inference_target": "NPU",
  "dms_inference_selection": "demo-model"
}
```

### Fitness Telemetry
Keys:
- `ft_exercise`: string (e.g., `"bicep_curl"`)
- `ft_reps`: integer
- `ft_rom_deg`: float (degrees)
- `ft_inference_fps`: float *(optional)*

Example:
```json
{
  "demo": "FITNESS",
  "ft_exercise": "bicep_curl",
  "ft_reps": 3,
  "ft_rom_deg": 82.5,
  "ft_inference_fps": 15.0
}
```

### CAN Telemetry
Keys:
- `can_speed_kph`: float
- `can_trip_km`: float

Example:
```json
{
  "demo": "CAN",
  "can_speed_kph": 42.0,
  "can_trip_km": 0.0534
}
```

> CAN telemetry forwards the exact speed and trip values used by the on‑screen display when available; if the bus is not connected, values may remain 0 while a heartbeat is still sent.


---

## /IOTCONNECT Commands

| Command           | Args            | Behavior |
|------------------|-----------------|----------|
| `ft-reset-reps`  | —               | Reset Fitness rep counter. |
| `can-accelerate` | seconds (float) | Accelerate for N seconds; then return to IDLE. |
| `can-brake`      | seconds (float) | Brake for N seconds; then return to IDLE. |
| `file-download`  | url (string)    | Download `.tar.gz`, extract, run `install.sh` if present, then restart the app. |


---

## Requirements

- **IOTCONNECT credentials** in repo root:
  - `iotcDeviceConfig.json`, `device-cert.pem`, `device-pkey.pem`
- **OpenCV** with V4L2 and GStreamer backends on the MaaXBoard image.
- **TFLite runtime** (as used by DMS modules).
- **Ethos‑U** delegate on i.MX93 (`/usr/lib/libethosu_delegate.so`) and/or **VX** delegate on i.MX8MP (`/usr/lib/libvx_delegate.so`) as referenced by DMS loaders. 
- **CAN** transceiver/cabling appropriate for your board + bus.


---

## Setup

1. **Copy credentials**  
   Place `iotcDeviceConfig.json`, `device-cert.pem`, `device-pkey.pem` alongside `webui.py`.

2. **CAN bring‑up (if needed)**  
   If the image doesn’t auto‑configure `can0`:
   ```bash
   ip link set can0 type can bitrate 500000
   ip link set up can0
   ```

3. **Ethos‑U delegate timeout**  
   To reduce long stalls during NPU init:
   ```bash
   export ETHOSU_TIMEOUT_NS=5000000000   # 5 seconds in nanoseconds (default)
   # try 10s if needed:
   export ETHOSU_TIMEOUT_NS=10000000000
   ```

4. **Launch**
   ```bash
   ./launch.sh
   ```
   The launcher cleans up any prior instance to avoid the singleton lock and exports a default `ETHOSU_TIMEOUT_NS` if not set.


---

## Running

- Use the on‑screen UI to switch among **Fitness**, **DMS**, and **CAN**.  
- The active demo publishes telemetry to IOTCONNECT every **4 seconds**.  
- For DMS, the UI toggle switches the inference target (CPU/NPU).  
- For Fitness, send the `ft-reset-reps` command from IOTCONNECT to clear reps.  
- For CAN, use `can-accelerate <sec>` or `can-brake <sec>` from IOTCONNECT.


---

## Troubleshooting

**Another instance is already running**  
The launcher terminates any previous demo processes before starting, preventing the singleton lock from aborting the run.

**Camera intermittent / V4L2 `select()` timeouts**  
The capture path prefers GStreamer and automatically reopens on repeated read failures; adjust the GStreamer caps (format/size/fps) in `camera.py` to match the sensor if needed. 
**Long stall during DMS startup**  
Lower the NPU delegate timeout using `ETHOSU_TIMEOUT_NS`. DMS modules now pass this timeout to the Ethos‑U delegate. 

**CAN values remain 0**  
Without a physical bus connected, values can remain 0. Once the bus is attached and the display shows speed/trip, those values are forwarded to IOTCONNECT.


---

## Change Log & Checklist

**Files updated**
- `camera.py`  
  — Prefer **GStreamer** pipeline; fallback to V4L2; **auto‑reopen** camera after repeated read timeouts; minor fix in `CloseCVDevice()` usage. 

- `dms/smoking_calling_yolov4.py`  
  — On i.MX93 (“NPU”), create the **Ethos‑U delegate** with explicit options:  
  `device_name=/dev/ethosu0`, `cache_file_path=.`, `enable_cycle_counter=0`, `enable_profiling=0`, and `timeout` from `ETHOSU_TIMEOUT_NS` (default 5s). i.MX8MP (VX) and CPU paths unchanged. 

- `dms/eye_landmark.py`  
  — When a delegate path is provided and contains “ethosu”, use the same **Ethos‑U options + timeout**; other delegates unchanged. 
- 
- `dms/face_detection.py`  
  — Same **Ethos‑U options + timeout** pattern as `eye_landmark.py`; other delegates unchanged. 

- `dms/face_landmark.py` (if present)  
  — Aligned with `eye_landmark.py` + `face_detection.py`: optional delegate, uses Ethos‑U options when path contains “ethosu”, includes `ETHOSU_TIMEOUT_NS` timeout support.

- `launch.sh`  
  — Exports `ETHOSU_TIMEOUT_NS=${ETHOSU_TIMEOUT_NS:-5000000000}` (5s default).  
  — Kills prior demo processes before starting (prevents singleton lock).  
  — Starts the application.

- `webui.py` and `iotc_bridge.py`  
  — Single IOTCONNECT client for all demos, 4‑second telemetry per demo, cloud commands (`ft-reset-reps`, `can-accelerate`, `can-brake`, `file-download`).

**System expectations**
- **Ethos‑U remoteproc** is already running; the app binds to `/dev/ethosu0` without attempting firmware changes.  
- **GStreamer** core plugins available (for the camera pipeline) or V4L2 fallback works. 
- **CAN** interface configured as needed (`can0`).  
- **Time sync** is correct (TLS for IOTCONNECT endpoints).


---

## Security Notes

- Do **not** commit real device credentials. Instead, keep `iotcDeviceConfig.json`, `device-cert.pem`, and `device-pkey.pem` out of version control or provide redacted examples.


---

## Development Notes

Typical git workflow:
```bash
git checkout -b feature/iotconnect-telemetry
# edit / test on device
git add camera.py dms/*.py webui.py iotc_bridge.py launch.sh README.md
git commit -m "IOTCONNECT: unified telemetry/commands, 4s cadence, camera stability, Ethos-U timeout"
git push origin feature/iotconnect-telemetry
```