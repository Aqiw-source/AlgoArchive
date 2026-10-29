#define MyAppName "算法档案"
#define MyAppEnglishName "AlgoArchive"
#define MyAppVersion "2.1.5"
#define MyAppPublisher "Aqiw"
#define MyAppExeName "启动.bat"

[Setup]
AppId={{66E6CC98-742D-4B90-9A18-4A5125AA4F21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/Aqiw-source/AlgoArchive
AppSupportURL=https://github.com/Aqiw-source/AlgoArchive
AppUpdatesURL=https://github.com/Aqiw-source/AlgoArchive/releases/latest
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} Windows x64 安装程序
DefaultDirName={localappdata}\Programs\AlgoArchive
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=AlgoArchive-{#MyAppVersion}-Windows-x64-Setup
SetupIconFile=..\ACM-ICPC-Windows.ico
UninstallDisplayIcon={app}\ACM-ICPC-Windows.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Files]
Source: "..\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\cph_runner.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\启动.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\start.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\创建桌面快捷方式.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\自检.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\self_check.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\使用说明.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\TEST_REPORT.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE-PENDING.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\ACM-ICPC-Windows.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\web\*"; DestDir: "{app}\web"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\scripts\create-desktop-shortcut.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\docs\screenshots\*"; DestDir: "{app}\docs\screenshots"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\ACM-ICPC-Windows.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\ACM-ICPC-Windows.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "启动 {#MyAppName}"; Flags: postinstall nowait skipifsilent

[Code]
var
  DataDirPage: TInputDirWizardPage;

function NormalizeDirectory(Value: String): String;
begin
  Result := RemoveBackslashUnlessRoot(Trim(Value));
end;

function DirectoryContains(ParentDir, ChildDir: String): Boolean;
var
  ParentValue, ChildValue: String;
begin
  ParentValue := AddBackslash(Lowercase(NormalizeDirectory(ParentDir)));
  ChildValue := AddBackslash(Lowercase(NormalizeDirectory(ChildDir)));
  Result := Copy(ChildValue, 1, Length(ParentValue)) = ParentValue;
end;

function JsonEscape(Value: String): String;
begin
  Result := Value;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

function UserConfigPath(): String;
begin
  Result := GetEnv('USERPROFILE') + '\AlgoArchive\config.json';
end;

procedure InitializeWizard;
begin
  DataDirPage := CreateInputDirPage(
    wpSelectDir,
    '数据目录',
    '选择题库与源码的完整数据目录',
    '仅在“仅为我安装”且当前账户尚无用户配置时显示。这里选择的目录会写入当前账户配置，用于保存数据库、代码、头像和业务设置。',
    False,
    ''
  );
  DataDirPage.Add('数据目录：');
  DataDirPage.Values[0] := GetEnv('USERPROFILE') + '\AlgoArchive\data';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result :=
    (DataDirPage <> nil) and
    (PageID = DataDirPage.ID) and
    (IsAdminInstallMode or FileExists(UserConfigPath()));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  AppDir, DataDir, ProbeFile: String;
begin
  Result := True;
  if DataDirPage = nil then
    Exit;
  if CurPageID <> DataDirPage.ID then
    Exit;

  AppDir := NormalizeDirectory(WizardDirValue);
  DataDir := NormalizeDirectory(DataDirPage.Values[0]);
  if DataDir = '' then
  begin
    MsgBox('请选择完整的数据目录。', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  if DirectoryContains(AppDir, DataDir) or DirectoryContains(DataDir, AppDir) then
  begin
    MsgBox('程序目录与数据目录不能相同，也不能互相包含。', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  if not ForceDirectories(DataDir) then
  begin
    MsgBox('无法创建数据目录。请检查路径和当前账户权限。', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  ProbeFile := AddBackslash(DataDir) + '.algoarchive-write-test';
  if not SaveStringToFile(ProbeFile, 'ok', False) then
  begin
    MsgBox('数据目录不可写。请选择当前账户有写入权限的位置。', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  DeleteFile(ProbeFile);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigDir, ConfigPath: String;
  ConfigLines: TArrayOfString;
begin
  if CurStep <> ssPostInstall then
    Exit;
  if IsAdminInstallMode or (DataDirPage = nil) then
    Exit;
  ConfigPath := UserConfigPath();
  if FileExists(ConfigPath) then
    Exit;
  ConfigDir := ExtractFileDir(ConfigPath);
  if not ForceDirectories(ConfigDir) then
    Exit;
  SetArrayLength(ConfigLines, 9);
  ConfigLines[0] := '{';
  ConfigLines[1] := '  "format": 1,';
  ConfigLines[2] := '  "data_dir": "' + JsonEscape(DataDirPage.Values[0]) + '",';
  ConfigLines[3] := '  "browser": {';
  ConfigLines[4] := '    "mode": "default",';
  ConfigLines[5] := '    "custom_path": "",';
  ConfigLines[6] := '    "window_mode": "tab"';
  ConfigLines[7] := '  }';
  ConfigLines[8] := '}';
  SaveStringsToUTF8FileWithoutBOM(ConfigPath, ConfigLines, False);
end;
