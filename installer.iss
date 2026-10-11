; installer.iss — builds JARVIS-Setup-<version>.exe with Inno Setup 6 (free:
; https://jrsoftware.org/isdl.php). Don't run this directly: double-click
; build_installer.bat, which builds Jarvis.exe first and passes the version.
;
; Installs to %LOCALAPPDATA%\Programs\JARVIS (no admin needed, and JARVIS can
; write its memory/settings next to itself). Your keys, settings and memory are
; NEVER put in the installer, and never overwritten or deleted by it.

#ifndef AppVer
  #define AppVer "2.0.0"
#endif

[Setup]
AppId={{8E3C6B1A-4F2D-4C77-9A51-JARVIS000001}
AppName=JARVIS
AppVersion={#AppVer}
AppPublisher=JARVIS
DefaultDirName={localappdata}\Programs\JARVIS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=JARVIS-Setup-{#AppVer}
SetupIconFile=config\jarvis.ico
UninstallDisplayIcon={app}\Jarvis.exe
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; Everything from the build EXCEPT secrets and personal data:
Source: "dist\Jarvis\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; \
  Excludes: "\config\*.json,\config\*.locked,\config\*.tmp,\config\certs\*,\config\whatsapp_web\*,\memory\*.json,\memory\chat_history\*,\memory\journal\*,\backups\*,__pycache__"

[Icons]
Name: "{autoprograms}\JARVIS"; Filename: "{app}\Jarvis.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\JARVIS"; Filename: "{app}\Jarvis.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Jarvis.exe"; Description: "Start JARVIS"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

; Uninstall removes the program but keeps config\ and memory\ (your data).
[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
