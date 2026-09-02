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
| `HUMAN_MIN_REACTION` | `0.15`        | Minimum reaction delay in seconds before moving             |
| `HUMAN_MAX_REACTION` | `0.35`        | Maximum reaction delay in seconds before moving             |
| `HUMAN_MOUSE_SPEED`  | `1.5`         | Movement speed factor (1.0 = normal, higher = faster)       |
| `HUMAN_SCAN_JITTER`  | `1`           | Add random timing variance to screen polling                |
| `DEBUG`              | `0`           | Set to `1` for verbose logging                              |

## Usage

```bash
# Start bot (uses HUMAN_LIKE setting from .env by default)
python bot.py start

# Run with instant snap-and-click mode (no delays or mouse curves)
python bot.py start --instant
# or shorthand:
python bot.py -i

# Run with human-like Bézier mouse movement
python bot.py start --human

# Override mouse speed factor on the fly
python bot.py start --human --speed 2.0

# Management commands
python bot.py status
python bot.py stop
```

Logs are written to `bot.log`. Metrics are saved to `metrics.json`.
