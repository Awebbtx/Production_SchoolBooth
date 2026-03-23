# Publishing

This folder is the clean app-only repo root to publish.

## Target Repository

- `https://github.com/Awebbtx/Production_SchoolBooth.git`

## Local Publish Commands

Run these commands from this folder after Git is available in your shell:

```powershell
git init
git branch -M main
git remote add origin https://github.com/Awebbtx/Production_SchoolBooth.git
git add .
git status
git commit -m "Initial production app-only import"
git push -u origin main
```

## Pre-Push Checks

- Confirm `output/` is absent
- Confirm `.venv/` is absent
- Confirm `camera_settings.json` still contains only safe defaults
- Confirm `overlay_frame_settings.json` contains only production-safe frame metadata
- Confirm `watermarks/FRAME_1.png` through `FRAME_4.png` are present

## Build Checks

If you want to validate the release artifacts before pushing:

```powershell
pip install -r requirements.txt
pyinstaller schoolbooth.spec
```

Then build the installer with Inno Setup using `schoolbooth.iss`.