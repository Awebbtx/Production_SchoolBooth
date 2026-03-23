# Production Checklist

## Completed

- Isolated the Windows app into this clean repo folder
- Excluded the WordPress plugin from the production file set
- Sanitized `config.json` to remove live URLs, secrets, usernames, printer names, and machine-specific values
- Sanitized `overlays.json` to remove custom absolute local paths
- Kept sample overlay frames `FRAME_1.png` through `FRAME_4.png`
- Hardened packaging inputs in `schoolbooth.spec` and `schoolbooth.iss`
- Removed local generated icon fallback artifacts from the production scope
- Added app-only documentation and repo ignore rules
- Verified Python syntax for `schoolbooth.py` and `settings_manager.py`

## Verified In Clean Tree

- No live WordPress secrets or usernames are present in shipped defaults
- No app-specific absolute local content paths remain in shipped JSON configuration
- Only the app source, packaging files, images, licenses, and sample frames are included

## Remaining Before Publish

- Initialize or connect this folder to the GitHub repo `Production_SchoolBooth`
- Install dependencies from `requirements.txt` in the target environment
- Run a full app launch test on the release machine
- Build the PyInstaller package and test the generated executable
- Build the Inno Setup installer and test installation on a clean Windows machine

## Publish Scope

- Commit from this folder, not from the mixed workspace root
- Do not add `output/`, `.venv/`, `access_codes.json`, or local backup config files