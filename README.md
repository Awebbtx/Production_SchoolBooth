# Schoolbooth Windows App

Schoolbooth is the Windows desktop capture app used for school and PTA photo events.

This app-only package is intended for production publishing without the WordPress plugin, local runtime data, or environment-specific secrets.

## Included In Production

- Desktop application source
- Windows build inputs
- Installer script
- Sample overlay frames `FRAME_1.png` through `FRAME_4.png`
- Default sanitized configuration files

## Excluded From Production

- WordPress plugin code
- Local virtual environments
- Output folders and debug logs
- Access-code runtime data
- Real WordPress URLs, shared secrets, usernames, and machine-specific paths

## Runtime Dependencies

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Run Locally

```bash
python schoolbooth.py
```

## Build

PyInstaller input:

- `schoolbooth.spec`

Windows installer input:

- `schoolbooth.iss`

## Configuration Notes

- `config.json` is checked in with safe defaults only.
- Configure printers, WordPress integration, and device-specific values after deployment.
- `overlay_frame_settings.json` contains only production-safe sample overlay metadata.

## Release Checklist

- See `PRODUCTION_CHECKLIST.md` for the current app-only cleanup status.
- See `PUBLISHING.md` for the GitHub handoff commands.
- Verify `config.json` contains no live credentials
- Verify `overlay_frame_settings.json` contains no absolute local paths
- Verify `output/` and `.venv/` are not included in release commits
- Verify sample overlay files remain in `watermarks/`
- Run syntax and packaging checks before publishing