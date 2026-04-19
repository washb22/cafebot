; CafeBot Inno Setup Installer Script
[Setup]
AppName=CafeBot
AppVersion=1.1
AppPublisher=CafeBot
DefaultDirName={autopf}\CafeBot
DefaultGroupName=CafeBot
OutputDir=..\installer_output
OutputBaseFilename=CafeBot_Setup_v1.1
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\CafeBot.exe
PrivilegesRequired=lowest
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면 바로가기 생성"; GroupDescription: "추가 옵션:"

[Files]
; PyInstaller 빌드 결과물 전체
Source: "..\dist\CafeBot\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

; data 폴더 (첫 설치 시만, 기존 설정 보존)
Source: "..\dist\CafeBot\data\accounts.json"; DestDir: "{app}\data"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\CafeBot"; Filename: "{app}\CafeBot.exe"
Name: "{autodesktop}\CafeBot"; Filename: "{app}\CafeBot.exe"; Tasks: desktopicon
Name: "{group}\CafeBot 삭제"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\CafeBot.exe"; Description: "CafeBot 실행"; Flags: nowait postinstall skipifsilent
