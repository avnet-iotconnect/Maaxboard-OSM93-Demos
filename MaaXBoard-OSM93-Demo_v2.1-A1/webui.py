"""
webui.py — Main Application Entry Point with IOTCONNECT integration.
Initializes CAN bus manager, camera, GUI, and a Microdot web server.
Pushes telemetry for Fitness, DMS, and CAN to IOTCONNECT and handles cloud commands.
"""

import os, sys, json, time, threading, numbers
import cv2
from netinfo import NETInfo
from camera import cameraSupport
from localWindow import localWindow
from tendo import singleton
from CanTools.car_status import CarStatus
from CanTools.can_main import CanDemoManager

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

from microdot import Microdot, redirect, send_file
from iotc_bridge import (
    init_webui_iotc, update_dms, update_fitness, update_can_values,
    register_fitness_reset, register_can_actions, iotc_is_connected
)

# ---------------- Options ----------------
run_on_hardware = False
if not run_on_hardware:
    HardwareSupport = False
    RotateCameraY = False
    RotateCameraX = False
    EnableUSBPowerMonitor = False
else:
    HardwareSupport = True
    RotateCameraY = False
    RotateCameraX = True
    EnableUSBPowerMonitor = True

# Demo constants
DEMO_FITNESS = 0
DEMO_DMS = 1
DEMO_CAN = 2

# Ensure single instance
me = singleton.SingleInstance()

serialPortBusy = False
ledStates = [0, 0, 0]

globalFrame = None
globalCurrentDemo = 0

# CAN simulator & tools
can_app_manager = CanDemoManager(selectedDemo=globalCurrentDemo)

fileDir = os.path.dirname(os.path.realpath(__file__))
def GetFileFullPath(s):
    filePath = os.path.join(fileDir, s)
    filePath = os.path.abspath(os.path.realpath(filePath))
    return filePath

# Telemetry throttle
_last_dms_ts = 0.0
_last_fit_ts = 0.0
_DMS_INTERVAL = 4.0
_FIT_INTERVAL = 4.0
_CAN_INTERVAL = 4.0

def _parse_latency_ms(value):
    try:
        if isinstance(value, str):
            v = value.replace("MS","" ).replace("ms","" ).replace("mS","" ).replace(" ", "")
            return float(v)
        return float(value)
    except Exception:
        return 0.0

def _infer_fitness_values(ret1, ret2, ret3, ret4):
    """Heuristic to map (ret1..ret4) to (exercise_name, reps, rom_deg, fps)."""
    exercise_name = str(ret1) if isinstance(ret1, str) else "exercise"
    reps, rom_deg, fps = 0, 0.0, None

    def _is_int_like(x):
        try:
            xi = int(float(x))
            return abs(float(x) - xi) < 0.001
        except Exception:
            return False

    def _to_float(x, default=0.0):
        try:
            return float(x)
        except Exception:
            return default

    c2_int = _is_int_like(ret2)
    c3_int = _is_int_like(ret3)
    if c2_int and not c3_int:
        reps, rom_deg = int(float(ret2)), _to_float(ret3, 0.0)
    elif c3_int and not c2_int:
        reps, rom_deg = int(float(ret3)), _to_float(ret2, 0.0)
    else:
        rom_deg, reps = _to_float(ret2, 0.0), int(float(ret3)) if _is_int_like(ret3) else 0

    try:
        fps = float(ret4)
    except Exception:
        fps = None
    return exercise_name, reps, rom_deg, fps

