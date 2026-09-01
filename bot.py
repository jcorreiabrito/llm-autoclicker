#!/usr/bin/env python3
"""
Allow-Bot
Ultra-lightweight background automation that monitors a target VDI window
and clicks the GitHub Copilot "Allow" permission dialog automatically.

Includes advanced human-like neuromuscular mouse movement:
- Asymmetric acceleration profiles (fast ballistic launch -> long homing deceleration)
- Randomized Bézier curve trajectories and dynamic velocity
- Correlated low-frequency hand sway / physiological tremor
- Submovement overshoot and corrective adjustments
- Natural reaction delays and realistic click dwell times
"""

import os
import sys
import time
import signal
import logging
import gc
import math
import random
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

WINDOW_TITLE = (os.getenv("WINDOW_TITLE") or os.getenv("CITRIX_WINDOW_TITLE", "Citrix")).strip()
SCAN_INTERVAL = float(os.getenv("SCAN_INTERVAL", "0.8"))
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.80"))
REF_IMAGES_DIR = PROJECT_DIR / os.getenv("REF_IMAGES_DIR", "ref_images")
LOG_FILE = PROJECT_DIR / os.getenv("LOG_FILE", "bot.log")
PID_FILE = PROJECT_DIR / os.getenv("PID_FILE", "bot.pid")
CLICK_COOLDOWN = float(os.getenv("CLICK_COOLDOWN", "2.0"))
DEBUG = int(os.getenv("DEBUG", "0")) == 1

# Human-like simulation settings
HUMAN_LIKE = int(os.getenv("HUMAN_LIKE", "1")) == 1
HUMAN_MIN_REACTION = float(os.getenv("HUMAN_MIN_REACTION", "0.20"))
HUMAN_MAX_REACTION = float(os.getenv("HUMAN_MAX_REACTION", "0.50"))
HUMAN_MOUSE_SPEED = float(os.getenv("HUMAN_MOUSE_SPEED", "1.0"))
HUMAN_SCAN_JITTER = int(os.getenv("HUMAN_SCAN_JITTER", "1")) == 1

# Setup logging
log_level = logging.DEBUG if DEBUG else logging.INFO
log_formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("allow_bot")
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

def get_target_window_geometry(target_title: str):
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

def get_current_pointer():
    """Returns the current (x, y) coordinates of the mouse cursor."""
    if not has_x11 or x11_root is None:
        return 0, 0
    try:
        data = x11_root.query_pointer()._data
        return data["root_x"], data["root_y"]
    except Exception as e:
        logger.debug("Failed to query pointer: %s", e)
        return 0, 0

def bezier_point(p0, p1, p2, p3, t: float):
    """Calculates a point along a Cubic Bézier curve at parameter t (0.0 to 1.0)."""
    u = 1.0 - t
    tt = t * t
    uu = u * u
    x = uu * u * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + tt * t * p3[0]
    y = uu * u * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + tt * t * p3[1]
    return int(round(x)), int(round(y))

def asymmetric_ease(t: float, alpha: float, beta: float) -> float:
    """
    Computes an asymmetric ease curve based on randomized Beta distribution parameters.
    Reaches peak velocity early (~30-40% of trajectory) and provides a longer deceleration tail.
    """
    t_clamped = max(0.0, min(1.0, t))
    nom = t_clamped ** alpha
    den = nom + ((1.0 - t_clamped) ** beta) + 1e-6
    return nom / den

