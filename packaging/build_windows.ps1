<#
.SYNOPSIS
    Interview Agent — Windows 客户端一键构建脚本（前端 + PyInstaller + 安装包）

.DESCRIPTION
    把「配 Python 环境、装依赖、构建前端、PyInstaller 打包、Inno Setup
    制安装包」压缩成一条命令，产出可直接分发的 setup.exe。

    前提（只需安装一次）：
        1. Python 3.11+（勾选 Add to PATH）
        2. Node.js 18+
        3. Inno Setup 6（仅制作安装包需要；不加 -Installer 可跳过）
           winget install JRSoft.InnoSetup

    用法（在项目根目录执行）：
        .\packaging\build_windows.ps1                    # 完整构建（含安装包）
        .\packaging\build_windows.ps1 -SkipFrontend      # 前端已构建过，跳过
        .\packaging\build_windows.ps1 -SkipInstaller     # 只出 onedir，不做安装包

    产物：
        dist\client\InterviewAgent\           PyInstaller onedir（可直接运行）
        dist\client\InterviewAgentSetup.exe   Inno Setup 安装包（默认开启时）

.NOTES
    * 构建发生在 dist\ 与 build\ 目录，不会污染源码树（两者均在 .gitignore）。
    * 打包版按设计不含语音（STT/TTS）与 RAG 依赖，详见
      packaging/interview-agent.spec 顶部的「设计取舍」与
      docs/WINDOWS_PACKAGING.md。
#>
[CmdletBinding()]
param(
    # 跳过前端构建（frontend/dist 已存在时用）
    [switch]$SkipFrontend,
    # 跳过安装包制作（只产出 PyInstaller onedir）
    [switch]$SkipInstaller,
    # 构建用的虚拟环境目录（默认 .build\venv，位于 .gitignore 覆盖范围外时请自行清理）
    [string]$VenvDir = ".build\venv",
    # 安装包版本号（影响安装包文件名与窗口标题）
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot

function Write-Step($Text) {
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

try {
    # ── 0. 环境检查 ──
    Write-Step "检查构建环境"
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "未找到 python。请先安装 Python 3.11+ 并加入 PATH。"
    }
    $pyVersion = (python --version).ToString()
    Write-Host "Python: $pyVersion"
    if ($pyVersion -notmatch "3\.(1[1-9]|[2-9][0-9])") {
        Write-Warning "项目要求 Python 3.11+，当前为 $pyVersion，构建可能失败。"
    }

    # ── 1. 虚拟环境 + 依赖 ──
    Write-Step "准备虚拟环境并安装依赖"
    if (-not (Test-Path $VenvDir)) {
        python -m venv $VenvDir
    }
    $venvPython = Join-Path $VenvDir "Scripts\python.exe"
    & $venvPython -m pip install -q --upgrade pip
    # 核心依赖（不含 requirements-rag.txt：RAG 的重依赖按设计不打入包体）
    & $venvPython -m pip install -q -r requirements.txt pyinstaller

    # ── 2. 前端构建 ──
    if (-not $SkipFrontend) {
        Write-Step "构建前端（npm ci && npm run build）"
        Push-Location frontend
        try {
            npm ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci 失败" }
            npm run build
            if ($LASTEXITCODE -ne 0) { throw "npm run build 失败" }
        }
        finally {
            Pop-Location
        }
        if (-not (Test-Path "frontend\dist\index.html")) {
            throw "frontend\dist\index.html 不存在，前端构建失败"
        }
    }
    else {
        Write-Step "跳过前端构建（-SkipFrontend）"
        if (-not (Test-Path "frontend\dist\index.html")) {
            throw "frontend\dist 不存在且指定了 -SkipFrontend。请先构建前端。"
        }
    }

    # ── 3. PyInstaller 打包 ──
    Write-Step "PyInstaller 打包（onedir）"
    & $venvPython -m PyInstaller packaging\interview-agent.spec `
        --distpath dist\client `
        --workpath build\client `
        --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }

    $appExe = "dist\client\InterviewAgent\InterviewAgent.exe"
    if (-not (Test-Path $appExe)) {
        throw "未找到产物 $appExe"
    }
    $sizeMB = [math]::Round((Get-ChildItem "dist\client\InterviewAgent" -Recurse |
        Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    Write-Host "打包完成: $appExe（$sizeMB MB）" -ForegroundColor Green

    # ── 4. Inno Setup 安装包 ──
    if (-not $SkipInstaller) {
        Write-Step "制作安装包（Inno Setup）"
        $iscc = Get-Command iscc -ErrorAction SilentlyContinue
        if (-not $iscc) {
            $candidates = @(
                "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
            )
            $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        }
        if (-not $iscc) {
            Write-Warning "未找到 Inno Setup（iscc）。跳过安装包制作；onedir 仍可使用。`n" +
                "安装 Inno Setup 后重跑本脚本即可：winget install JRSoft.InnoSetup"
        }
        else {
            & $iscc "/DAppVersion=$Version" packaging\installer.iss
            if ($LASTEXITCODE -ne 0) { throw "Inno Setup 构建失败" }
            $setup = "dist\client\InterviewAgentSetup-$Version.exe"
            if (Test-Path $setup) {
                Write-Host "安装包完成: $setup" -ForegroundColor Green
            }
        }
    }

    Write-Step "全部完成"
    Write-Host "onedir:  $ProjectRoot\dist\client\InterviewAgent" -ForegroundColor Green
    Write-Host "双击 InterviewAgent.exe 即可运行（无需 Python 环境）。" -ForegroundColor Green
}
finally {
    Pop-Location
}
