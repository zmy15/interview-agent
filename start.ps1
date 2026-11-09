<#
.SYNOPSIS
    Interview Agent 网页版启动器（start.bat 的 PowerShell 实现）。

.DESCRIPTION
    步骤与原来的 start.bat 完全一致：检查 Node / Python → 首次启动自动创建 .venv
    → 安装依赖 → 初始化数据库 →（可选）配置语音 → 启动后端 / 语音 / 前端窗口
    → 打开浏览器。

    为什么换成 PowerShell：
      * .bat 在 chcp 65001 下对中文很不友好：非 ASCII 文本放进 if ( ) / for ( )
        块里会被 cmd 的解析器读坏，只能靠 goto 绕开，逻辑越写越绕；
      * 块里的 %errorlevel% 在解析阶段就展开，读到的是进块前的旧值；
      * 端口检查要拼 netstat + findstr，而 PowerShell 有 Get-NetTCPConnection、
        Start-Process -WorkingDirectory，参数还能按数组传，不必和引号缠斗。

    双击 start.bat 仍可正常使用：它只负责用 PowerShell 调起本文件。

.PARAMETER SkipDeps
    跳过「创建虚拟环境 + 安装 Python 依赖」。虚拟环境不存在时退回系统 Python
    （仅适用于已经手动装好依赖的场景）。

.NOTES
    需要 Windows PowerShell 5.1+（系统自带）或 PowerShell 7。
    本文件必须以 **UTF-8 BOM** 保存：Windows PowerShell 5.1 在没有 BOM 时按系统
    ANSI 代码页读取 .ps1，中文字符串会被解码成乱码并破坏引号配对。
#>

[CmdletBinding()]
param(
    [switch]$SkipDeps
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

# ─────────────────────────────────────────────────────────────────────────────
#  小工具
# ─────────────────────────────────────────────────────────────────────────────

# 失败时不能直接退出：双击运行时窗口会瞬间消失，用户什么也看不到。
function Fail([string]$Message) {
    Write-Host ''
    Write-Host "[错误] $Message" -ForegroundColor Red
    [void](Read-Host '按回车键退出')
    exit 1
}

# 外部命令（pip / npm / python / netstat）常把警告或 traceback 写到 stderr。
# Windows PowerShell 5.1 在 $ErrorActionPreference='Stop' 下会把「重定向过的
# stderr」当成终止性错误抛出 —— 实测表现为「数据库初始化只是打了个 traceback，
# 整个启动器却直接退出」。因此外部命令统一走这里：期间局部放宽为 Continue，
# 成败只看退出码，需要时再把输出打出来。
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

# 端口预检查。为什么要先查：
#   服务用 Start-Process 起在独立窗口里，端口被占时 uvicorn 会立刻退出，那个
#   窗口一闪而过，用户只会发现「少了一个窗口」，完全不知道原因（旧脚本踩过）。
function Test-PortFree([int]$Port, [string]$Name) {
    $owners = @()
    $queryOk = $false

    if (Get-Command 'Get-NetTCPConnection' -ErrorAction SilentlyContinue) {
        try {
            $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                Select-Object -ExpandProperty OwningProcess -Unique)
            $queryOk = $true
        } catch {
            $queryOk = $false
        }
    }

    if (-not $queryOk) {
        # 很老的系统没有 Get-NetTCPConnection，退回 netstat 解析
        $pattern = ":$Port\s+\S+\s+LISTENING\s+(\d+)"
        $netstat = Invoke-Native { & netstat -ano -p TCP }
        foreach ($line in @($netstat.Output)) {
            if ("$line" -match $pattern) { $owners += $Matches[1] }
        }
        $owners = @($owners | Select-Object -Unique)
    }

    if ($owners.Count -eq 0) { return $true }

    $ownerPid = $owners[0]
    Write-Host ''
    Write-Host "[警告] 端口 $Port 已被占用，无法启动 $Name（占用进程 PID=$ownerPid）" -ForegroundColor Yellow
    Write-Host "       查看: Get-Process -Id $ownerPid | Format-List *"
    Write-Host "       结束: Stop-Process -Id $ownerPid -Force"
    Write-Host '       本次会跳过该服务；释放端口后重新运行即可。' -ForegroundColor Yellow
    return $false
}

