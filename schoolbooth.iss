[Setup]
; BASIC INFO
AppName=Schoolbooth
AppVersion=3.0.11
AppPublisher=I Know A Pro, LLC
AppPublisherURL=https://www.iknowapro.net
AppSupportURL=mailto:service@iknowapro.net
AppUpdatesURL=https://www.iknowapro.net/updates
AppCopyright=Copyright © 2024 I Know A Pro, LLC - Special use for PTA

; IDENTIFIERS
AppId={{f2e2bcd6-8f31-414b-9ce1-6f574eeca6fd}}
UninstallDisplayName=Schoolbooth
UninstallDisplayIcon={app}\schoolbooth.exe

; INSTALLER SETTINGS
DefaultDirName={autopf}\Schoolbooth
DefaultGroupName=Schoolbooth
OutputBaseFilename=SchoolboothSetup-v3.0.11
OutputDir=output
Compression=lzma2
SolidCompression=yes

; If the running schoolbooth.exe still has the EXE locked when Inno starts
; copying files, force-close it instead of failing. RestartApplications
; tells Inno to relaunch it after the install completes (the [Run] section
; already offers a "Launch SchoolBooth" postinstall option, so this is a
; belt-and-suspenders safety net for the auto-updater path).
CloseApplications=force
RestartApplications=no

[Files]
; MAIN APP FILES
Source: "dist\schoolbooth.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "overlays.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "app.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE.TXT"; DestDir: "{app}"; Flags: ignoreversion
Source: "watermarks\*"; DestDir: "{app}\watermarks"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; PRINTER DRIVERS (with recursive copy)
Source: "dist\starprnt_v3.8.1\*"; DestDir: "{app}\PrinterDrivers\StarPRNT"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\SchoolBooth"; Filename: "{app}\schoolbooth.exe"
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SchoolBooth"; Filename: "{app}\schoolbooth.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional icons:"
Name: "installprinter"; Description: "Install StarPRNT printer drivers"; GroupDescription: "Optional components:"; Flags: unchecked

[Run]
; MAIN APP (no admin needed)
Filename: "{app}\schoolbooth.exe"; Description: "Launch SchoolBooth"; Flags: postinstall nowait

; PRINTER INSTALLER (with admin elevation)
Filename: "{app}\PrinterDrivers\StarPRNT\setup\setup.exe"; \
    Description: "Install StarPRNT drivers"; \
    Flags: postinstall nowait skipifsilent runascurrentuser; \
    Tasks: installprinter; \
        StatusMsg: "Installing printer drivers (admin rights required)..."; \
        Check: HasStarDriverSetup

[Code]
function HasStarDriverSetup: Boolean;
begin
    Result := FileExists(ExpandConstant('{app}\PrinterDrivers\StarPRNT\setup\setup.exe'));
end;