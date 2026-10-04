; Windows installer of Audiotext, built with Inno Setup 6.5 or later
; (https://jrsoftware.org/isinfo.php).
;
; It installs the app built by PyInstaller. If the GPU add-on is defined, the user can
; choose GPU acceleration, which downloads the add-on from the GitHub release and
; extracts it over the CPU build (see `.github/scripts/make_gpu_addon.py`).
;
; To create the installer locally, build the app and compile this script:
;
;   pyinstaller audiotext.spec --noconfirm
;   iscc packaging\windows.iss
;
; The installer is created in `dist\`. These defines (/D<name>=<value>) change the
; defaults, which is what the Release workflow does:
;
;   AppVersion  The version of the app (default: the one in `pyproject.toml`)
;   BundleDir   The app built by PyInstaller (default: `dist\Audiotext`)
;   OutputDir   Where the installer is created (default: `dist`)
;   GpuAddon    The Inno Setup file of the GPU add-on (default: none, so the
;               installer doesn't offer GPU acceleration)

#if VER < EncodeVer(6, 5, 0)
  #error Inno Setup 6.5 or later is required
#endif

#define RootDir AddBackslash(SourcePath) + ".."

#ifndef AppVersion
  ; `pyproject.toml` is close enough to an INI file to read the version this way
  #define AppVersion StringChange(ReadIni(RootDir + "\pyproject.toml", "project", "version"), '"', "")
#endif
#if AppVersion == ""
  #error The version of the app wasn't found in pyproject.toml
#endif
#ifndef BundleDir
  #define BundleDir RootDir + "\dist\Audiotext"
#endif
#ifndef OutputDir
  #define OutputDir RootDir + "\dist"
#endif

#define AppName "Audiotext"
#define AppExeName "Audiotext.exe"
#define AppUrl "https://github.com/HenestrosaDev/audiotext"

[Setup]
AppId={{C93FC20E-55E4-402B-A7C4-05EDB0F44136}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=HenestrosaDev
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
; Installs for the current user without administrator rights, unless the user chooses
; to install for all users
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile={#RootDir}\LICENSE
SetupIconFile={#RootDir}\res\windows\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir={#OutputDir}
OutputBaseFilename={#AppName}-{#AppVersion}-windows-x64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
; The GPU add-on has large files, which need less memory with this method
ArchiveExtraction=enhanced/nopassword

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "catalan"; MessagesFile: "compiler:Languages\Catalan.isl"
; Inno Setup 6 only has it among the unofficial translations (from is-6_7_3)
Name: "chinesesimplified"; MessagesFile: "{#RootDir}\packaging\languages\ChineseSimplified.isl"
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "swedish"; MessagesFile: "compiler:Languages\Swedish.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[CustomMessages]
GpuGroup=Transcription with WhisperX:
GpuTask=Use the NVIDIA GPU (CUDA) to transcribe faster (downloads %1)
spanish.GpuGroup=Transcripción con WhisperX:
spanish.GpuTask=Usar la GPU de NVIDIA (CUDA) para transcribir más rápido (descarga %1)

[InstallDelete]
; Installs a clean copy of the app, so no files of a previous version or of the GPU
; add-on remain (e.g. when reinstalling without GPU acceleration)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; The CPU build, which goes first so the GPU add-on is extracted over it
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#ifdef GpuAddon
; The archives of the GPU add-on, downloaded before installing ([Files]), and the
; procedure that adds them to the download page ([Code])
#include GpuAddon
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
#ifdef GpuAddon
Name: "gpu"; Description: "{cm:GpuTask,{#GpuDownloadSize}}"; GroupDescription: "{cm:GpuGroup}"
#endif

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

#ifdef GpuAddon
[Code]
var
  DownloadPage: TDownloadWizardPage;
  GpuTaskInitialized: Boolean;

function HasNvidiaGpu: Boolean;
begin
  // Installed by the NVIDIA driver, which CUDA needs
  Result := FileExists(ExpandConstant('{sys}\nvcuda.dll'));
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  // GPU acceleration is selected by default only if there's an NVIDIA GPU
  if (CurPageID = wpSelectTasks) and not GpuTaskInitialized then begin
    GpuTaskInitialized := True;
    if not HasNvidiaGpu then
      WizardSelectTasks('!gpu');
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID <> wpReady) or not WizardIsTaskSelected('gpu') then
    Exit;

  DownloadPage.Clear;
  AddGpuDownloads(DownloadPage);
  DownloadPage.Show;
  try
    try
      // Downloads the archives to {tmp} and checks their SHA-256
      DownloadPage.Download;
    except
      if not DownloadPage.AbortedByUser then
        SuppressibleMsgBox(AddPeriod(Format('%s: %s', [DownloadPage.LastBaseNameOrUrl, GetExceptionMessage])), mbCriticalError, MB_OK, IDOK);
      Result := False;
    end;
  finally
    DownloadPage.Hide;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  RemoveListPath: String;
  RemoveList: TArrayOfString;
  RelativePath: String;
  I: Integer;
begin
  if (CurStep <> ssPostInstall) or not WizardIsTaskSelected('gpu') then
    Exit;

  // Deletes the files of the CPU build that aren't in the GPU build
  RemoveListPath := ExpandConstant('{app}\gpu-addon-remove.txt');
  if LoadStringsFromFile(RemoveListPath, RemoveList) then begin
    for I := 0 to GetArrayLength(RemoveList) - 1 do begin
      RelativePath := RemoveList[I];
      StringChange(RelativePath, '/', '\');
      if RelativePath <> '' then
        DeleteFile(ExpandConstant('{app}\') + RelativePath);
    end;
    DeleteFile(RemoveListPath);
  end;
end;
#endif
