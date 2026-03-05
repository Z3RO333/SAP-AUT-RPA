#define MyAppName "Robos SAP"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Robos SAP"
#define MyAppExeName "RobosSAP.exe"

[Setup]
AppId={{B4D6AE2B-4E8F-4F3C-A2AF-4B5F35B5AE6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Robos SAP
DefaultGroupName=Robos SAP
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=RobosSAP-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern

[Files]
Source: "..\dist\RobosSAP\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Robos SAP"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Robos SAP"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Robos SAP"; Flags: nowait postinstall skipifsilent
