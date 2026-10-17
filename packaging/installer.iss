; ============================================
; Interview Agent — Windows 安装包脚本（Inno Setup 6）
; ============================================
; 构建：iscc /DAppVersion=1.0.0 packaging\installer.iss
; 产物：dist\client\InterviewAgentSetup-<版本>.exe
;
; 设计取舍：
;   * PrivilegesRequired=lowest + 安装到 {localappdata}\Programs：
;     免 UAC 弹窗，双击即装，适合个人电脑。需要多用户共享部署时
;     可改为 PrivilegesRequired=admin + DefaultDirName={autopf}。
;   * client.env 复制为安装目录的 .env：用户编辑这一份即可改配置，
;     优先级高于打包内置的默认 .env（见 config.py 冻结分支）。
;   * 数据（SQLite / 日志 / 截图 / 模型缓存）不放在安装目录，
;     而是 %LOCALAPPDATA%\InterviewAgent（见 app_paths.py），
;     卸载不丢数据、重装不丢数据。

#define AppName "Interview Agent"
#define AppNameCN "面试Agent"
#define AppExeName "InterviewAgent.exe"
; 版本号由构建脚本通过 /DAppVersion=x.y.z 传入；未传时回退 1.0.0
#ifndef AppVersion
  #define AppVersion 1.0.0
#endif
#define AppPublisher "Interview Agent"
#define AppURL "https://github.com/L-yu03/interview-agent"

[Setup]
; 固定 AppId：升级安装时能正确识别为同一应用（换 GUID = 全新安装）
AppId={{7E5A3B28-3C4E-4F2A-9E1D-8B6F0A2C4D51}
AppName={#AppName}（{#AppNameCN}）
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; 免管理员权限：装到用户目录，无 UAC 弹窗
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist\client
OutputBaseFilename=InterviewAgentSetup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}（{#AppNameCN}）
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"
; 英文系统回退（Inno 6 内置语言列表里简体中文名为 chinesesimplified）

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Files]
; PyInstaller onedir 产物整体复制（含 _internal/）
Source: "..\dist\client\InterviewAgent\*"; DestDir: "{app}"; \
    Excludes: "*.pyc,__pycache__\*,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs
; 默认配置复制为安装目录的 .env（用户实际编辑的那份）
Source: "client.env"; DestDir: "{app}"; DestName: ".env"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
    WorkingDir: "{app}"; Comment: "AI 模拟面试助手"
Name: "{autodesktop}\{#AppNameCN}"; Filename: "{app}\{#AppExeName}"; \
    WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; 安装完成后可选立即启动（默认勾选）
Filename: "{app}\{#AppExeName}"; Description: "立即运行 {cm:LaunchProgram,{#AppNameCN}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时清理用户数据目录之外的残留（用户数据按设计保留，见 app_paths.py）
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\screenshots"

[Code]
// 安装前提示：语音与 RAG 功能未包含在打包版中
function InitializeSetup(): Boolean;
begin
  Result := True;
  // 静默安装（CI / 脚本场景）不弹窗
  if not WizardSilent then
    MsgBox('欢迎安装 ' + '{#AppNameCN}' + '。' + #13#13 +
           '注意：语音识别/合成（STT/TTS）与 RAG 知识库依赖未包含在本安装包中，' + #13 +
           '这些功能默认关闭，不影响模拟面试、截图答题等核心功能。' + #13 +
           '完整功能请使用源码方式运行。', mbInformation, MB_OK);
end;
