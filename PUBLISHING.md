# Publishing

This folder is the clean app-only repo root to publish.

## Target Repository

- `https://github.com/Awebbtx/Production_SchoolBooth.git`
- Current tagged version: `v3.0.1`

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
- Confirm `config.json` still contains only safe defaults
- Confirm `overlays.json` contains only production-safe frame metadata
- Confirm `watermarks/FRAME_1.png` through `FRAME_4.png` are present

## Build Checks

If you want to validate the release artifacts before pushing:

```powershell
pip install -r requirements.txt
pyinstaller schoolbooth.spec
```

Then build the installer with Inno Setup using `schoolbooth.iss`.

## Build Installer From Git (PowerShell)

For developer/operator machines, you can clone and build in one flow:

```powershell
git clone https://github.com/Awebbtx/Production_SchoolBooth.git
cd Production_SchoolBooth
powershell -ExecutionPolicy Bypass -File .\build-installer.ps1
```

Notes:

- This method is for building the app and installer from source.
- End users should install from the released installer artifact, not from Git source.
- Optional flags:
	- `-NoVenv` uses system Python (`py -3`) instead of creating `.venv`
	- `-NoInno` builds the executable only and skips installer packaging

## Quick Monitoring

Use these commands from this folder to monitor repo health and release state:

```powershell
git fetch origin --tags
git status --short --branch
git log --oneline --decorate -n 5
git tag --list
```