# ---------------- Frame callback ----------------
def frameCallback(frame, demoNumber, ret1, ret2, ret3, ret4, ret5, ret6):
    global globalFrame, globalCurrentDemo, _last_dms_ts, _last_fit_ts
    globalFrame = frame
    window.updateFrame(frame)

    now = time.time()

    if (globalCurrentDemo == DEMO_FITNESS) and (demoNumber == DEMO_FITNESS):
        window.UpdateFitnessUI(ret1, ret2, ret3, ret4)
        if (now - _last_fit_ts) >= _FIT_INTERVAL:
            exercise_name, reps, rom_deg, fps = _infer_fitness_values(ret1, ret2, ret3, ret4)
            print(f"[FIT] TX reps={reps} rom={rom_deg} fps={fps}", flush=True)
            update_fitness(exercise_name, reps, rom_deg, fps)
            _last_fit_ts = now

    elif (globalCurrentDemo == DEMO_DMS) and (demoNumber == DEMO_DMS):
        window.UpdateDMSUI(ret1, ret2, ret3, ret4, ret5, ret6)
        if (now - _last_dms_ts) >= _DMS_INTERVAL:
            latency_ms = _parse_latency_ms(ret4)
            try:
                inference_target = "NPU" if getattr(camera, "enableNPU", False) else "CPU"
            except Exception:
                inference_target = "CPU"
            print(f"[DMS] TX att={ret1} yawn={ret2} eyes={ret3} ms={latency_ms}", flush=True)
            update_dms(
                attention_label=str(ret1),
                yawning=bool(ret2),
                eye_closed=bool(ret3),
                latency_ms=float(latency_ms),
                penalty_score=float(ret5) if ret5 is not None else 0.0,
                phone_in_use=bool(ret6),
                inference_target=inference_target,
                model_name=None
            )
            _last_dms_ts = now

    else:
        # CAN demo selected: handled by background loop
        pass

# ---------------- Screen / button handlers ----------------
def screenClickCallback(event):
    global globalCurrentDemo

    if event == "event_reset":
        camera.ResetFitnessApp()
        globalCurrentDemo = DEMO_FITNESS

    elif event == "page0":
        globalCurrentDemo = DEMO_FITNESS
        window.UpdateActiveDemo(globalCurrentDemo)

    elif event == "page1":
        globalCurrentDemo = DEMO_DMS
        window.UpdateActiveDemo(globalCurrentDemo)

    elif event == "page2":
        globalCurrentDemo = DEMO_CAN
        window.UpdateActiveDemo(globalCurrentDemo)
        try:
            spd, dist = _read_display_can_values()
            update_can_values(spd if spd is not None else 0.0, dist)
        except Exception:
            pass

    elif event == "toggle_DMS_Acceleration":
        camera.ToggleDMSAcceleration()
        window.ToggleNPUAccelerationLabel()

    elif event == "car_accelerate":
        window.UpdateCANUI()
        can_app_manager.update_car_state(carState=CarStatus.ACCELERATE)

    elif event == "car_brake":
        window.UpdateCANUI()
        can_app_manager.update_car_state(carState=CarStatus.BRAKE)

    elif event == "car_idle":
        window.UpdateCANUI()
        can_app_manager.update_car_state(CarStatus.IDLE)

    camera.SwitchDemo(globalCurrentDemo)

# ---------------- Web Server ----------------
app = Microdot()

@app.route('/video_feed')
async def video_feed(request):
    global globalFrame
    if sys.implementation.name != 'micropython':
        async def stream():
            yield b'--frame\r\n'
            while True:
                if camera.CameraOpen():
                    frame = globalFrame
                    if(frame is not None):
                        _, frame = cv2.imencode('.JPEG', frame)
                        yield (b'--frame\r\n'
                            b'Content-Type: image/jpeg\r\n\r\n' + frame.tobytes() + b'\r\n')
                await asyncio.sleep(0.01)
    else:
        class stream():
            def __init__(self): self.i = 0
            def __aiter__(self): return self
            async def __anext__(self):
                await asyncio.sleep(1)
    return stream(), 200, {'Content-Type': 'multipart/x-mixed-replace; boundary=frame'}

@app.route('/ethernet.cgi', methods=['GET'])
async def ethernet(request):
    response = None
    if request.method == 'GET':
        cmdType = 'ethernet'
        info = NETInfo.GetNetworkInfo()
        data_set = {"cmdType": cmdType, "ethernetInfo": [info]}
        response = json.dumps(data_set)
    return response

@app.route('/uses/rundemo.cgi', methods=['GET', 'POST'])
def demoCgi(request):
    if request.method == 'POST':
        resp = json.loads(request.body)
        if ("cmdType" in resp):
            data_set = {"cmdType": 'rundemo'}
        response = json.dumps(data_set)
        return response
    return redirect('/')

@app.route('/uses/<name>', methods=['GET', 'POST'])
def uses_file(request,name):
    if request.method == 'POST':
        return redirect('/')
    else:
        return send_file(GetFileFullPath('web/uses/'+name))

