# allow-bot

Background automation that monitors a VDI window and auto-clicks the GitHub Copilot "Allow" permission dialog with human-like mouse movement and timing.

## How it works

Uses Xlib to capture the target window and OpenCV template matching to detect the dialog. When detected, it moves the mouse along natural cubic Bézier curves, applies human reaction delays, randomized landing points within the button bounds, and realistic click dwell times before triggering the click.

## Requirements

- Linux/X11
- Python 3

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env` and adjust as needed:

| Variable             | Default       | Description                                                 |
|----------------------|---------------|-------------------------------------------------------------|
| `WINDOW_TITLE`       | `Citrix`      | Partial title of the target window                          |
| `SCAN_INTERVAL`      | `0.8`         | Seconds between scans                                       |
| `MATCH_THRESHOLD`    | `0.80`        | OpenCV match confidence threshold                           |
| `CLICK_COOLDOWN`     | `2.0`         | Seconds between clicks                                      |
| `REF_IMAGES_DIR`     | `ref_images/` | Directory with template images                              |
| `HUMAN_LIKE`         | `1`           | Enable human-like mouse curves and randomized delays        |
| `HUMAN_MIN_REACTION` | `0.20`        | Minimum reaction delay in seconds before moving             |
| `HUMAN_MAX_REACTION` | `0.50`        | Maximum reaction delay in seconds before moving             |
| `HUMAN_MOUSE_SPEED`  | `1.0`         | Movement speed factor (1.0 = normal, higher = faster)       |
| `HUMAN_SCAN_JITTER`  | `1`           | Add random timing variance to screen polling                |
| `DEBUG`              | `0`           | Set to `1` for verbose logging                              |

## Usage

```bash
python bot.py start
python bot.py stop
python bot.py status
```

Logs are written to `bot.log`. Metrics are saved to `metrics.json`.
