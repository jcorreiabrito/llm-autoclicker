#!/usr/bin/env python3
"""
Citrix Copilot Allow-Bot
Ultra-lightweight background automation that monitors a Citrix VDI window
and clicks the GitHub Copilot "Allow" permission dialog automatically.

Optimized for Linux/X11 with direct Xlib + OpenCV headless template matching.
Steady-state memory footprint: ~45-55 MB RSS.
"""

import os
import sys
import time
import signal
import logging
import gc
import subprocess
from pathlib import Path
import cv2
import numpy as np
from dotenv import load_dotenv
import json
import datetime

# Load configuration from .env
PROJECT_DIR = Path(__file__).resolve().parent
ENV_PATH = PROJECT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

SCAN_INTERVAL = float(os.getenv("SCAN_INTERVAL", "0.8"))
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.80"))
CITRIX_WINDOW_TITLE = os.getenv("CITRIX_WINDOW_TITLE", "Citrix").strip()
REF_IMAGES_DIR = PROJECT_DIR / os.getenv("REF_IMAGES_DIR", "ref_images")
LOG_FILE = PROJECT_DIR / os.getenv("LOG_FILE", "bot.log")
PID_FILE = PROJECT_DIR / os.getenv("PID_FILE", "bot.pid")
CLICK_COOLDOWN = float(os.getenv("CLICK_COOLDOWN", "2.0"))
DEBUG = int(os.getenv("DEBUG", "0")) == 1

# Setup logging
log_level = logging.DEBUG if DEBUG else logging.INFO
log_formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("citrix_allow_bot")
logger.setLevel(log_level)
logger.handlers.clear()

fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setFormatter(log_formatter)
logger.addHandler(fh)

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(log_formatter)
logger.addHandler(ch)

# Initialize X11 Display
try:
    from Xlib import display, X
    from Xlib.ext import xtest
    x11_display = display.Display()
    x11_root = x11_display.screen().root
    has_x11 = True
except Exception as e:
    x11_display = None
    x11_root = None
    has_x11 = False
    logger.error("X11 display initialization failed: %s", e)

running = True

def handle_exit(signum, frame):
    global running
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    logger.info("Received termination signal (%s). Exiting gracefully...", sig_name)
    running = False

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

def write_pid():
    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write PID file: %s", e)

def remove_pid():
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception as e:
        logger.warning("Failed to remove PID file: %s", e)

