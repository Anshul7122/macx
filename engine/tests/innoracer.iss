; A real Inno Setup "repack": LZMA2-compressed, solid, split into setup-N.bin parts like repacks and GOG installers.
[Setup]
AppName=Inno Racer
AppVersion=1.0
AppPublisher=MacX test
DefaultDirName=C:\Games\Inno Racer
DefaultGroupName=Inno Racer
DisableProgramGroupPage=yes
OutputDir=W:\Inno Racer Repack
OutputBaseFilename=setup
Compression=lzma2/ultra64
SolidCompression=yes
DiskSpanning=yes
DiskSliceSize=30000000
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Files]
Source: "W:\.build\src\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Inno Racer"; Filename: "{app}\InnoRacer.exe"
Name: "{autodesktop}\Inno Racer"; Filename: "{app}\InnoRacer.exe"