# 后端就绪探测：只用来提示「启动较慢」，失败不阻断启动。
function Test-Backend {
    try {
        $resp = Invoke-WebRequest -Uri 'http://localhost:8000/' -UseBasicParsing -TimeoutSec 2
        return ($resp.StatusCode -ge 200)
    } catch {
        return $false
    }
}

# 系统 Python：优先 py 启动器（多版本时它自己挑最新的 3.x），
# 再退回 PATH 里的 python.exe / python3.exe。统一返回可执行文件路径。
function Find-SystemPython {
    $py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($py) {
        $probe = Invoke-Native { & $py.Source -3 -c "import sys; print(sys.executable)" }
        if ($probe.Code -eq 0) {
            $exe = @($probe.Output) | ForEach-Object { "$_".Trim() } |
                Where-Object { $_ -like '*python.exe' } | Select-Object -Last 1
            if ($exe -and (Test-Path $exe)) { return $exe }
        }
    }
    foreach ($name in @('python.exe', 'python3.exe')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

# Python 版本号（形如 3.13）：找不到可用输出时返回 $null。
function Get-PythonVersionText([string]$PythonExe) {
    $r = Invoke-Native { & $PythonExe -c "import sys; print('%d.%d' % sys.version_info[:2])" }
    if ($r.Code -ne 0) { return $null }
    return (@($r.Output) | ForEach-Object { "$_".Trim() } |
        Where-Object { $_ -match '^\d+\.\d+$' } | Select-Object -Last 1)
}

# 把依赖清单的「安装时间标记」与 requirements.txt 的 mtime 对比。
# 标记放在 .venv 内部，虚拟环境一重建标记自然失效，不会出现
# 「新 venv 里什么都没装却被判定为依赖已就绪」。
function Test-DepsReady([string]$VenvDir, [string]$RequirementsPath) {
    $marker = Join-Path $VenvDir '.deps_installed'
    if (-not (Test-Path $marker)) { return $false }
    if (-not (Test-Path $RequirementsPath)) { return $false }
    return -not ((Get-Item $RequirementsPath).LastWriteTimeUtc -gt (Get-Item $marker).LastWriteTimeUtc)
}

# ─────────────────────────────────────────────────────────────────────────────
#  0. 环境检查 + 首次启动自动创建虚拟环境
# ─────────────────────────────────────────────────────────────────────────────

try { $Host.UI.RawUI.WindowTitle = 'Interview Agent 平台 — 一键启动' } catch { }

Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  Interview Agent — AI 模拟面试平台' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

if (-not (Get-Command 'node' -ErrorAction SilentlyContinue)) {
    Fail '未找到 Node.js，请先安装 Node.js 18+'
}

$venvDir = Join-Path $root '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$python = $venvPython

if (Test-Path $venvPython) {
    Write-Host '[提示] 使用虚拟环境: .venv' -ForegroundColor Green
} elseif ($SkipDeps) {
    Write-Host '[警告] 未找到 .venv，按 -SkipDeps 跳过自动创建，改用系统 Python' -ForegroundColor Yellow
    $python = Find-SystemPython
    if (-not $python) {
        Fail '未找到 Python：py 启动器与 PATH 里的 python.exe 都不可用。请先安装 Python 3.11+（安装时勾选 "Add python.exe to PATH"）。'
    }
} else {
    Write-Host '[提示] 未检测到虚拟环境，正在自动创建 .venv ...' -ForegroundColor Yellow
    $sysPython = Find-SystemPython
    if (-not $sysPython) {
        Fail '未找到 Python：py 启动器与 PATH 里的 python.exe 都不可用。请先安装 Python 3.11+（安装时勾选 "Add python.exe to PATH"）。'
    }

    $versionText = Get-PythonVersionText $sysPython
    if (-not $versionText) { Fail "无法运行 Python：$sysPython" }
    if ([version]$versionText -lt [version]'3.11') {
        Fail "Python 版本过低（$versionText）：本项目需要 Python 3.11+（推荐 3.11 / 3.12）。"
    }

    Write-Host "      使用系统 Python $versionText：$sysPython"
    Write-Host '[提示] 正在创建虚拟环境（首次启动只需一次，请稍候）...'
    $make = Invoke-Native { & $sysPython -m venv $venvDir }
    if ($make.Code -ne 0 -or -not (Test-Path $venvPython)) {
        Write-Host (($make.Output | Out-String).Trim()) -ForegroundColor DarkGray
        Fail "创建虚拟环境失败：$venvDir`n       Debian/Ubuntu 需要先执行 sudo apt install python3-venv；Windows 请确认安装的是 python.org 官方版本（不是 Microsoft Store 版）。"
    }

    # 自带 pip 可能偏旧，尽力升级一次；失败不影响后面的安装
    $pipSelf = Invoke-Native { & $venvPython -m pip install --upgrade pip -q }
    if ($pipSelf.Code -ne 0) {
        Write-Host '      提示: pip 自更新失败，继续使用虚拟环境自带的版本' -ForegroundColor Yellow
    }
    Write-Host '[提示] 虚拟环境创建完成: .venv' -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────────────────────
#  1. .env
# ─────────────────────────────────────────────────────────────────────────────

$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    if (Test-Path (Join-Path $root '.env.example')) {
        Copy-Item -Path (Join-Path $root '.env.example') -Destination $envFile
        Write-Host '[提示] 已创建 .env，请编辑填入你的 DEEPSEEK_API_KEY 和 JWT_SECRET' -ForegroundColor Yellow
    } else {
        Write-Host '[警告] .env.example 也不存在，请手动创建 .env 文件' -ForegroundColor Yellow
    }
}

# ─────────────────────────────────────────────────────────────────────────────
#  2. Python 依赖（装在虚拟环境里）
# ─────────────────────────────────────────────────────────────────────────────

Write-Host '[1/5] 检查 Python 依赖...'
$requirementsPath = Join-Path $root 'requirements.txt'

if ($SkipDeps) {
    Write-Host '      已按 -SkipDeps 跳过'
} elseif (Test-DepsReady -VenvDir $venvDir -RequirementsPath $requirementsPath) {
    Write-Host '      Python 依赖已就绪 √' -ForegroundColor Green
} else {
    Write-Host '      正在安装 Python 依赖到虚拟环境（首次较慢）...'
    $install = Invoke-Native { & $python -m pip install -r $requirementsPath -q }
    if ($install.Code -ne 0) {
        Write-Host (($install.Output | Out-String).Trim()) -ForegroundColor DarkGray
        Fail 'Python 依赖安装失败，请检查网络连接（国内可换镜像：pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple）'
    }
    # 空文件当标记，mtime 即「依赖装好」的时间；用 WriteAllText 而不是
    # New-Item -Force，后者对已存在的文件不会刷新 mtime。
    [IO.File]::WriteAllText((Join-Path $venvDir '.deps_installed'), '')
    Write-Host '      Python 依赖安装完成 √' -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────────────────────
#  3. 前端依赖
# ─────────────────────────────────────────────────────────────────────────────

Write-Host '[2/5] 检查前端依赖...'
$frontendDir = Join-Path $root 'frontend'
if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Host '      正在安装前端依赖...'
    Push-Location $frontendDir
    try {
        $npm = Invoke-Native { & npm install --silent }
    } finally {
        Pop-Location
    }
    if ($npm.Code -ne 0) {
        Write-Host (($npm.Output | Out-String).Trim()) -ForegroundColor DarkGray
        Fail '前端依赖安装失败（npm install）。'
    }
} else {
    Write-Host '      前端依赖已就绪 √' -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────────────────────
#  4. 数据库
# ─────────────────────────────────────────────────────────────────────────────

Write-Host '[3/5] 初始化数据库...'
$db = Invoke-Native { & $python -c "import asyncio; from database import init_db; asyncio.run(init_db()); print('数据库就绪')" }
if ($db.Code -ne 0) {
    # 与旧脚本一致：不阻断启动，应用会在首次请求时自动建表
    Write-Host '[警告] 数据库初始化失败，应用将尝试首次请求时自动建表' -ForegroundColor Yellow
} else {
    Write-Host '      数据库就绪 √' -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────────────────────
#  5. 语音（可选，必须在启动后端之前决定）
# ─────────────────────────────────────────────────────────────────────────────

Write-Host ''
Write-Host '--------------------------------------' -ForegroundColor Cyan
Write-Host '  语音功能（STT识别 + TTS朗读）' -ForegroundColor Cyan
Write-Host '  启用后可以：用麦克风说话 / AI语音回复' -ForegroundColor Cyan
Write-Host '--------------------------------------' -ForegroundColor Cyan

$voiceOn = $false
$voiceAnswer = Read-Host '启用语音功能？[y/n]（默认 n）'

if ($voiceAnswer -match '^\s*(y|yes)\s*$') {
    $voiceOn = $true

    # 只在当前会话内生效（子进程会继承），不写回 .env
    $env:VOICE_ENABLED = 'true'
    $env:STT_ENABLED = 'true'
    $env:TTS_ENABLED = 'true'
    $env:STT_SERVICE_URL = 'http://localhost:8001'
    $env:TTS_SERVICE_URL = 'http://localhost:8002'
    # HuggingFace 镜像（国内必须，否则模型下载超时）
    if (-not $env:HF_ENDPOINT) { $env:HF_ENDPOINT = 'https://hf-mirror.com' }

    Write-Host ''
    Write-Host '  STT 推理设备选择：'
    Write-Host '    [1] CPU'
    Write-Host '    [2] GPU'
    $deviceAnswer = Read-Host '请选择 [1/2]（默认 1）'
    if ($deviceAnswer -eq '2') {
        $env:STT_DEVICE = 'cuda'
        $sttPkgs = @('faster-whisper', 'ctranslate2')
        Write-Host '[语音] 已选择 GPU 模式' -ForegroundColor Green
    } else {
        $env:STT_DEVICE = 'cpu'
        $sttPkgs = @('faster-whisper')
        Write-Host '[语音] 已选择 CPU 模式' -ForegroundColor Green
    }

    # 模型由 .env 的 STT_MODEL 决定（STT 服务读取），这里只展示，不改配置
    $modelShow = 'base（默认）'
    $modelLine = Select-String -Path $envFile -Pattern '^STT_MODEL=' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($modelLine) { $modelShow = ($modelLine.Line -replace '^STT_MODEL=', '').Trim() }
    Write-Host "[语音] Whisper 模型: $modelShow（改 .env 的 STT_MODEL 可切换）"

    Write-Host '[语音] 安装语音依赖...'
    $null = Invoke-Native { & $python -m pip install @sttPkgs -q }
    $null = Invoke-Native { & $python -m pip install silero-vad numpy ffmpeg-python -q }
    $null = Invoke-Native { & $python -m pip install piper-tts huggingface_hub -q }
    $null = Invoke-Native { & $python -m pip install zhconv -q }
    Write-Host '[语音] 依赖安装完成' -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────────────────────
#  6. 启动后端
# ─────────────────────────────────────────────────────────────────────────────

Write-Host '[4/5] 启动后端服务 (端口 8000)...'
if ($voiceOn) { Write-Host '[语音] 后端将加载语音路由...' }

if (-not (Test-PortFree -Port 8000 -Name 'backend')) {
    Write-Host '[错误] 后端未启动。请释放 8000 端口后重新运行；如果已有实例在运行，直接使用它即可。' -ForegroundColor Red
    [void](Read-Host '按回车键退出')
    exit 1
}
Start-Process -FilePath $python -ArgumentList @(
    '-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'
) -WorkingDirectory $root

# 等待后端启动（首次可能要下载 Embedding 模型）
Write-Host '等待后端启动（首次可能需要下载模型，请耐心等待）...'
Start-Sleep -Seconds 8
if (-not (Test-Backend)) {
    Write-Host '后端启动较慢，再等待 5 秒...' -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}

# ─────────────────────────────────────────────────────────────────────────────
#  7. 语音微服务（如果启用）
# ─────────────────────────────────────────────────────────────────────────────

$sttStarted = $false
$ttsStarted = $false

if ($voiceOn) {
    if (Test-PortFree -Port 8001 -Name 'STT') {
        Write-Host '[语音] 启动 STT 语音识别服务 (端口 8001)...'
        Start-Process -FilePath $python -ArgumentList @(
            '-m', 'uvicorn', 'stt_service.main:app', '--host', '0.0.0.0', '--port', '8001'
        ) -WorkingDirectory $root
        $sttStarted = $true
    }
    if (Test-PortFree -Port 8002 -Name 'TTS') {
        Write-Host '[语音] 启动 TTS 语音合成服务 (端口 8002)...'
        Start-Process -FilePath $python -ArgumentList @(
            '-m', 'uvicorn', 'tts_service.main:app', '--host', '0.0.0.0', '--port', '8002'
        ) -WorkingDirectory $root
        $ttsStarted = $true
    }
    if ($sttStarted -and $ttsStarted) {
        Write-Host '[语音] 已启动（首次需下载模型 ~200MB，稍等片刻）' -ForegroundColor Green
    } else {
        Write-Host '[语音] 部分服务未启动（端口被占用，详见上方警告）' -ForegroundColor Yellow
    }
}

# ─────────────────────────────────────────────────────────────────────────────
#  8. 启动前端
# ─────────────────────────────────────────────────────────────────────────────

Write-Host '[5/5] 启动前端服务 (端口 5173)...'
$frontendStarted = $false
if (Test-PortFree -Port 5173 -Name 'frontend') {
    # npx 是 .cmd 脚本，交给 cmd /c 启动最稳妥
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'npx vite --host 0.0.0.0' -WorkingDirectory $frontendDir
    $frontendStarted = $true
}

# ─────────────────────────────────────────────────────────────────────────────
#  9. 汇总
# ─────────────────────────────────────────────────────────────────────────────

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
if ($voiceOn) {
    Write-Host '  [语音] 已启用'
    if ($sttStarted) { Write-Host '  STT: http://localhost:8001' } else { Write-Host '  STT: 未启动（端口 8001 被占用）' }
    if ($ttsStarted) { Write-Host '  TTS: http://localhost:8002' } else { Write-Host '  TTS: 未启动（端口 8002 被占用）' }
}
Write-Host '  启动完成！'
if ($frontendStarted) {
    Write-Host '  前端地址: http://localhost:5173'
    Write-Host '  登录页面: http://localhost:5173/login'
} else {
    Write-Host '  前端: 未启动（端口 5173 被占用，直接复用已在运行的前端）' -ForegroundColor Yellow
}
Write-Host '  后端地址: http://localhost:8000'
Write-Host '  API 文档: http://localhost:8000/docs'
Write-Host ''
Write-Host '  [提示] 首次使用请先注册账号'
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''
[void](Read-Host '按回车键打开前端页面')
Start-Process 'http://localhost:5173'
