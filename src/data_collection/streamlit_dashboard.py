"""
Unified RPi Streamlit dashboard for Nano 33 BLE + camera tracking.
 
Features:
- Start/End session controls.
- Live camera feed with green marker bounding box and trajectory overlay.
- Live accelerometer, gyroscope, and magnetometer plots.
- Recording outputs per session: imu.csv, annotated.mp4, raw frame images,
  frame_manifest.csv, trajectory.png, and metadata.json.
"""
 

import asyncio
import csv
import inspect
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
 
import cv2
import numpy as np
import pandas as pd
import streamlit as st
from bleak import BleakClient, BleakScanner
from picamera2 import Picamera2
 
 
# ---------- Configuration ----------
# BLE_ADDRESS = "7FB164EE-1D0A-44C5-C693-D9A5296FB2B2"
BLE_ADDRESS = "79:8E:DB:1A:1C:28"
BLE_DEVICE_NAME = "NanoBLE"
BLE_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
BLE_CONNECT_TIMEOUT_S = 4.0
BLE_RETRY_DELAY_S = 0.1
BLE_SCAN_TIMEOUT_S = 1.0

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_SIZE = (CAMERA_WIDTH, CAMERA_HEIGHT)
CAMERA_FPS = 20

UI_REFRESH_SECONDS = 0.4
MAX_IMU_POINTS = 800
MAX_TRAJECTORY_POINTS = 1500
MIN_CONTOUR_AREA = 400
MIN_BOX_SIDE_PX = 12

SAVE_RAW_FRAMES_DEFAULT = False
RAW_FRAME_STRIDE_DEFAULT = 10
SHOW_MASK_DEFAULT = False
 
# Trajectory denoising controls.
SMOOTHING_ALPHA = 0.35
MIN_POINT_DISTANCE_PX = 4.0
MAX_POINT_JUMP_PX = 80.0
 
# HSV range for green marker.
LOWER_GREEN = np.array([57, 66, 76], dtype=np.uint8)
UPPER_GREEN = np.array([87, 206, 216], dtype=np.uint8)
 
LABELS = [str(i) for i in range(10)]
 
if os.path.isdir("/home/rpi4"):
    DATA_ROOT = "/home/rpi4/dataset"
else:
    DATA_ROOT = "./dataset"
 
os.makedirs(DATA_ROOT, exist_ok=True)
 
st.set_page_config(layout="wide", page_title="RPi Air Writing Dashboard")
 
 
@dataclass
class RuntimeState:
    lock: threading.Lock = field(default_factory=threading.Lock)
 
    imu_buffer: deque = field(default_factory=lambda: deque(maxlen=MAX_IMU_POINTS))
    marker_points: deque = field(default_factory=lambda: deque(maxlen=MAX_TRAJECTORY_POINTS))
 
    sample_count: int = 0
    frame_count: int = 0
    is_running: bool = False
    ble_connected: bool = False
 
    payload_format: str = "unknown"
    latest_error: str = ""
 
    latest_frame_rgb: Optional[np.ndarray] = None
    latest_bbox: Optional[Tuple[int, int, int, int]] = None
    trajectory_canvas: Optional[np.ndarray] = None
    smoothed_marker: Optional[Tuple[float, float]] = None
    hsv_lower: np.ndarray = field(default_factory=lambda: LOWER_GREEN.copy())
    hsv_upper: np.ndarray = field(default_factory=lambda: UPPER_GREEN.copy())
    min_contour_area: int = MIN_CONTOUR_AREA
    min_box_side: int = MIN_BOX_SIDE_PX
    save_raw_frames: bool = SAVE_RAW_FRAMES_DEFAULT
    raw_frame_every_n: int = RAW_FRAME_STRIDE_DEFAULT
    show_mask: bool = SHOW_MASK_DEFAULT
    latest_mask: Optional[np.ndarray] = None
 
    stop_event: Optional[threading.Event] = None
    ble_thread: Optional[threading.Thread] = None
    camera_thread: Optional[threading.Thread] = None
 
    session_label: str = ""
    session_dir: str = ""
    raw_frame_dir: str = ""
    session_started_at: float = 0.0
    session_started_wallclock_ms: int = 0
    last_saved_session_dir: str = ""
 
    imu_path: str = ""
    frame_manifest_path: str = ""
    trajectory_path: str = ""
    video_path: str = ""
 
    imu_file: Optional[Any] = None
    imu_writer: Optional[Any] = None
    frame_manifest_file: Optional[Any] = None
    frame_manifest_writer: Optional[Any] = None
    video_writer: Optional[cv2.VideoWriter] = None
 
 
