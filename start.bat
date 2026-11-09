@echo off
REM ===========================================================================
REM  Interview Agent launcher entry point (double-click this file).
REM
REM  The actual logic lives in start.ps1 (PowerShell). Why it left .bat:
REM    * under chcp 65001, non-ASCII text inside if (...)/for (...) blocks breaks
REM      cmd's parser, so the old version had to use goto for everything;
REM    * %errorlevel% inside a block is expanded when the block is parsed, so it
REM      reports the value from before the block ran;
REM    * port checks needed netstat + findstr string surgery, while PowerShell has
REM      Get-NetTCPConnection and Start-Process -WorkingDirectory.
REM
REM  This file only forwards to start.ps1 and passes any arguments through, e.g.
REM      start.bat -SkipDeps
REM
REM  NOTE: keep this file ASCII-only and CRLF. Non-ASCII text in .bat comments is
REM  decoded with the console code page and can break cmd's parser.
REM ===========================================================================

setlocal
cd /d "%~dp0"

REM Prefer PowerShell 7 when present, otherwise use built-in Windows PowerShell.
set "PS_EXE=powershell.exe"
where pwsh.exe >nul 2>nul && set "PS_EXE=pwsh.exe"

"%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*

endlocal