@app.route('/<name>', methods=['GET', 'POST'])
def named_file(request,name):
    if request.method == 'POST':
        return redirect('/')
    else:
        return send_file(GetFileFullPath('web/'+name))

@app.route('/', methods=['GET', 'POST'])
def index(request):
    if request.method == 'POST':
        return redirect('/')
    else:
        return send_file(GetFileFullPath('web/index.html'))

# ---------------- Initialization ----------------
camera = cameraSupport(HardwareSupport, frameCallback)
window = localWindow(screenClickCallback)

# IOTCONNECT: connect + command wiring
init_webui_iotc()
print(f"[BOOT] IoTConnect connected: {iotc_is_connected()} (PID={os.getpid()})", flush=True)

register_fitness_reset(lambda: camera.ResetFitnessApp())

# ---- CAN helpers ----
_SPEED_KEYS = ["current_speed_kph","speed_kph","speed_kmh","speed","vehicle_speed","car_speed","v_speed","kmh","kph","mph"]
_TRIP_KEYS = ["trip_km","distance_km","odometer_km","trip","distance","odometer","km_travel","km_travelled","km_traveled","mileage","miles","mi"]
def _num(v) -> float | None:
    try:
        if isinstance(v, numbers.Number):
            return float(v)
        if isinstance(v, str):
            return float(v.strip())
    except Exception:
        return None
    return None
def _maybe_convert_speed(name: str, val: float) -> float:
    n = name.lower()
    if "mph" in n:
        return val * 1.60934
    return val
def _maybe_convert_distance(name: str, val: float) -> float:
    n = name.lower()
    if any(k in n for k in ["mile","miles","mi"]) and not any(k in n for k in ["km"]):
        return val * 1.60934
    return val
def _pick_best_match(obj, keys):
    for attr in dir(obj):
        low = attr.lower()
        if any(k in low for k in keys):
            try:
                val = getattr(obj, attr)
                v = _num(val)
                if v is not None:
                    return attr, v
            except Exception:
                pass
    for attr in dir(obj):
        low = attr.lower()
        if any(k in low for k in keys):
            try:
                fn = getattr(obj, attr)
                if callable(fn):
                    v = _num(fn())
                    if v is not None:
                        return attr+"()", v
            except Exception:
                pass
    return None, None
def _scan_nested(obj, keys):
    name, val = _pick_best_match(obj, keys)
    if val is not None:
        return name, val
    for child_name in ("car","vehicle","state","status","model"):
        if hasattr(obj, child_name):
            child = getattr(obj, child_name)
            try:
                name, val = _pick_best_match(child, keys)
                if val is not None:
                    return f"{child_name}.{name}", val
            except Exception:
                pass
    return None, None
def _read_display_can_values():
    s_name, s_val = _scan_nested(can_app_manager, _SPEED_KEYS)
    speed = _maybe_convert_speed(s_name, s_val) if (s_val is not None and s_name) else None
    d_name, d_val = _scan_nested(can_app_manager, _TRIP_KEYS)
    trip  = _maybe_convert_distance(d_name, d_val) if (d_val is not None and d_name) else None
    return speed, trip

def _can_telemetry_loop():
    while True:
        if globalCurrentDemo == DEMO_CAN:
            try:
                speed, trip = _read_display_can_values()
            except Exception:
                speed, trip = 0.0, None
            update_can_values(speed if speed is not None else 0.0, trip)
        time.sleep(_CAN_INTERVAL)

def _telemetry_heartbeat():
    while True:
        try:
            update_fitness("heartbeat", 0, 0.0, None)
        except Exception as e:
            print("[HB] error:", e, flush=True)
        time.sleep(5)

threading.Thread(target=_can_telemetry_loop, daemon=True).start()
threading.Thread(target=_telemetry_heartbeat, daemon=True).start()

# Run app (debug disabled to avoid reloader)
print("[BOOT] Camera opening and Microdot starting...", flush=True)
DEBUG = bool(int(os.getenv("MICRODOT_DEBUG", "0")))
app.run(host='0.0.0.0', port=int(os.getenv("WEBUI_PORT", "5000")), debug=DEBUG)
camera.close()