def get_runtime() -> RuntimeState:
    if "runtime" not in st.session_state:
        st.session_state.runtime = RuntimeState()
    runtime = st.session_state.runtime
    if not hasattr(runtime, "hsv_lower"):
        runtime.hsv_lower = LOWER_GREEN.copy()
    if not hasattr(runtime, "hsv_upper"):
        runtime.hsv_upper = UPPER_GREEN.copy()
    if not hasattr(runtime, "min_contour_area"):
        runtime.min_contour_area = MIN_CONTOUR_AREA
    if not hasattr(runtime, "min_box_side"):
        runtime.min_box_side = MIN_BOX_SIDE_PX
    if not hasattr(runtime, "save_raw_frames"):
        runtime.save_raw_frames = SAVE_RAW_FRAMES_DEFAULT
    if not hasattr(runtime, "raw_frame_every_n"):
        runtime.raw_frame_every_n = RAW_FRAME_STRIDE_DEFAULT
    if not hasattr(runtime, "show_mask"):
        runtime.show_mask = SHOW_MASK_DEFAULT
    if not hasattr(runtime, "latest_mask"):
        runtime.latest_mask = None
    return runtime
 
 
def _decode_ble_packet(payload: bytes) -> Optional[Dict[str, float]]:
    decoded = payload.decode(errors="ignore").strip()
    parts = [p.strip() for p in decoded.split(",")]
 
    if len(parts) == 10:
        try:
            return {
                "nano_timestamp_ms": int(float(parts[0])),
                "ax": float(parts[1]),
                "ay": float(parts[2]),
                "az": float(parts[3]),
                "gx": float(parts[4]),
                "gy": float(parts[5]),
                "gz": float(parts[6]),
                "mx": float(parts[7]),
                "my": float(parts[8]),
                "mz": float(parts[9]),
                "payload_format": "10-field",
            }
        except ValueError:
            return None
 
    if len(parts) == 7:
        try:
            return {
                "nano_timestamp_ms": int(float(parts[0])),
                "ax": float(parts[1]),
                "ay": float(parts[2]),
                "az": float(parts[3]),
                "gx": float(parts[4]),
                "gy": float(parts[5]),
                "gz": float(parts[6]),
                "mx": float("nan"),
                "my": float("nan"),
                "mz": float("nan"),
                "payload_format": "7-field",
            }
        except ValueError:
            return None
 
    return None
 
 
def _ble_notification_handler(runtime: RuntimeState, payload: bytes) -> None:
    parsed = _decode_ble_packet(payload)
    if parsed is None:
        return
 
    rpi_timestamp_ms = int(time.time() * 1000)
 
    with runtime.lock:
        runtime.payload_format = parsed["payload_format"]
 
        sample = {
            "rpi_timestamp_ms": rpi_timestamp_ms,
            "nano_timestamp_ms": parsed["nano_timestamp_ms"],
            "ax": parsed["ax"],
            "ay": parsed["ay"],
            "az": parsed["az"],
            "gx": parsed["gx"],
            "gy": parsed["gy"],
            "gz": parsed["gz"],
            "mx": parsed["mx"],
            "my": parsed["my"],
            "mz": parsed["mz"],
        }
 
        runtime.imu_buffer.append(sample)
        runtime.sample_count += 1
 
        if runtime.imu_writer is not None:
            runtime.imu_writer.writerow(
                [
                    rpi_timestamp_ms,
                    sample["nano_timestamp_ms"],
                    sample["ax"],
                    sample["ay"],
                    sample["az"],
                    sample["gx"],
                    sample["gy"],
                    sample["gz"],
                    sample["mx"],
                    sample["my"],
                    sample["mz"],
                    runtime.session_label,
                ]
            )
 
            if runtime.sample_count % 20 == 0 and runtime.imu_file is not None:
                runtime.imu_file.flush()
 
 