def get_citrix_window_geometry(target_title: str):
    """
    Finds the window matching target_title using wmctrl -l -G.
    Returns (x, y, width, height, title) or None.
    """
    if not target_title:
        return None

    try:
        proc = subprocess.run(
            ["wmctrl", "-l", "-G"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1,
        )
        if proc.returncode == 0:
            target_lower = target_title.lower()
            candidates = []
            for line in proc.stdout.strip().splitlines():
                parts = line.split(None, 7)
                if len(parts) >= 8:
                    wid, desktop, x_str, y_str, w_str, h_str, machine, title = parts
                    if target_lower in title.lower():
                        try:
                            x, y, w, h = int(x_str), int(y_str), int(w_str), int(h_str)
                            if w > 50 and h > 50:
                                candidates.append((x, y, w, h, title))
                        except ValueError:
                            continue
            if candidates:
                # Return the largest window if multiple match
                candidates.sort(key=lambda item: item[2] * item[3], reverse=True)
                return candidates[0]
    except Exception as e:
        logger.debug("wmctrl query error: %s", e)

    return None

def capture_x11_region(x: int, y: int, width: int, height: int):
    """Captures a screen region directly via X11 without subprocess or disk I/O."""
    if not has_x11 or x11_root is None:
        return None
    try:
        raw = x11_root.get_image(x, y, width, height, X.ZPixmap, 0xffffffff)
        frame = np.frombuffer(raw.data, dtype=np.uint8).reshape((height, width, 4))
        # Convert BGRA/BGRX to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        return gray
    except Exception as e:
        logger.error("Failed to capture X11 region (%d, %d, %d, %d): %s", x, y, width, height, e)
        return None

def click_screen_point(x: int, y: int):
    """Simulates a left mouse click at absolute coordinates (x, y) using XTest."""
    if not has_x11 or x11_display is None:
        logger.error("Cannot click: X11 display is unavailable.")
        return False
    try:
        xtest.fake_input(x11_display, X.MotionNotify, x=x, y=y)
        xtest.fake_input(x11_display, X.ButtonPress, 1)
        xtest.fake_input(x11_display, X.ButtonRelease, 1)
        x11_display.sync()
        return True
    except Exception as e:
        logger.error("Error simulating click at (%d, %d): %s", x, y, e)
        return False

class MetricsTracker:
    def __init__(self, metrics_file: Path):
        self.metrics_file = metrics_file
        self.data = self._load()
        self.start_time = time.time()
        self.last_save_time = time.time()

    def _load(self):
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading metrics: {e}")
        return {}

    def _save(self):
        try:
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving metrics: {e}")

    def get_today_record(self):
        today = datetime.date.today().isoformat()
        if today not in self.data:
            self.data[today] = {"run_time_seconds": 0, "clicks": {}}
        return self.data[today]

    def record_click(self, button_name: str):
        record = self.get_today_record()
        record["clicks"][button_name] = record["clicks"].get(button_name, 0) + 1
        self._save()

    def update_runtime(self):
        now = time.time()
        elapsed = now - self.start_time
        self.start_time = now
        
        record = self.get_today_record()
        record["run_time_seconds"] += elapsed
        
        if now - self.last_save_time > 60:
            self._save()
            self.last_save_time = now

    def save_final(self):
        self.update_runtime()
        self._save()

def load_templates(ref_dir: Path):
    """Loads reference button images from ref_dir as grayscale numpy arrays."""
    templates = []
    if not ref_dir.exists():
        return templates

    valid_exts = {".png", ".jpg", ".jpeg"}
    for img_path in sorted(ref_dir.iterdir()):
        if img_path.is_file() and img_path.suffix.lower() in valid_exts:
            tpl = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if tpl is not None:
                th, tw = tpl.shape[:2]
                templates.append((img_path.name, tpl, tw, th))
                logger.debug("Loaded reference template: %s (%dx%d)", img_path.name, tw, th)
            else:
                logger.warning("Could not parse image: %s", img_path.name)
    return templates

def main():
    if not has_x11:
        logger.critical("X11 display could not be opened. Terminating.")
        sys.exit(1)

    write_pid()
    logger.info("Citrix Copilot Allow-Bot started (PID: %d)", os.getpid())
    logger.info(
        "Settings: target='%s', threshold=%.2f, interval=%.2fs, cooldown=%.2fs",
        CITRIX_WINDOW_TITLE,
        MATCH_THRESHOLD,
        SCAN_INTERVAL,
        CLICK_COOLDOWN,
    )

    templates = load_templates(REF_IMAGES_DIR)
    last_template_check = time.time()
    last_window_missing_log = 0.0
    iteration = 0

    metrics = MetricsTracker(PROJECT_DIR / "metrics.json")

    try:
        while running:
            iteration += 1
            loop_start = time.time()

            # Hot-reload reference templates periodically (every 5 seconds)
            if time.time() - last_template_check > 5.0:
                templates = load_templates(REF_IMAGES_DIR)
                last_template_check = time.time()

            if not templates:
                if iteration % 15 == 1:
                    logger.warning(
                        "No reference images found in '%s'. Run 'python capture.py' to save the 'Allow' button.",
                        REF_IMAGES_DIR.name,
                    )
                time.sleep(SCAN_INTERVAL)
                continue

            # Find Citrix window
            win_info = get_citrix_window_geometry(CITRIX_WINDOW_TITLE)
            if not win_info:
                now = time.time()
                if now - last_window_missing_log > 30.0:
                    logger.info(
                        "Window containing '%s' not found. Standing by...",
                        CITRIX_WINDOW_TITLE,
                    )
                    last_window_missing_log = now
                time.sleep(SCAN_INTERVAL)
                continue

            win_x, win_y, win_w, win_h, win_title = win_info

            # Capture only the Citrix window region
            frame_gray = capture_x11_region(win_x, win_y, win_w, win_h)
            if frame_gray is None:
                time.sleep(SCAN_INTERVAL)
                continue

            clicked = False
            for tpl_name, tpl_img, tw, th in templates:
                if frame_gray.shape[0] < th or frame_gray.shape[1] < tw:
                    continue

                res = cv2.matchTemplate(frame_gray, tpl_img, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                if DEBUG:
                    logger.debug("Template '%s' max confidence: %.3f", tpl_name, max_val)

                if max_val >= MATCH_THRESHOLD:
                    match_x, match_y = max_loc
                    center_x = win_x + match_x + (tw // 2)
                    center_y = win_y + match_y + (th // 2)

                    logger.info(
                        "TARGET MATCHED! Template '%s' (score: %.3f >= %.2f). Clicking at screen (%d, %d)",
                        tpl_name,
                        max_val,
                        MATCH_THRESHOLD,
                        center_x,
                        center_y,
                    )

                    clicked = click_screen_point(center_x, center_y)
                    if clicked:
                        metrics.record_click(tpl_name)
                    del res
                    break

                del res

            # Release frame from memory and collect garbage to guarantee RAM < 60 MB
            del frame_gray
            if iteration % 25 == 0:
                gc.collect()

            metrics.update_runtime()

            if clicked:
                logger.info("Entering cooldown (%.2fs)...", CLICK_COOLDOWN)
                time.sleep(CLICK_COOLDOWN)
            else:
                elapsed = time.time() - loop_start
                sleep_time = max(0.05, SCAN_INTERVAL - elapsed)
                time.sleep(sleep_time)

    except Exception as e:
        logger.exception("Unexpected error in main loop: %s", e)
    finally:
        metrics.save_final()
        remove_pid()
        logger.info("Citrix Copilot Allow-Bot stopped cleanly.")

if __name__ == "__main__":
    main()
