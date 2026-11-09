<#
.SYNOPSIS
    Interview Agent 桌面版启动器（无窗口 + 系统托盘）。

.DESCRIPTION
    这是 start_app.bat 的 PowerShell 实现，两者的启动步骤完全一致
    （依赖 → 前端构建 → 数据库 → 语音依赖 → 启动独立窗口），区别只有一个：
    **不会再出现终端窗口**。

    为什么必须换掉 bat 来启动（实测结论，不是猜测）：
      Windows 11 默认终端是 Windows Terminal，cmd 因此跑在 ConPTY 伪控制台里。
      子进程（python）调用 GetConsoleWindow() 拿到的是 conhost.exe 名下的
      "PseudoConsoleWindow" —— 对它调用 ShowWindow(SW_HIDE) 会「返回成功、
      IsWindowVisible 也变成 False」，但屏幕上那个真正的终端窗口纹丝不动。
      也就是说：**应用自己藏不掉启动它的那个终端**。

      本脚本改用 Start-Process -WindowStyle Hidden（配合 pythonw.exe）：
      由 CreateProcess 的 STARTUPINFO.wShowWindow 直接告诉系统「不要显示窗口」，
      不依赖子进程自救，因此在 ConPTY / Windows Terminal 下同样有效。

    启动后的形态：
      * 独立窗口（pywebview）
      * 系统托盘图标：单击显示/隐藏窗口，右键菜单可打开日志、退出
      * 任务栏不出现图标（托盘模式下默认隐藏，避免留下点不开的死按钮）

.PARAMETER Foreground
    在当前终端前台运行并等待退出（会显示全部启动日志，用于排查问题）。

.PARAMETER SkipDeps
    跳过 pip 依赖检查/安装（依赖已装好时能明显加快启动）。

.PARAMETER NoBuild
    跳过前端构建检查（dist 已是最新时可用）。

.PARAMETER NoTray
    不注册托盘图标（应用仍无窗口运行，但只能从任务管理器结束）。

.PARAMETER ShowTaskbar
    保留任务栏图标（默认在托盘模式下隐藏）。

.PARAMETER ExtraArgs
    其余参数原样透传给 desktop.py，例如 -ExtraArgs --debug。

.EXAMPLE
    .\start_app.ps1
    托盘方式启动（推荐）。

.EXAMPLE
    .\start_app.ps1 -Foreground
    前台启动，实时看日志。

.NOTES
    日志：logs\start_app.log（启动器本身）、logs\desktop.log（应用）。
    若提示「禁止运行脚本」，可双击 start_app.bat（它转发到本脚本），
    或先执行一次：Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

    ⚠ 本文件必须以 **UTF-8 BOM** 保存：Windows PowerShell 5.1 在没有 BOM 时
      按系统 ANSI 代码页读取 .ps1，中文字符串会被解码成乱码并破坏引号配对，
      脚本直接语法报错。用编辑器改完本文件后请确认 BOM 仍在
      （PowerShell 7 默认按 UTF-8 读取，不受影响）。
#>

[CmdletBinding()]
param(
    [switch]$Foreground,
    [switch]$SkipDeps,
    [switch]$NoBuild,
    [switch]$NoTray,
    [switch]$ShowTaskbar,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir 'start_app.log'

# ── 日志：同时写控制台（前台时可见）与文件（隐藏时必须能查）──
function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = "{0} [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    if ($Foreground) { Write-Host $line }
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

# 外部命令（pip / npm）常把警告写到 stderr。在 $ErrorActionPreference='Stop'
# 下，PowerShell 会把原生命令的 stderr 当成终止性错误直接抛出 —— 表现为
# 「pip 只是打了个黄字警告，启动器却整个中断」。因此调用外部命令时统一
# 局部放宽为 Continue，只按退出码判断成功与否。
function Invoke-Native {
    param([scriptblock]$Command)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Command 2>&1
        return @{ Output = $output; Code = $LASTEXITCODE }
    } finally {
        $ErrorActionPreference = $prev
    }
}