async def _ble_stream_loop(runtime: RuntimeState) -> None:
    last_device = None

    while runtime.stop_event is not None and not runtime.stop_event.is_set():
        try:
            if last_device is None:
                with runtime.lock:
                    runtime.latest_error = "Scanning for BLE device..."

                device = await BleakScanner.find_device_by_filter(
                    lambda d, _ad: (
                        (BLE_ADDRESS and (getattr(d, "address", None) == BLE_ADDRESS))
                        or (BLE_ADDRESS and (getattr(d, "identifier", None) == BLE_ADDRESS))
                        or (
                            BLE_DEVICE_NAME
                            and (d.name or "").lower() == BLE_DEVICE_NAME.lower()
                        )
                    ),
                    timeout=BLE_SCAN_TIMEOUT_S,
                )

                if device is None:
                    with runtime.lock:
                        runtime.ble_connected = False
                        runtime.latest_error = (
                            f"BLE scan timeout: name={BLE_DEVICE_NAME}, target={BLE_ADDRESS}"
                        )
                    await asyncio.sleep(BLE_RETRY_DELAY_S)
                    continue

                last_device = device
            else:
                device = last_device

            async with BleakClient(device, timeout=BLE_CONNECT_TIMEOUT_S) as client:
                with runtime.lock:
                    runtime.ble_connected = True
                    runtime.latest_error = ""
 
                await client.start_notify(
                    BLE_CHAR_UUID,
                    lambda _sender, data: _ble_notification_handler(runtime, data),
                )
 
                while runtime.stop_event is not None and not runtime.stop_event.is_set():
                    await asyncio.sleep(0.1)
 
                await client.stop_notify(BLE_CHAR_UUID)
 
        except Exception as exc:
            last_device = None
            with runtime.lock:
                runtime.ble_connected = False
                runtime.latest_error = f"BLE error: {exc}"
 
            if runtime.stop_event is not None and runtime.stop_event.is_set():
                break
 
            await asyncio.sleep(BLE_RETRY_DELAY_S)
 
    with runtime.lock:
        runtime.ble_connected = False
 
 
def _ble_worker(runtime: RuntimeState) -> None:
    try:
        asyncio.run(_ble_stream_loop(runtime))
    except Exception as exc:
        with runtime.lock:
            runtime.latest_error = f"BLE worker failed: {exc}"
            runtime.ble_connected = False
 
 
