; Instalador de SyncWatch (Inno Setup 6)
; Lo compila automáticamente construir_exe.bat si Inno Setup está instalado.
; Requiere haber generado antes dist\SyncWatch.exe con PyInstaller.

#define AppName "SyncWatch"
#define AppVersion "1.0.0"
#define AppPublisher "Robinson Meza"
#define AppExe "SyncWatch.exe"

[Setup]
AppId={{8C3F6A2E-5B1D-4E7A-9C2F-1A2B3C4D5E6F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments=Monitor de recursos + Laboratorio de sincronización (Sistemas Operativos)
; Instalación por usuario: no pide permisos de administrador
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=SyncWatch_Instalador_{#AppVersion}
SetupIconFile=assets\syncwatch.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Dirs]
; Carpeta de datos (CSV y bitácora). No se borra al desinstalar para conservar las evidencias.
Name: "{userdocs}\SyncWatch\registros"; Flags: uninsneveruninstall

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Carpeta de registros"; Filename: "{userdocs}\SyncWatch\registros"
Name: "{group}\Léame"; Filename: "{app}\README.md"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName} ahora"; Flags: nowait postinstall skipifsilent