# 启动失败时不能静默退出：隐藏运行时用户看不到任何输出，
# 所以弹一个对话框指出日志位置（WinForms 在 Windows PowerShell 里自带）。
function Show-Failure {
    param([string]$Message)
    Write-Log $Message 'ERROR'
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        [System.Windows.Forms.MessageBox]::Show(
            "$Message`n`n详细日志：`n$logFile`n$logDir\desktop.log",
            'Interview Agent 启动失败',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    } catch {
        # 连对话框都弹不出来（极端情况）时至少让前台运行能看到
        if ($Foreground) { Write-Host $Message -ForegroundColor Red }
    }
    exit 1
}

# 需要长时间等待的步骤（装依赖 / 构建前端）在隐藏模式下先告知用户，
# 否则「双击后半天没反应」会被当成启动失败。
function Show-WaitingNotice {
    param([string]$Message)
    if ($Foreground) { return }
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        [System.Windows.Forms.MessageBox]::Show(
            "$Message`n`n完成后会自动打开窗口，期间不会有其它提示。",
            'Interview Agent 正在准备',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    } catch { }
}

Write-Log '======== Interview Agent 启动 ========'
Write-Log ("参数: Foreground={0} SkipDeps={1} NoBuild={2} NoTray={3} ShowTaskbar={4}" -f `
    $Foreground, $SkipDeps, $NoBuild, $NoTray, $ShowTaskbar)

# ── 1. 解释器：优先 .venv；首次启动时自动创建 ──
$venvDir = Join-Path $root '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$venvPythonW = Join-Path $venvDir 'Scripts\pythonw.exe'
$python = $venvPython
$pythonw = $venvPythonW

# 系统 Python：优先 py 启动器（装了多个版本时它会自己挑最新的 3.x），
# 再退回 PATH 里的 python.exe / python3.exe。统一返回可执行文件路径，
# 调用方不必再关心「要不要带 -3」。
function Find-SystemPython {
    $py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($py) {
        $probe = Invoke-Native { & $py.Source -3 -c "import sys; print(sys.executable)" }
        if ($probe.Code -eq 0) {
            $exe = ($probe.Output | Select-Object -Last 1).ToString().Trim()
            if ($exe -and (Test-Path $exe)) { return $exe }
        }
    }
    foreach ($name in @('python.exe', 'python3.exe')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

if (Test-Path $venvPython) {
    Write-Log '[1/5] 使用虚拟环境 .venv'
} elseif ($SkipDeps) {
    # 用户明确要求跳过依赖：不创建虚拟环境，退回系统 Python（保持旧行为）
    Write-Log '[1/5] 未找到 .venv，按 -SkipDeps 跳过自动创建，改用 PATH 里的 Python' 'WARN'
    $cmd = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if (-not $cmd) { Show-Failure '未找到 Python：既没有 .venv\Scripts\python.exe，PATH 里也没有 python.exe。请先安装 Python 3.11+。' }
    $python = $cmd.Source
    $cmdw = Get-Command 'pythonw.exe' -ErrorAction SilentlyContinue
    $pythonw = if ($cmdw) { $cmdw.Source } else { $python }
} else {
    # 首次启动：自动创建虚拟环境，之后的依赖都装进 .venv，不污染系统 Python
    Write-Log '[1/5] 未找到 .venv，正在自动创建虚拟环境...'
    Show-WaitingNotice "首次启动需要创建 Python 虚拟环境并安装依赖，可能需要几分钟。`n`n完成后会自动打开窗口。"
    $sysPython = Find-SystemPython
    if (-not $sysPython) {
        Show-Failure '未找到 Python：py 启动器与 PATH 里的 python.exe 都不可用。请先安装 Python 3.11+（安装时勾选 "Add python.exe to PATH"）。'
    }

    $ver = Invoke-Native { & $sysPython -c "import sys; print('%d.%d' % sys.version_info[:2])" }
    if ($ver.Code -ne 0) {
        Write-Log ($ver.Output | Out-String) 'PY'
        Show-Failure "无法运行 Python：$sysPython"
    }
    $verText = ($ver.Output | Out-String).Trim()
    if ([version]$verText -lt [version]'3.11') {
        Show-Failure "Python 版本过低（$verText）：本项目需要 Python 3.11+（CI 使用 3.11 / 3.12）。请安装新版后重试。"
    }

    Write-Log "      使用系统 Python $verText：$sysPython"
    $make = Invoke-Native { & $sysPython -m venv $venvDir }
    if ($make.Code -ne 0 -or -not (Test-Path $venvPython)) {
        Write-Log ($make.Output | Out-String) 'VENV'
        Show-Failure "创建虚拟环境失败：$venvDir`n`n提示：Debian/Ubuntu 需要先执行 sudo apt install python3-venv；Windows 请确认安装的是 python.org 官方版本（不是 Microsoft Store 版）。"
    }
    Write-Log "      虚拟环境已创建：$venvDir"

    # pip 自更新失败不阻断启动：自带 pip 一样能装 requirements
    $pipSelf = Invoke-Native { & $venvPython -m pip install --upgrade pip -q }
    if ($pipSelf.Code -ne 0) {
        Write-Log '      pip 自更新失败，继续使用虚拟环境自带的 pip' 'WARN'
    } else {
        Write-Log '      pip 已就绪'
    }
}

# ── 2. .env ──
if (-not (Test-Path (Join-Path $root '.env'))) {
    if (Test-Path (Join-Path $root '.env.example')) {
        Copy-Item (Join-Path $root '.env.example') (Join-Path $root '.env')
        Write-Log '[提示] 未找到 .env，已从 .env.example 复制；请填入 DEEPSEEK_API_KEY 与 JWT_SECRET' 'WARN'
    }
}

# ── 3. Python 依赖（全部装进 .venv） ──
if ($SkipDeps) {
    Write-Log '[2/5] 跳过依赖检查（-SkipDeps）'
} else {
    Write-Log '[2/5] 检查 Python 依赖...'
    $req = Join-Path $root 'requirements.txt'
    # 标记文件放在 .venv 内部：虚拟环境一重建，标记自动失效，
    # 不会出现「新 venv 里什么都没装却被判定为依赖已就绪」。
    $depsMarker = Join-Path $venvDir '.deps_installed'
    $needInstall = $true
    if ((Test-Path $depsMarker) -and (Test-Path $req)) {
        $needInstall = (Get-Item $req).LastWriteTimeUtc -gt (Get-Item $depsMarker).LastWriteTimeUtc
    }

    if ($needInstall) {
        Write-Log '      安装依赖到虚拟环境（首次较慢）...'
        $pip = Invoke-Native { & $python -m pip install -r $req -q }
        if ($pip.Code -ne 0) {
            if ($pip.Output) { Write-Log ($pip.Output | Out-String) 'PIP' }
            Show-Failure 'Python 依赖安装失败，请检查网络或改用国内镜像：pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple'
        }
        # 空文件当标记，mtime 即「依赖装好」的时间；不写版本号，避免无意义改动。
        # 用 WriteAllText 而不是 New-Item -Force：后者对已存在的文件不会刷新 mtime。
        [IO.File]::WriteAllText($depsMarker, '')
        Write-Log '      Python 依赖已就绪'
    } else {
        Write-Log '      Python 依赖已就绪（requirements.txt 未变化，跳过安装）'
    }
}

# ── 4. 前端构建产物 ──
if ($NoBuild) {
    Write-Log '[3/5] 跳过前端构建检查（-NoBuild）'
} else {
    $distIndex = Join-Path $root 'frontend\dist\index.html'
    $needBuild = -not (Test-Path $distIndex)

    if (-not $needBuild) {
        # 复用已有的陈旧检测脚本：源码比产物新就需要重建
        $stale = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\frontend_stale.ps1') 2>$null
        if ($stale -match 'newer') { $needBuild = $true }
    }

    if ($needBuild) {
        Write-Log '[3/5] 前端源码有更新或产物缺失，开始构建...'
        Show-WaitingNotice "检测到前端需要重新构建，首次可能需要几分钟。`n`n可先用 -NoBuild 参数跳过。"
        if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
            Write-Log '      安装前端依赖（首次较慢）...'
            Push-Location (Join-Path $root 'frontend')
            try {
                $npmInstall = Invoke-Native { & npm install --silent }
                if ($npmInstall.Code -ne 0) {
                    Write-Log ($npmInstall.Output | Out-String) 'NPM'
                    Show-Failure '前端依赖安装失败（npm install）。'
                }
            } finally { Pop-Location }
        }
        Push-Location (Join-Path $root 'frontend')
        try {
            $build = Invoke-Native { & npm run build }
            if ($build.Code -ne 0) {
                Write-Log ($build.Output | Out-String) 'NPM'
                Show-Failure '前端构建失败（npm run build）。'
            }
        } finally { Pop-Location }
        Write-Log '      前端构建完成'
    } else {
        Write-Log '[3/5] 前端构建产物已就绪'
    }
}

# ── 5. 数据库 ──
Write-Log '[4/5] 初始化数据库...'
$db = Invoke-Native { & $python -c "import asyncio; from database import init_db; asyncio.run(init_db()); print('ok')" }
if ($db.Code -ne 0) {
    # 与 bat 一致：不阻断启动，应用会在首次请求时自动建表
    Write-Log "[警告] 数据库初始化失败，应用将在首次请求时尝试自动建表`n$($db.Output)" 'WARN'
} else {
    Write-Log '      数据库就绪'
}