def _camera_worker(runtime: RuntimeState) -> None:
    picam2: Optional[Picamera2] = None
    frame_interval = 1.0 / float(CAMERA_FPS)
 
    try:
        picam2 = Picamera2()
        config = picam2.create_video_configuration(
            main={"size": CAMERA_SIZE, "format": "RGB888"}
        )
        picam2.configure(config)
        picam2.start()
 
        kernel = np.ones((3, 3), dtype=np.uint8)
 
        while runtime.stop_event is not None and not runtime.stop_event.is_set():
            tick = time.monotonic()
 
            frame_rgb = picam2.capture_array()
            if frame_rgb is None:
                continue

            with runtime.lock:
                hsv_lower = runtime.hsv_lower.copy()
                hsv_upper = runtime.hsv_upper.copy()
                min_contour_area = runtime.min_contour_area
                min_box_side = runtime.min_box_side
                save_raw_frames = runtime.save_raw_frames
                raw_frame_every_n = max(1, runtime.raw_frame_every_n)
                show_mask = runtime.show_mask
 
            if frame_rgb.shape[1] != CAMERA_WIDTH or frame_rgb.shape[0] != CAMERA_HEIGHT:
                frame_rgb = cv2.resize(frame_rgb, CAMERA_SIZE)
 
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
 
            mask = cv2.inRange(hsv, hsv_lower, hsv_upper)
            mask = cv2.GaussianBlur(mask, (5, 5), 0)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
 
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
 
            bbox: Optional[Tuple[int, int, int, int]] = None
            marker: Optional[Tuple[int, int]] = None
 
            if contours:
                contour = max(contours, key=cv2.contourArea)
                if cv2.contourArea(contour) >= min_contour_area:
                    x, y, w, h = cv2.boundingRect(contour)
                    if w >= min_box_side and h >= min_box_side:
                        bbox = (x, y, w, h)
                        marker = (x + (w // 2), y + (h // 2))
 
            annotated_bgr = frame_bgr.copy()
 
            if bbox is not None:
                x, y, w, h = bbox
                cv2.rectangle(annotated_bgr, (x, y), (x + w, y + h), (0, 255, 0), 2)
 
            if marker is not None:
                cv2.circle(annotated_bgr, marker, 4, (0, 255, 0), -1)
 
            with runtime.lock:
                if runtime.trajectory_canvas is None:
                    runtime.trajectory_canvas = np.zeros(
                        (CAMERA_HEIGHT, CAMERA_WIDTH), dtype=np.uint8
                    )
 
                if marker is not None:
                    mx, my = float(marker[0]), float(marker[1])
                    if runtime.smoothed_marker is None:
                        runtime.smoothed_marker = (mx, my)
                    else:
                        sx, sy = runtime.smoothed_marker
                        runtime.smoothed_marker = (
                            (SMOOTHING_ALPHA * mx) + ((1.0 - SMOOTHING_ALPHA) * sx),
                            (SMOOTHING_ALPHA * my) + ((1.0 - SMOOTHING_ALPHA) * sy),
                        )
 
                    smooth_pt = (
                        int(runtime.smoothed_marker[0]),
                        int(runtime.smoothed_marker[1]),
                    )
 
                    if runtime.marker_points:
                        prev = runtime.marker_points[-1]
                        step = float(np.hypot(smooth_pt[0] - prev[0], smooth_pt[1] - prev[1]))
 
                        # Ignore tiny jitter and sudden jumps to keep cleaner strokes.
                        if MIN_POINT_DISTANCE_PX <= step <= MAX_POINT_JUMP_PX:
                            cv2.line(runtime.trajectory_canvas, prev, smooth_pt, 255, 2)
                            runtime.marker_points.append(smooth_pt)
                    else:
                        runtime.marker_points.append(smooth_pt)
 
                if len(runtime.marker_points) >= 2:
                    pts = np.array(runtime.marker_points, dtype=np.int32).reshape((-1, 1, 2))
                    cv2.polylines(annotated_bgr, [pts], False, (0, 255, 255), 2)
 
                runtime.latest_bbox = bbox
                runtime.latest_frame_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
                runtime.latest_mask = mask.copy() if show_mask else None
 
                runtime.frame_count += 1
                frame_idx = runtime.frame_count
 
                session_label = runtime.session_label
                raw_dir = runtime.raw_frame_dir
                frame_manifest_writer = runtime.frame_manifest_writer
                frame_manifest_file = runtime.frame_manifest_file
                video_writer = runtime.video_writer
 
            rpi_timestamp_ms = int(time.time() * 1000)
            frame_name = ""
            if save_raw_frames and frame_idx % raw_frame_every_n == 0:
                frame_name = f"frame_{frame_idx:06d}.jpg"
                frame_path = os.path.join(raw_dir, frame_name)
                cv2.imwrite(frame_path, frame_bgr)
 
            if video_writer is not None:
                video_writer.write(annotated_bgr)
 
            if frame_manifest_writer is not None:
                if marker is None:
                    cx, cy = "", ""
                else:
                    cx, cy = marker
 
                if bbox is None:
                    x, y, w, h = "", "", "", ""
                else:
                    x, y, w, h = bbox
 
                frame_manifest_writer.writerow(
                    [
                        frame_idx,
                        rpi_timestamp_ms,
                        frame_name,
                        cx,
                        cy,
                        x,
                        y,
                        w,
                        h,
                        session_label,
                    ]
                )
 
                if frame_idx % 10 == 0 and frame_manifest_file is not None:
                    frame_manifest_file.flush()
 
            elapsed = time.monotonic() - tick
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
 
    except Exception as exc:
        with runtime.lock:
            runtime.latest_error = f"Camera error: {exc}"
 
    finally:
        if picam2 is not None:
            try:
                picam2.stop()
            except Exception:
                pass
            try:
                picam2.close()
            except Exception:
                pass
 
 
def _open_recording_files(runtime: RuntimeState) -> None:
    runtime.imu_file = open(runtime.imu_path, "w", newline="")
    runtime.imu_writer = csv.writer(runtime.imu_file)
    runtime.imu_writer.writerow(
        [
            "rpi_timestamp_ms",
            "nano_timestamp_ms",
            "ax",
            "ay",
            "az",
            "gx",
            "gy",
            "gz",
            "mx",
            "my",
            "mz",
            "label",
        ]
    )
 
    runtime.frame_manifest_file = open(runtime.frame_manifest_path, "w", newline="")
    runtime.frame_manifest_writer = csv.writer(runtime.frame_manifest_file)
    runtime.frame_manifest_writer.writerow(
        [
            "frame_idx",
            "rpi_timestamp_ms",
            "filename",
            "cx",
            "cy",
            "bbox_x",
            "bbox_y",
            "bbox_w",
            "bbox_h",
            "label",
        ]
    )
 
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    runtime.video_writer = cv2.VideoWriter(runtime.video_path, fourcc, CAMERA_FPS, CAMERA_SIZE)
 
    if runtime.video_writer is not None and not runtime.video_writer.isOpened():
        runtime.video_writer = None
 
 
def _close_recording_files(runtime: RuntimeState) -> None:
    if runtime.video_writer is not None:
        runtime.video_writer.release()
        runtime.video_writer = None
 
    if runtime.imu_file is not None:
        runtime.imu_file.flush()
        runtime.imu_file.close()
        runtime.imu_file = None
        runtime.imu_writer = None
 
    if runtime.frame_manifest_file is not None:
        runtime.frame_manifest_file.flush()
        runtime.frame_manifest_file.close()
        runtime.frame_manifest_file = None
        runtime.frame_manifest_writer = None
 
 
def start_session(runtime: RuntimeState, label: str) -> Tuple[bool, str]:
    with runtime.lock:
        if runtime.is_running:
            return False, "A session is already running."
 
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = f"session_{timestamp}_label_{label}"
        session_dir = os.path.join(DATA_ROOT, session_name)
        raw_frame_dir = os.path.join(session_dir, "raw_frames")
 
        os.makedirs(raw_frame_dir, exist_ok=True)
 
        runtime.sample_count = 0
        runtime.frame_count = 0
        runtime.imu_buffer.clear()
        runtime.marker_points.clear()
        runtime.latest_bbox = None
        runtime.latest_frame_rgb = None
        runtime.smoothed_marker = None
        runtime.latest_mask = None
        runtime.payload_format = "unknown"
        runtime.latest_error = ""
 
        runtime.session_label = label
        runtime.session_dir = session_dir
        runtime.raw_frame_dir = raw_frame_dir
        runtime.session_started_at = time.monotonic()
        runtime.session_started_wallclock_ms = int(time.time() * 1000)
 
        runtime.imu_path = os.path.join(session_dir, "imu.csv")
        runtime.frame_manifest_path = os.path.join(session_dir, "frame_manifest.csv")
        runtime.trajectory_path = os.path.join(session_dir, "trajectory.png")
        runtime.video_path = os.path.join(session_dir, "annotated.mp4")
 
        runtime.trajectory_canvas = np.zeros((CAMERA_HEIGHT, CAMERA_WIDTH), dtype=np.uint8)
 
        runtime.stop_event = threading.Event()
 
        try:
            _open_recording_files(runtime)
        except Exception as exc:
            runtime.latest_error = f"Failed to open recording files: {exc}"
            _close_recording_files(runtime)
            return False, runtime.latest_error
 
        runtime.is_running = True
        runtime.ble_connected = False
 
        runtime.ble_thread = threading.Thread(
            target=_ble_worker,
            args=(runtime,),
            daemon=True,
            name="ble-worker",
        )
        runtime.camera_thread = threading.Thread(
            target=_camera_worker,
            args=(runtime,),
            daemon=True,
            name="camera-worker",
        )
 
        runtime.ble_thread.start()
        runtime.camera_thread.start()
 
    return True, f"Session started: {session_dir}"
 
 
def stop_session(runtime: RuntimeState) -> Tuple[bool, str]:
    with runtime.lock:
        if not runtime.is_running:
            return False, "No active session."
 
        if runtime.stop_event is not None:
            runtime.stop_event.set()
 
        ble_thread = runtime.ble_thread
        camera_thread = runtime.camera_thread
 
    if ble_thread is not None:
        ble_thread.join(timeout=5.0)
 
    if camera_thread is not None:
        camera_thread.join(timeout=5.0)
 
    with runtime.lock:
        _close_recording_files(runtime)
 
        if runtime.trajectory_canvas is not None:
            cv2.imwrite(runtime.trajectory_path, runtime.trajectory_canvas)
 
        metadata_path = os.path.join(runtime.session_dir, "metadata.json")
        duration_s = max(0.0, time.monotonic() - runtime.session_started_at)
        metadata = {
            "label": runtime.session_label,
            "session_dir": runtime.session_dir,
            "duration_s": duration_s,
            "imu_samples": runtime.sample_count,
            "frames_saved": runtime.frame_count,
            "payload_format": runtime.payload_format,
            "ble_address": BLE_ADDRESS,
            "ble_char_uuid": BLE_CHAR_UUID,
            "camera_size": [CAMERA_WIDTH, CAMERA_HEIGHT],
            "camera_fps": CAMERA_FPS,
        }
 
        with open(metadata_path, "w") as meta_file:
            json.dump(metadata, meta_file, indent=2)
 
        runtime.last_saved_session_dir = runtime.session_dir
        runtime.is_running = False
        runtime.ble_connected = False
        runtime.stop_event = None
        runtime.ble_thread = None
        runtime.camera_thread = None
 
    return True, f"Session saved: {runtime.last_saved_session_dir}"
 
 
def get_snapshot(runtime: RuntimeState) -> Dict[str, Any]:
    with runtime.lock:
        frame = None if runtime.latest_frame_rgb is None else runtime.latest_frame_rgb.copy()
        trajectory = (
            None if runtime.trajectory_canvas is None else runtime.trajectory_canvas.copy()
        )
        mask = None if runtime.latest_mask is None else runtime.latest_mask.copy()
        imu_samples = list(runtime.imu_buffer)
 
        snapshot = {
            "is_running": runtime.is_running,
            "ble_connected": runtime.ble_connected,
            "sample_count": runtime.sample_count,
            "frame_count": runtime.frame_count,
            "payload_format": runtime.payload_format,
            "latest_error": runtime.latest_error,
            "label": runtime.session_label,
            "session_dir": runtime.session_dir,
            "last_saved_session_dir": runtime.last_saved_session_dir,
            "started_at": runtime.session_started_at,
            "frame": frame,
            "trajectory": trajectory,
            "mask": mask,
            "imu_samples": imu_samples,
        }
 
    return snapshot
 
 
def build_plot_df(imu_samples: List[Dict[str, Any]]) -> pd.DataFrame:
    if not imu_samples:
        return pd.DataFrame()
 
    df = pd.DataFrame(imu_samples)
    t0 = df["rpi_timestamp_ms"].iloc[0]
    df["time_s"] = (df["rpi_timestamp_ms"] - t0) / 1000.0
    return df
 
 
def show_image_compat(image: np.ndarray, channels: str = "RGB") -> None:
    """Render images across Streamlit versions without API-kwarg crashes."""
    params = inspect.signature(st.image).parameters
    if "use_container_width" in params:
        st.image(image, channels=channels, use_container_width=True)
    elif "use_column_width" in params:
        st.image(image, channels=channels, use_column_width=True)
    else:
        st.image(image, channels=channels)
 
 
runtime = get_runtime()
 
st.title("RPi Air Writing Dashboard")
 
with st.sidebar:
    st.subheader("Session")
 
    selected_label = st.selectbox("Digit label", LABELS, index=0)

    st.subheader("Camera tuning")
    hue_range = st.slider(
        "Hue range",
        0,
        179,
        (int(runtime.hsv_lower[0]), int(runtime.hsv_upper[0])),
    )
    sat_range = st.slider(
        "Saturation range",
        0,
        255,
        (int(runtime.hsv_lower[1]), int(runtime.hsv_upper[1])),
    )
    val_range = st.slider(
        "Value range",
        0,
        255,
        (int(runtime.hsv_lower[2]), int(runtime.hsv_upper[2])),
    )
    min_contour_area = st.slider(
        "Min contour area",
        50,
        2000,
        int(runtime.min_contour_area),
    )
    min_box_side = st.slider(
        "Min box side (px)",
        4,
        80,
        int(runtime.min_box_side),
    )
    save_raw_frames = st.checkbox("Save raw frames", value=runtime.save_raw_frames)
    raw_frame_every_n = st.slider(
        "Raw frame stride",
        1,
        30,
        int(runtime.raw_frame_every_n),
    )
    show_mask = st.checkbox("Show mask preview", value=runtime.show_mask)

    with runtime.lock:
        runtime.hsv_lower = np.array(
            [hue_range[0], sat_range[0], val_range[0]], dtype=np.uint8
        )
        runtime.hsv_upper = np.array(
            [hue_range[1], sat_range[1], val_range[1]], dtype=np.uint8
        )
        runtime.min_contour_area = int(min_contour_area)
        runtime.min_box_side = int(min_box_side)
        runtime.save_raw_frames = bool(save_raw_frames)
        runtime.raw_frame_every_n = int(raw_frame_every_n)
        runtime.show_mask = bool(show_mask)
 
    start_clicked = st.button(
        "Start",
        type="primary",
        disabled=runtime.is_running,
        use_container_width=True,
    )
 
    end_clicked = st.button(
        "End",
        type="secondary",
        disabled=not runtime.is_running,
        use_container_width=True,
    )
 
    if start_clicked:
        ok, message = start_session(runtime, selected_label)
        if ok:
            st.success(message)
        else:
            st.error(message)
        st.rerun()
 
    if end_clicked:
        ok, message = stop_session(runtime)
        if ok:
            st.success(message)
        else:
            st.error(message)
        st.rerun()
 
    snapshot = get_snapshot(runtime)
 
    st.markdown("---")
    st.caption(f"BLE address: {BLE_ADDRESS}")
    st.caption(f"Characteristic: {BLE_CHAR_UUID}")
 
    if snapshot["is_running"]:
        state_text = "CONNECTED" if snapshot["ble_connected"] else "RECONNECTING"
        st.metric("BLE status", state_text)
        st.metric("IMU samples", snapshot["sample_count"])
        st.metric("Frames", snapshot["frame_count"])
 
        elapsed = max(0.0, time.monotonic() - snapshot["started_at"])
        hz = (snapshot["sample_count"] / elapsed) if elapsed > 0 else 0.0
        st.metric("Approx rate", f"{hz:.1f} Hz")
        st.metric("Payload", snapshot["payload_format"])
        st.caption(f"Label: {snapshot['label']}")
    else:
        st.metric("BLE status", "IDLE")
        if snapshot["last_saved_session_dir"]:
            st.caption(f"Last session: {snapshot['last_saved_session_dir']}")
 
    if snapshot["latest_error"]:
        st.warning(snapshot["latest_error"])
 
 
camera_col, trajectory_col = st.columns(2)
 
with camera_col:
    st.subheader("Live camera")
    if snapshot["frame"] is not None:
        show_image_compat(snapshot["frame"], channels="RGB")
    else:
        st.info("No camera frame yet. Press Start to begin.")
    if show_mask and snapshot["mask"] is not None:
        st.caption("Mask preview")
        mask_rgb = cv2.cvtColor(snapshot["mask"], cv2.COLOR_GRAY2RGB)
        show_image_compat(mask_rgb, channels="RGB")
 
with trajectory_col:
    st.subheader("Trajectory")
    if snapshot["trajectory"] is not None:
        trajectory_rgb = cv2.cvtColor(snapshot["trajectory"], cv2.COLOR_GRAY2RGB)
        show_image_compat(trajectory_rgb, channels="RGB")
    else:
        st.info("Trajectory will appear after tracking starts.")
 
 
st.subheader("IMU live plots")
df_plot = build_plot_df(snapshot["imu_samples"])
 
if not df_plot.empty:
    c1, c2, c3 = st.columns(3)
 
    with c1:
        st.caption("Accelerometer (g)")
        st.line_chart(
            df_plot,
            x="time_s",
            y=["ax", "ay", "az"],
            color=["#ff4b4b", "#1f77b4", "#2ca02c"],
            height=260,
        )
 
    with c2:
        st.caption("Gyroscope (dps)")
        st.line_chart(
            df_plot,
            x="time_s",
            y=["gx", "gy", "gz"],
            color=["#ff7f0e", "#17becf", "#9467bd"],
            height=260,
        )
 
    with c3:
        st.caption("Magnetometer")
        st.line_chart(
            df_plot,
            x="time_s",
            y=["mx", "my", "mz"],
            color=["#8c564b", "#e377c2", "#7f7f7f"],
            height=260,
        )
else:
    st.info("Waiting for IMU notifications from Nano BLE.")
 
 
if snapshot["is_running"]:
    time.sleep(UI_REFRESH_SECONDS)
    st.rerun()
 