# camera.py — MaaXBoard OSM93 camera support (V4L2-first by default, lazy DMS init)
# SPDX-License-Identifier: MIT

import os
import time
import threading
import cv2
import numpy as np

from FitnessApp.fitnessApp import init_fitness_app
from FitnessApp.fitnessApp import process_frame_fitness, reset_fitness_app
from dms.dms_manager import DMSManager

# Initialize Fitness pipeline (same behavior as original)
init_fitness_app()

# ----- Lazy DMS initialization (prevents cold-boot CMA contention) -----
dms_cpu = None
dms_npu = None
_DMS_INIT_ONCE = False
_DMS_INIT_DELAY_SEC = int(os.getenv("DMS_INIT_DELAY_SEC", "2"))

def _ensure_dms_inited():
    global dms_cpu, dms_npu, _DMS_INIT_ONCE
    if not _DMS_INIT_ONCE and _DMS_INIT_DELAY_SEC > 0:
        # Give kernel/camera a moment after boot
        time.sleep(_DMS_INIT_DELAY_SEC)
        _DMS_INIT_ONCE = True
    if dms_cpu is None:
        dms_cpu = DMSManager(run_on_hardware=True, use_npu=False)
    if dms_npu is None:
        dms_npu = DMSManager(run_on_hardware=True, use_npu=True)

class cameraSupport:
    """Manage camera capture, Fitness and DMS processing, and callbacks."""

    def __init__(self, run_on_hardware: bool = False, callback=None):
        self.runningDemo = 0  # 0 = Fitness, 1 = DMS, 2 = CAN
        self.callback = callback
        self.onHardware = run_on_hardware
        self.cameraOpen = False
        self.running = True
        self.frame = None
        self.cap = None
        self.enableNPU = False

        # Start capture thread
        self.FrameGetterThread = threading.Thread(target=self.FrameGetter, daemon=True)
        self.FrameGetterThread.start()

    # ---------------- UI helpers ----------------

    def ResetFitnessApp(self):
        reset_fitness_app()

    def SwitchDemo(self, demo: int):
        self.runningDemo = demo

    def ToggleDMSAcceleration(self):
        self.enableNPU = not self.enableNPU

    # ---------------- Camera lifecycle ----------------

    def close(self):
        self.running = False
        try:
            if self.FrameGetterThread.is_alive():
                self.FrameGetterThread.join(timeout=0.5)
        except Exception:
            pass
        self.CloseCVDevice()

    def OpenCVDevice(self):
        """Open camera robustly: prefer V4L2 on i.MX93 unless USE_GSTREAMER=1."""
        # Release any previous capture
        try:
            if self.cap is not None and hasattr(self.cap, "isOpened") and self.cap.isOpened():
                self.cap.release()
        except Exception:
            pass

        # hw-accelerated decode hints if you ever use FFMPEG (harmless if unused)
        if self.onHardware:
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "hwaccel;qsv|video_codec;h264_qsv|vsync;0")

        use_gst = os.environ.get("USE_GSTREAMER", "0") == "1"

        def _open_v4l2():
            cap = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)
            if cap and cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                try:
                    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)  # ignore if unsupported
                except Exception:
                    pass
                return cap
            return None

        def _open_gst():
            gst = (
                "v4l2src device=/dev/video0 ! "
                "video/x-raw,format=YUY2,width=640,height=480,framerate=30/1 ! "
                "videoconvert ! video/x-raw,format=BGR ! "
                "appsink drop=true max-buffers=1 sync=false"
            )
            cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)
            return cap if cap and cap.isOpened() else None

        # Prefer V4L2 unless explicitly overridden
        cap = _open_gst() if use_gst else _open_v4l2()
        if cap is None:
            cap = _open_v4l2() if use_gst else _open_gst()

        self.cap = cap
        self.cameraOpen = bool(self.cap)

        # Quick warm-up: grab up to 2 frames to stabilize the pipeline
        if self.cameraOpen:
            ok = 0
            t0 = time.time()
            while time.time() - t0 < 2.0 and ok < 2:
                try:
                    ret, img = self.cap.read()
                    if ret and img is not None and getattr(img, "size", 0):
                        ok += 1
                    else:
                        time.sleep(0.02)
                except Exception:
                    time.sleep(0.02)
        else:
            self.cameraOpen = False

    def CloseCVDevice(self):
        self.cameraOpen = False
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass

    # ---------------- Accessors ----------------

    def CameraOpen(self) -> bool:
        return self.cameraOpen

    def GetFrame(self):
        return self.frame

    # ---------------- Capture loop ----------------

    def FrameGetter(self):
        REOPEN_AFTER = 3     # consecutive read failures before re-open
        timeout_count = 0

        while self.running:
            if not self.cameraOpen:
                self.OpenCVDevice()
                time.sleep(0.2)
                continue

            try:
                ret, image = self.cap.read()

                if ret and image is not None and getattr(image, "size", 0):
                    timeout_count = 0  # got a frame

                    # Resize before inference to keep downstream work consistent
                    image = cv2.resize(image, (320, 240), interpolation=cv2.INTER_AREA)

                    if self.runningDemo == 1:
                        # ---------- DMS ----------
                        _ensure_dms_inited()
                        try:
                            if not self.enableNPU:
                                (newFrame, att, yawn, eyes, inf_ms, penalty, phone) = dms_cpu.process_frame_dms(image)
                            else:
                                (newFrame, att, yawn, eyes, inf_ms, penalty, phone) = dms_npu.process_frame_dms(image)

                            self.frame = newFrame
                            if self.callback:
                                self.callback(self.frame, 1, att, yawn, eyes, inf_ms, penalty, phone)

                        except Exception as e:
                            import traceback
                            print("[CAM] DMS inference error:", e, flush=True)
                            traceback.print_exc()

                    elif self.runningDemo == 0:
                        # ---------- Fitness ----------
                        try:
                            newFrame, rom, _, repCount, name, status = process_frame_fitness(image)
                            self.frame = newFrame
                            if self.callback:
                                self.callback(self.frame, 0, rom, repCount, name, status, 0, 0)
                        except Exception as e:
                            import traceback
                            print("[CAM] Fitness inference error:", e, flush=True)
                            traceback.print_exc()

                    else:
                        # ---------- CAN ----------
                        # CAN demo active: video frames are not used for telemetry
                        pass

                else:
                    # Read failed or empty frame: count & consider reopen
                    timeout_count += 1
                    if timeout_count >= REOPEN_AFTER:
                        print("[CAM] read timeout; reopening", flush=True)
                        try:
                            self.cap.release()
                        except Exception:
                            pass
                        self.cameraOpen = False
                        time.sleep(0.1)
                    else:
                        time.sleep(0.02)

            except Exception as e:
                # Any unexpected read error: log and consider reopen
                timeout_count += 1
                print("[CAM] exception during read:", e, flush=True)
                if timeout_count >= REOPEN_AFTER:
                    print("[CAM] reopening after exception", flush=True)
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                    self.cameraOpen = False
                    time.sleep(0.1)