# ── 6. 语音依赖（仅在 .env 打开开关时）──
function Get-EnvSwitch {
    param([string]$Name)
    $path = Join-Path $root '.env'
    if (-not (Test-Path $path)) { return $false }
    $line = Select-String -Path $path -Pattern "^$Name=" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $line) { return $false }
    return ($line.Line -match 'true')
}

$voiceOn = (Get-EnvSwitch 'VOICE_ENABLED') -or (Get-EnvSwitch 'STT_ENABLED') -or (Get-EnvSwitch 'TTS_ENABLED')
if ($voiceOn) {
    Write-Log '      语音已启用，检查语音依赖...'
    $sttLine = Select-String -Path (Join-Path $root '.env') -Pattern '^STT_DEVICE=' -ErrorAction SilentlyContinue | Select-Object -First 1
    $sttPkgs = @('faster-whisper')
    if ($sttLine -and ($sttLine.Line -match 'cuda')) { $sttPkgs += 'ctranslate2' }
    $allPkgs = $sttPkgs + @('silero-vad', 'numpy', 'ffmpeg-python', 'piper-tts', 'huggingface_hub', 'zhconv')
    $voice = Invoke-Native { & $python -m pip install @allPkgs -q }
    if ($voice.Code -ne 0) {
        Write-Log "[警告] 语音依赖安装失败，语音功能可能不可用`n$($voice.Output)" 'WARN'
    } else {
        Write-Log '      语音依赖已就绪'
    }
} else {
    Write-Log '      语音未启用（.env 三个开关均为 false），跳过'
}

