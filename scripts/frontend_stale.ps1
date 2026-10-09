# 判断前端构建产物（frontend\dist）是否已落后于源码（frontend\src）。
#
# 输出（供 start_app.bat 的 for /f 读取）：
#     newer      —— 源码比产物新，需要重新构建
#     （无输出） —— 产物是最新的，或无法判断
#
# 为什么要单独成文件：
#   `|` 在 bat 的 for /f 命令体里必须转义成 `^|`，内联写极易被 cmd
#   当成管道符拆开，报出与真实原因毫不相干的错误
#   （实测表现为 `'t-Object' is not recognized as an internal or external command`）。
#   放进独立脚本就完全不用考虑这层转义。
#
# 兼容 Windows PowerShell 5.1（系统自带 powershell.exe）：
#   不用 `??`、`?.`、三元等 PS7 语法，管道也避免跨行书写
#   （多行管道后面直接跟 `} elseif` 会被 5.1 的解析器判为语法错误）。
#
# 退出码始终为 0：这只是个「优化判断」，失败时应让启动流程继续，
# 而不是把整个启动脚本带崩。

$ErrorActionPreference = 'SilentlyContinue'

# 以脚本自身位置推算项目根，避免依赖调用方的当前目录。
#
# $PSScriptRoot 在某些调用方式下会是空字符串（实测：经 bat 的 for /f
# 调用 powershell -File 时），此时 Join-Path 会退化成相对路径，
# 判断结果就完全错了。因此这里显式回退到 $MyInvocation.MyCommand.Path，
# 再用 [IO.Path]::GetFullPath 归一成绝对路径。
$scriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($scriptDir)) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrEmpty($scriptDir)) {
    # 两种方式都拿不到：无法可靠判断，直接放弃（视为不需要重建）
    exit 0
}
$root = Split-Path -Parent ([IO.Path]::GetFullPath($scriptDir))

$distIndex = Join-Path $root 'frontend\dist\index.html'
$srcDir = Join-Path $root 'frontend\src'

if (-not (Test-Path $distIndex)) { exit 0 }
if (-not (Test-Path $srcDir)) { exit 0 }

$distTime = (Get-Item $distIndex).LastWriteTime
$distDirTime = (Get-Item (Join-Path $root 'frontend\dist')).LastWriteTime
$srcDirTime = (Get-Item $srcDir).LastWriteTime

$newestSrcTime = $distTime
$newest = Get-ChildItem $srcDir -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($newest) { $newestSrcTime = $newest.LastWriteTime }

# 三个比较覆盖不同情况：
#   newestSrcTime —— 已有源文件被改动
#   srcDirTime    —— 增删文件（只改目录时间戳）
#   distDirTime   —— 产物目录本身比源码旧（dist 被整体重建过）
$stale = $false
if ($newestSrcTime -gt $distTime) { $stale = $true }
if ($srcDirTime -gt $distTime) { $stale = $true }

if ($stale) { Write-Output 'newer' }

exit 0