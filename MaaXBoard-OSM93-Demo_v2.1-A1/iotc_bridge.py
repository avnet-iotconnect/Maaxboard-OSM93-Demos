# iotc_bridge.py — MaaXBoard OSM93 demos IOTCONNECT integration (import-only)
# Connect to IOTCONNECT and provide helpers for DMS, Fitness, and CAN telemetry + commands.
# SPDX-License-Identifier: MIT

from __future__ import annotations
import os, sys, time, threading, subprocess, urllib.request, math
from typing import Optional, Callable
from dataclasses import dataclass

# OS-level lock to ensure single MQTT owner per device
try:
    import fcntl  # POSIX only
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore

# Graceful import: Avnet IOTCONNECT Lite SDK
IOTC_AVAILABLE = True
try:
    from avnet.iotconnect.sdk.lite import Client, DeviceConfig, C2dCommand, Callbacks, DeviceConfigError
    from avnet.iotconnect.sdk.lite import __version__ as SDK_VERSION
    from avnet.iotconnect.sdk.sdklib.mqtt import C2dAck, C2dOta
except Exception:
    IOTC_AVAILABLE = False
    SDK_VERSION = "unavailable"
    Client = object  # type: ignore
    DeviceConfig = object  # type: ignore
    C2dCommand = object  # type: ignore
    Callbacks = object  # type: ignore
    DeviceConfigError = Exception  # type: ignore
    class C2dAck:
        CMD_SUCCESS_WITH_ACK = "SUCCESS"
        CMD_FAILED = "FAILED"
        OTA_DOWNLOADING = "DOWNLOADING"
        OTA_DOWNLOAD_DONE = "DOWNLOAD_DONE"
    class C2dOta:
        urls = []
        version = "0"

_client: Optional[Client] = None
_connected_lock = threading.Lock()
_last_disconnect_ts = 0.0
_reconnect_backoff_sec = float(os.getenv("IOTC_RECONNECT_BACKOFF_SEC", "5"))

_proc_lock_fd: Optional[int] = None
_proc_lock_path: str = os.getenv("IOTC_PROCESS_LOCK_PATH", "/var/run/iotc_device.lock")

# App-supplied callbacks for commands
_fitness_reset_cb: Optional[Callable[[], None]] = None
_can_accelerate_cb: Optional[Callable[[float], None]] = None
_can_brake_cb: Optional[Callable[[float], None]] = None

def _log(msg: str):
    print(f"[IOTC] {msg}", flush=True)