# ── 7. 启动 ──
$pyArgs = @('desktop.py')
if (-not $NoTray) { $pyArgs += '--tray' }
if ($ShowTaskbar) { $pyArgs += '--hide-taskbar', 'false' }
if ($ExtraArgs) { $pyArgs += $ExtraArgs }

if ($Foreground) {
    Write-Log "[5/5] 前台启动: $python $($pyArgs -join ' ')"
    & $python @pyArgs
    $code = $LASTEXITCODE
    Write-Log "应用已退出（退出码 $code）"
    exit $code
}

Write-Log "[5/5] 后台启动: $pythonw $($pyArgs -join ' ')"
# -WindowStyle Hidden 是关键：通过 STARTUPINFO.wShowWindow 让系统不显示窗口，
# 配合 pythonw.exe（GUI 子系统，不分配控制台）彻底没有黑窗。
#
# 必须重定向 stdout/stderr（实测教训）：不重定向时子进程会**继承启动器的标准句柄**，
# 而启动器进程随即退出 —— 句柄失效后子进程在第一次写 stdout 时直接死掉，
# 表现为「日志停在加载 faiss，之后什么都没有」（pythonw 下连 traceback 都看不到）。
# 重定向到 logs\app-stdout.log 还有一个好处：pythonw 没有控制台，
# 未捕获异常的 traceback 只能靠这里留痕。
$appOut = Join-Path $logDir 'app-stdout.log'
$appErr = Join-Path $logDir 'app-stderr.log'
Start-Process -FilePath $pythonw -ArgumentList $pyArgs `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput $appOut -RedirectStandardError $appErr

Write-Log '启动完成：托盘图标见右下角；单击图标显示/隐藏窗口，右键可退出'
Write-Log '本启动器已退出，应用在后台继续运行'