def move_mouse_humanlike(target_x: int, target_y: int, speed_factor: float = 1.0):
    """
    Moves mouse along a human-like neuromuscular trajectory with:
    - Asymmetric acceleration (fast launch -> gentle homing)
    - Dynamic velocity & randomized curvature
    - Momentum-based hand drift / sway
    - Submovement overshoot and corrective adjustment
    """
    if not has_x11 or x11_display is None:
        return

    start_x, start_y = get_current_pointer()
    distance = math.hypot(target_x - start_x, target_y - start_y)
    if distance < 4:
        xtest.fake_input(x11_display, X.MotionNotify, x=target_x, y=target_y)
        x11_display.sync()
        return

    # 1. Decide if this movement will overshoot slightly (30% probability on long distance)
    will_overshoot = (random.random() < 0.30) and (distance > 70)
    if will_overshoot:
        angle = math.atan2(target_y - start_y, target_x - start_x)
        overshoot_dist = random.uniform(5, 14)
        inter_target_x = int(target_x + math.cos(angle) * overshoot_dist + random.uniform(-4, 4))
        inter_target_y = int(target_y + math.sin(angle) * overshoot_dist + random.uniform(-4, 4))
    else:
        inter_target_x, inter_target_y = target_x, target_y

    # 2. Randomized acceleration curve exponents for this specific movement
    alpha = random.uniform(1.8, 2.4)   # Controls initial acceleration burst
    beta = random.uniform(2.8, 4.2)    # Controls deceleration homing tail

    # 3. Dynamic duration based on Fitts's law + speed profile
    base_duration = (0.16 + (distance / 1500.0) * random.uniform(0.75, 1.25)) / max(0.1, speed_factor)
    steps = max(18, int(distance / 10))
    base_step_delay = base_duration / steps

    # 4. Bézier control points with randomized curvature
    deviation = distance * random.uniform(0.10, 0.25)
    ang = math.atan2(inter_target_y - start_y, inter_target_x - start_x)
    norm_ang = ang + (math.pi / 2) * random.choice([-1, 1])

    c1 = (
        start_x + math.cos(ang) * distance * 0.3 + math.cos(norm_ang) * deviation * random.uniform(0.6, 1.0),
        start_y + math.sin(ang) * distance * 0.3 + math.sin(norm_ang) * deviation * random.uniform(0.6, 1.0),
    )
    c2 = (
        start_x + math.cos(ang) * distance * 0.7 + math.cos(norm_ang) * deviation * random.uniform(0.1, 0.5),
        start_y + math.sin(ang) * distance * 0.7 + math.sin(norm_ang) * deviation * random.uniform(0.1, 0.5),
    )

    # 5. Execute primary flight with correlated hand drift & dynamic step timing
    drift_x, drift_y = 0.0, 0.0
    for i in range(1, steps + 1):
        raw_progress = i / steps
        t = asymmetric_ease(raw_progress, alpha, beta)

        px, py = bezier_point((start_x, start_y), c1, c2, (inter_target_x, inter_target_y), t)

        # Correlated hand sway (momentum drift)
        drift_x = drift_x * 0.75 + random.uniform(-0.6, 0.6)
        drift_y = drift_y * 0.75 + random.uniform(-0.6, 0.6)

        if i < steps:
            px += int(round(drift_x))
            py += int(round(drift_y))

        xtest.fake_input(x11_display, X.MotionNotify, x=px, y=py)
        x11_display.sync()

        # Variable delta-t: micro-randomized timing jitter per step
        jittered_delay = base_step_delay * random.uniform(0.85, 1.15)
        time.sleep(jittered_delay)

    # 6. Corrective submovement if overshot
    if will_overshoot:
        time.sleep(random.uniform(0.02, 0.05))  # Micro-pause before correction
        correct_steps = random.randint(4, 7)
        cur_x, cur_y = get_current_pointer()
        for j in range(1, correct_steps + 1):
            ct = j / correct_steps
            # Linear/smooth step for micro-settling
            st = ct * ct * (3.0 - 2.0 * ct)
            cx = int(cur_x + (target_x - cur_x) * st)
            cy = int(cur_y + (target_y - cur_y) * st)
            xtest.fake_input(x11_display, X.MotionNotify, x=cx, y=cy)
            display.sync()
            time.sleep(random.uniform(0.008, 0.018))

    # Final position confirmation
    xtest.fake_input(x11_display, X.MotionNotify, x=target_x, y=target_y)
    x11_display.sync()