def _acquire_process_lock() -> bool:
    """Try to take an exclusive process-wide lock so only one process connects."""
    global _proc_lock_fd
    if fcntl is None:
        _log("fcntl unavailable; skipping process lock (single-process not enforced)")
        return True
    if _proc_lock_fd is not None:
        return True
    try:
        # Ensure directory exists
        d = os.path.dirname(_proc_lock_path) or "/var/run"
        os.makedirs(d, exist_ok=True)
        _proc_lock_fd = os.open(_proc_lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.lockf(_proc_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _log(f"Process lock acquired at {_proc_lock_path} (PID={os.getpid()})")
        return True
    except Exception as e:
        _log(f"Another process holds IOTCONNECT lock at {_proc_lock_path}; skipping connect. ({e})")
        return False

def _extract_and_run_tar_gz(targz_filename: str) -> bool:
    try:
        subprocess.run(("tar", "-xzvf", targz_filename, "--overwrite"), check=True)
        script_file_path = os.path.join(os.getcwd(), "install.sh")
        if os.path.isfile(script_file_path):
            try:
                subprocess.run(['bash', script_file_path], check=True)
                os.remove(script_file_path)
                _log("install.sh executed successfully")
                return True
            except subprocess.CalledProcessError as e:
                os.remove(script_file_path)
                _log(f"install.sh returned error: {e}")
                return False
        return True
    except Exception as e:
        _log(f"Extraction error for {targz_filename}: {e}")
        return False

def _on_command(msg: C2dCommand):
    name = getattr(msg, "command_name", "")
    args = list(getattr(msg, "command_args", []) or [])
    _log(f"Command: {name} args={args} ack_id={getattr(msg,'ack_id',None)}")

    if name == "file-download":
        if len(args) != 1:
            _send_cmd_ack(msg, C2dAck.CMD_FAILED, "Expected 1 argument: URL")
            return
        try:
            url = args[0]
            _log(f"Downloading {url} -> package.tar.gz")
            urllib.request.urlretrieve(url, "package.tar.gz")
            ok = _extract_and_run_tar_gz("package.tar.gz")
            if ok:
                _send_cmd_ack(msg, C2dAck.CMD_SUCCESS_WITH_ACK, "Downloaded & applied. Restarting...")
                _log("Restarting after file-download")
                sys.stdout.flush()
                os.execv(sys.executable, [sys.executable, sys.argv[0]] + sys.argv[1:])
            else:
                _send_cmd_ack(msg, C2dAck.CMD_FAILED, "Download/extract failed")
        except Exception as e:
            _send_cmd_ack(msg, C2dAck.CMD_FAILED, f"Download error: {e}")
        return

    if name == "ft-reset-reps":
        if _fitness_reset_cb is None:
            _send_cmd_ack(msg, C2dAck.CMD_FAILED, "No reset callback registered")
            return
        try:
            _fitness_reset_cb()
            _send_cmd_ack(msg, C2dAck.CMD_SUCCESS_WITH_ACK, "Reps reset")
        except Exception as e:
            _send_cmd_ack(msg, C2dAck.CMD_FAILED, f"Reset error: {e}")
        return

    if name in ("can-accelerate", "can-brake"):
        if len(args) != 1:
            _send_cmd_ack(msg, C2dAck.CMD_FAILED, "Expected 1 argument: seconds")
            return
        try:
            seconds = float(args[0]); assert seconds > 0
        except Exception:
            _send_cmd_ack(msg, C2dAck.CMD_FAILED, "Invalid seconds value")
            return
        try:
            if name == "can-accelerate":
                if _can_accelerate_cb is None:
                    raise RuntimeError("No accelerate callback registered")
                _can_accelerate_cb(seconds)
            else:
                if _can_brake_cb is None:
                    raise RuntimeError("No brake callback registered")
                _can_brake_cb(seconds)
            _send_cmd_ack(msg, C2dAck.CMD_SUCCESS_WITH_ACK, f"{name} for {seconds} sec")
        except Exception as e:
            _send_cmd_ack(msg, C2dAck.CMD_FAILED, f"Action error: {e}")
        return

    _log(f"Unhandled command: {name}")
    _send_cmd_ack(msg, C2dAck.CMD_FAILED, "Not Implemented")

def _on_ota(msg: C2dOta):
    _send_ota_ack(msg, C2dAck.OTA_DOWNLOADING)
    ok = False
    try:
        for url in getattr(msg, "urls", []) or []:
            fname = getattr(url, "file_name", "payload.tar.gz")
            u = getattr(url, "url", None)
            if not u:
                continue
            _log(f"OTA download {fname} <- {u}")
            urllib.request.urlretrieve(u, fname)
            if fname.endswith(".tar.gz"):
                ok = _extract_and_run_tar_gz(fname)
                if not ok:
                    break
        if ok:
            _send_ota_ack(msg, C2dAck.OTA_DOWNLOAD_DONE)
            _log("OTA applied; restarting")
            sys.stdout.flush()
            os.execv(sys.executable, [sys.executable, sys.argv[0]] + sys.argv[1:])
    except Exception as e:
        _log(f"OTA error: {e}")

def _on_disconnect(reason: str, disconnected_from_server: bool):
    global _last_disconnect_ts
    _last_disconnect_ts = time.time()
    _log(f"Disconnected{' from server' if disconnected_from_server else ''}. reason={reason}")

def _send_cmd_ack(msg, status, text):
    try:
        if _client and hasattr(msg, "ack_id") and getattr(msg, "ack_id") is not None:
            _client.send_command_ack(msg, status, text)
    except Exception as e:
        _log(f"ACK error: {e}")

def _send_ota_ack(msg, status):
    try:
        if _client:
            _client.send_ota_ack(msg, status)
    except Exception as e:
        _log(f"OTA ACK error: {e}")

def ensure_connected(retries: int = 60, delay_s: float = 0.5):
    """Ensure IOTCONNECT is connected; safe to call many times; race-proof."""
    global _client
    if not IOTC_AVAILABLE:
        _log("SDK not available: install Avnet IOTCONNECT Lite SDK")
        return

    # Backoff after disconnects to avoid thrash
    if _last_disconnect_ts and (time.time() - _last_disconnect_ts) < _reconnect_backoff_sec:
        return

    with _connected_lock:
        # Acquire a cross-process lock before creating/connecting
        if _client is None:
            if not _acquire_process_lock():
                return
            try:
                cfg_dir = os.getenv("IOTC_CONFIG_DIR", os.getcwd())
                device_config_json_path = os.path.join(cfg_dir, "iotcDeviceConfig.json")
                device_cert_path = os.path.join(cfg_dir, "device-cert.pem")
                device_pkey_path = os.path.join(cfg_dir, "device-pkey.pem")

                cfg = DeviceConfig.from_iotc_device_config_json_file(
                    device_config_json_path=device_config_json_path,
                    device_cert_path=device_cert_path,
                    device_pkey_path=device_pkey_path
                )
                _client = Client(config=cfg, callbacks=Callbacks(
                    ota_cb=_on_ota, command_cb=_on_command, disconnected_cb=_on_disconnect
                ))
                _log(f"PID={os.getpid()} IOTCONNECT client created")
            except DeviceConfigError as dce:
                _log(f"DeviceConfig error: {dce}")
                raise

        if getattr(_client, "is_connected", lambda: False)():
            return

        _log("(re)connecting...")
        _client.connect()
        for _ in range(retries):
            if _client.is_connected():
                break
            time.sleep(delay_s)
        if not _client.is_connected():
            _log("Unable to connect after retries")

def _send_telemetry(payload: dict):
    if not IOTC_AVAILABLE:
        _log("SDK not available; dropping telemetry")
        return
    ensure_connected()
    base = {"sdk_version": SDK_VERSION}
    if payload:
        base.update(payload)

    # 1) Try plain-dict first
    try:
        _client.send_telemetry(base)
        _log(f"TX ok keys={list(payload.keys())[:8]}")
        return
    except TypeError:
        pass
    except Exception as e:
        _log(f"telemetry error (plain): {e}")

    # 2) Fallback: wrapped envelope shape
    try:
        wrapped = {"d": [{"d": base}]}
        _client.send_telemetry(wrapped)
        _log(f"TX ok (wrapped) keys={list(payload.keys())[:8]}")
    except Exception as e:
        _log(f"telemetry error (wrapped): {e}")

# Public API
def init_webui_iotc():
    ensure_connected()
    _log("IOTCONNECT ready")
    try:
        _send_telemetry({"demo": "BOOT", "boot_ts": int(time.time())})
        _log("[BOOT] Sent initial heartbeat")
    except Exception as e:
        _log(f"[BOOT] heartbeat send failed: {e}")

def iotc_is_connected() -> bool:
    try:
        return bool(_client and _client.is_connected())
    except Exception:
        return False

def register_fitness_reset(cb: Callable[[], None]):
    global _fitness_reset_cb; _fitness_reset_cb = cb

def register_can_actions(accelerate_cb: Callable[[float], None], brake_cb: Callable[[float], None]):
    global _can_accelerate_cb, _can_brake_cb
    _can_accelerate_cb = accelerate_cb
    _can_brake_cb = brake_cb

def update_dms(attention_label: str, yawning: bool, eye_closed: bool,
               latency_ms: float, penalty_score: float, phone_in_use: bool,
               inference_target: str = "CPU", model_name: Optional[str] = None):
    try:
        fps = 1000.0 / float(latency_ms) if latency_ms and latency_ms > 0 else None
    except Exception:
        fps = None
    eyes_on_road = str(attention_label).strip().lower() == "forward" and not bool(eye_closed)
    driver_status = "OK" if float(penalty_score) < 15 else ("WARN" if float(penalty_score) < 50 else "ALERT")
    payload = {
        "demo": "DMS",
        "dms_driver_status": driver_status,
        "dms_attention": 1.0 if eyes_on_road else 0.0,
        "dms_yawning": bool(yawning),
        "dms_eyes_on_road": bool(eyes_on_road),
        "dms_phone_in_use": bool(phone_in_use),
        "dms_inference_fps": float(fps) if fps is not None else None,
        "dms_inference_target": "NPU" if str(inference_target).upper()=="NPU" else "CPU",
    }
    if model_name:
        payload["dms_inference_selection"] = str(model_name)
    _send_telemetry(payload)

def update_fitness(exercise_name: str, rep_count: int, rom_deg: float, fps: Optional[float] = None):
    payload = {
        "demo": "FITNESS",
        "ft_exercise": str(exercise_name),
        "ft_reps": int(rep_count),
        "ft_rom_deg": float(rom_deg),
    }
    if fps is not None:
        payload["ft_inference_fps"] = float(fps)
    _send_telemetry(payload)

@dataclass
class _CanState:
    last_ts: float = time.time()
    trip_km: float = 0.0

_can_state = _CanState()

def update_can_values(speed_kph: float, trip_km: Optional[float] = None):
    """Send CAN telemetry; if trip_km is provided, send that exact value. Otherwise integrate."""
    now = time.time()
    try:
        s = float(speed_kph)
    except Exception:
        s = 0.0

    if trip_km is None:
        dt = now - _can_state.last_ts
        _can_state.last_ts = now
        if dt > 0 and math.isfinite(dt):
            _can_state.trip_km += max(s, 0.0) * (dt / 3600.0)
    else:
        _can_state.trip_km = float(trip_km)
        _can_state.last_ts = now

    payload = {
        "demo": "CAN",
        "can_speed_kph": float(s),
        "can_trip_km": float(_can_state.trip_km),
    }
    _send_telemetry(payload)

def update_can(speed_kph: float):
    update_can_values(speed_kph, None)
