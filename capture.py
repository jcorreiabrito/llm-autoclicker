#!/usr/bin/env python3
"""
Citrix Allow-Bot Reference Image Capture Helper
Captures a reference screenshot (e.g. of the "Allow" button) and saves it to ref_images/.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parent
REF_DIR = PROJECT_DIR / "ref_images"

def print_help():
    print("""Citrix Allow-Bot Capture Utility
Usage:
  python capture.py [filename.png]
  python capture.py --help

Examples:
  python capture.py                     # Saves to ref_images/allow_button.png
  python capture.py allow_secondary.png # Saves to ref_images/allow_secondary.png

How to use:
  1. Open your Citrix VDI window with VS Code and trigger the Copilot "Allow" dialog.
  2. Run 'python capture.py'.
  3. Your mouse pointer will become a crosshair.
  4. Click and drag a tight box around ONLY the 'Allow' button.
  5. The cropped image will be saved directly into ref_images/.
""")

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help", "help"):
        print_help()
        sys.exit(0)

    REF_DIR.mkdir(parents=True, exist_ok=True)
    
    target_name = sys.argv[1] if len(sys.argv) > 1 else "allow_button.png"
    if not target_name.lower().endswith((".png", ".jpg", ".jpeg")):
        target_name += ".png"
    
    target_path = REF_DIR / target_name
    print(f"=== Capture Reference Button Image ===")
    print(f"Target file: {target_path}")

    # Detect capture tools
    tools = []
    if shutil.which("import"):
        tools.append(("import", ["import", str(target_path)], "ImageMagick 'import' (click & drag rectangle)"))
    if shutil.which("scrot"):
        tools.append(("scrot", ["scrot", "-s", str(target_path)], "scrot -s (click & drag rectangle)"))
    if shutil.which("spectacle"):
        tools.append(("spectacle", ["spectacle", "-r", "-b", "-n", "-o", str(target_path)], "KDE Spectacle rectangular region"))
    
    if not tools:
        print("ERROR: No CLI screenshot utility found (neither 'import', 'scrot', nor 'spectacle').", file=sys.stderr)
        sys.exit(1)

    tool_name, chosen_cmd, desc = tools[0]
    print(f"Using tool: {desc}")
    print("Action: Click and drag your mouse over the 'Allow' button to crop it tightly.\n")
    
    try:
        subprocess.run(chosen_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during capture: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCapture cancelled.")
        sys.exit(130)

    if not target_path.exists():
        print(f"ERROR: Expected file {target_path} was not created.", file=sys.stderr)
        sys.exit(1)

    try:
        with Image.open(target_path) as img:
            w, h = img.size
            print(f"Success! Saved image: {target_path.name} ({w}x{h} px)")
            if w > 300 or h > 150:
                print(f"Note: Image size is {w}x{h} px. A tighter crop around the button text is recommended for maximum accuracy.")
            else:
                print("Dimensions look optimal for fast matching.")
    except Exception as e:
        print(f"Saved file, but could not inspect with Pillow: {e}")

if __name__ == "__main__":
    main()
