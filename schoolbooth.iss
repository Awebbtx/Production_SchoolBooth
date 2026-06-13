[Setup]
; BASIC INFO
AppName=Schoolbooth
AppVersion=3.0.13
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
OutputBaseFilename=SchoolboothSetup-v3.0.13
OutputDir=output
Compression=lzma2
SolidCompression=yes
; Mark as 64-bit installer so it installs into Program Files (not Program Files
; (x86)) and runs the 64-bit Inno helper. Required because schoolbooth.exe is a
; 64-bit PyInstaller bundle.
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; Wipe %TEMP%\_MEI* extraction folders from previous runs/versions before
; installing. A stale or partially-extracted PyInstaller cache is one of the
; common causes of Qt5Core.dll fastfail (0xc0000409) at startup.
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

; VC++ 2015-2022 Redistributable (x64) -- PyQt5 5.15 wheels link against
; this runtime. Without it, Qt5Core.dll fastfails (0xc0000409) on startup.
Source: "redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

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
; VC++ 2015-2022 Redistributable. Runs silently. /norestart prevents reboot.
; Skipped automatically if a same-or-newer redist is already installed (the
; bootstrapper does its own version check and returns exit code 1638).
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; \
    StatusMsg: "Installing Microsoft Visual C++ Runtime (required for Qt)..."; \
    Flags: waituntilterminated; \
    Check: NeedsVCRedist

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

function NeedsVCRedist: Boolean;
var
    InstalledMajor: Cardinal;
    InstalledMinor: Cardinal;
begin
    // Microsoft publishes the installed VC++ 14.x runtime version under this
    // registry key. We require at least 14.30 (VS 2022 baseline). If the key
    // is missing or the version is too old, run the bootstrapper.
    Result := True;
    if RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Major', InstalledMajor) then
    begin
        if InstalledMajor > 14 then
            Result := False
        else if InstalledMajor = 14 then
        begin
            if RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Minor', InstalledMinor) then
            begin
                if InstalledMinor >= 30 then
                    Result := False;
            end;
        end;
    end;
end;

procedure CleanupStaleMEI;
var
    FindRec: TFindRec;
    TempDir: String;
begin
    // PyInstaller onefile extracts to %TEMP%\_MEI<random>. If a previous
    // launch crashed or AV interfered, stale folders linger and can be
    // re-used incorrectly on the next launch, causing Qt5Core to fastfail.
    TempDir := ExpandConstant('{%TEMP}');
    if FindFirst(TempDir + '\_MEI*', FindRec) then
    begin
        try
            repeat
                if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
                    DelTree(TempDir + '\' + FindRec.Name, True, True, True);
            until not FindNext(FindRec);
        finally
            FindClose(FindRec);
        end;
    end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
    if CurStep = ssInstall then
        CleanupStaleMEI;
end;