def click_screen_box(box_x: int, box_y: int, box_w: int, box_h: int):
    """Simulates a human-like or instant left mouse click inside a bounding box."""
    if not has_x11 or x11_display is None:
        logger.error("Cannot click: X11 display is unavailable.")
        return False
    
    try:
        if HUMAN_LIKE:
            # 1. Cognitive reaction delay (random hesitation before responding)
            reaction_delay = random.uniform(HUMAN_MIN_REACTION, HUMAN_MAX_REACTION)
            time.sleep(reaction_delay)

            # 2. Pick a randomized landing point within button boundaries (inner 20%-80%)
            pad_w = int(box_w * 0.20)
            pad_h = int(box_h * 0.20)
            min_x = box_x + pad_w
            max_x = box_x + max(pad_w, box_w - pad_w)
            min_y = box_y + pad_h
            max_y = box_y + max(pad_h, box_h - pad_h)

            target_x = random.randint(min_x, max_x)
            target_y = random.randint(min_y, max_y)

            # 3. Smooth neuromuscular mouse movement
            move_mouse_humanlike(target_x, target_y, speed_factor=HUMAN_MOUSE_SPEED)

            # 4. Pre-click micro hesitation (30ms - 80ms)
            time.sleep(random.uniform(0.03, 0.08))

            # 5. Click with realistic down/up dwell time
            xtest.fake_input(x11_display, X.ButtonPress, 1)
            x11_display.sync()
            time.sleep(random.uniform(0.05, 0.12))
            xtest.fake_input(x11_display, X.ButtonRelease, 1)
            x11_display.sync()
        else:
            # Instant snap and click
            center_x = box_x + (box_w // 2)
            center_y = box_y + (box_h // 2)
            xtest.fake_input(x11_display, X.MotionNotify, x=center_x, y=center_y)
            xtest.fake_input(x11_display, X.ButtonPress, 1)
            xtest.fake_input(x11_display, X.ButtonRelease, 1)
            x11_display.sync()

        return True
    except Exception as e:
        logger.error("Error simulating click at (%d, %d, %dx%d): %s", box_x, box_y, box_w, box_h, e)
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

def run_bot():
    if not has_x11:
        logger.critical("X11 display could not be opened. Terminating.")
        sys.exit(1)

    write_pid()
    mode_str = "HUMAN-LIKE (Asymmetric Bézier curves + submovement correction)" if HUMAN_LIKE else "INSTANT"
    logger.info("Allow-Bot started (PID: %d) [Mode: %s]", os.getpid(), mode_str)
    logger.info(
        "Settings: target='%s', threshold=%.2f, interval=%.2fs, cooldown=%.2fs",
        WINDOW_TITLE,
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
                        "No reference images found in '%s'. Run 'python capture.py' to save the target button.",
                        REF_IMAGES_DIR.name,
                    )
                time.sleep(SCAN_INTERVAL)
                continue

            # Find target window
            win_info = get_target_window_geometry(WINDOW_TITLE)
            if not win_info:
                now = time.time()
                if now - last_window_missing_log > 30.0:
                    logger.info(
                        "Window containing '%s' not found. Standing by...",
                        WINDOW_TITLE,
                    )
                    last_window_missing_log = now
                time.sleep(SCAN_INTERVAL)
                continue

            win_x, win_y, win_w, win_h, win_title = win_info

            # Capture only the target window region
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
                    btn_screen_x = win_x + match_x
                    btn_screen_y = win_y + match_y

                    logger.info(
                        "TARGET MATCHED! Template '%s' (score: %.3f >= %.2f). Initiating click at (%d, %d, %dx%d)...",
                        tpl_name,
                        max_val,
                        MATCH_THRESHOLD,
                        btn_screen_x,
                        btn_screen_y,
                        tw,
                        th,
                    )

                    clicked = click_screen_box(btn_screen_x, btn_screen_y, tw, th)
                    if clicked:
                        metrics.record_click(tpl_name)
                    del res
                    break

                del res

            # Release frame from memory and collect garbage
            del frame_gray
            if iteration % 25 == 0:
                gc.collect()

            metrics.update_runtime()

            if clicked:
                logger.info("Entering cooldown (%.2fs)...", CLICK_COOLDOWN)
                time.sleep(CLICK_COOLDOWN)
            else:
                elapsed = time.time() - loop_start
                target_interval = SCAN_INTERVAL
                if HUMAN_SCAN_JITTER and HUMAN_LIKE:
                    target_interval += random.uniform(-0.15 * SCAN_INTERVAL, 0.20 * SCAN_INTERVAL)
                sleep_time = max(0.05, target_interval - elapsed)
                time.sleep(sleep_time)

    except Exception as e:
        logger.exception("Unexpected error in main loop: %s", e)
    finally:
        metrics.save_final()
        remove_pid()
        logger.info("Allow-Bot stopped cleanly.")

def cmd_status():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            print(f"allow-bot is running (PID: {pid})")
            return 0
        except (ProcessLookupError, ValueError):
            print("PID file exists but process is not running (stale PID).")
            return 1
        except PermissionError:
            print("allow-bot is running (permission denied to check details).")
            return 0
    else:
        print("allow-bot is stopped.")
        return 1

def cmd_stop():
    if not PID_FILE.exists():
        print("allow-bot is not running (no PID file found).")
        return 0
    try:
        pid = int(PID_FILE.read_text().strip())
        print(f"Stopping allow-bot (PID: {pid})...")
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                print("Stopped successfully.")
                if PID_FILE.exists():
                    PID_FILE.unlink()
                return 0
        print("Process did not stop gracefully, sending SIGKILL...")
        os.kill(pid, signal.SIGKILL)
        if PID_FILE.exists():
            PID_FILE.unlink()
        print("Stopped.")
        return 0
    except (ProcessLookupError, ValueError):
        print("Process was not running. Cleaning up stale PID file.")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return 0
    except Exception as e:
        print(f"Error stopping bot: {e}")
        return 1

def main():
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "start"
    if action == "stop":
        sys.exit(cmd_stop())
    elif action == "status":
        sys.exit(cmd_status())
    elif action in ("start", "run"):
        run_bot()
    elif action in ("-h", "--help", "help"):
        print("Usage: python bot.py [start|stop|status]")
        sys.exit(0)
    else:
        print(f"Unknown action '{action}'. Usage: python bot.py [start|stop|status]")
        sys.exit(1)

if __name__ == "__main__":
    main()
