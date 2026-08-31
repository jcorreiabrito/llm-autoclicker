# citrix-allow-bot

Background automation that monitors a Citrix VDI window and auto-clicks the GitHub Copilot "Allow" permission dialog.

## How it works

Uses Xlib to capture the Citrix window and OpenCV template matching to detect the dialog, then clicks it automatically. Runs as a daemon with a PID file.

## Requirements

- Linux/X11
- Python 3
- A Citrix VDI window with a title matching `CITRIX_WINDOW_TITLE`

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env` and adjust as needed:

| Variable              | Default       | Description                        |
|-----------------------|---------------|------------------------------------|
| `CITRIX_WINDOW_TITLE` | `Citrix`      | Partial title of the Citrix window |
| `SCAN_INTERVAL`       | `0.8`         | Seconds between scans              |
| `MATCH_THRESHOLD`     | `0.80`        | OpenCV match confidence threshold  |
| `CLICK_COOLDOWN`      | `2.0`         | Seconds between clicks             |
| `REF_IMAGES_DIR`      | `ref_images/` | Directory with template images     |
| `DEBUG`               | `0`           | Set to `1` for verbose logging     |

## Usage

```bash
python bot.py start
python bot.py stop
python bot.py status
```

Logs are written to `bot.log`. Metrics are saved to `metrics.json`.
