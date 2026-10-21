@echo off
chcp 65001 >nul
REM ===========================================================================
REM  Interview Agent launcher entry point (double-click this file).
REM
REM  This file only forwards to start_app.ps1 in the same folder, then exits.
REM
REM  Why the detour: double-clicking a .bat always opens a terminal window for
REM  it, and that window CANNOT be reliably hidden. On Windows 11 the default
REM  terminal is Windows Terminal, so cmd runs inside a ConPTY pseudo console:
REM  a child process calling GetConsoleWindow gets conhost's
REM  "PseudoConsoleWindow", and hiding that has no effect on the real terminal
REM  window on screen -- ShowWindow still returns success, which is why logs
REM  used to claim the console was hidden while the user still saw it.
REM
REM  So instead PowerShell starts the real launcher with -WindowStyle Hidden
REM  (STARTUPINFO.wShowWindow tells the OS not to show a window at all) and the
REM  app itself runs under pythonw.exe (GUI subsystem, no console). Nothing is
REM  ever created that would need hiding.
REM
REM  The brief cmd flash from this file is unavoidable; to avoid it entirely,
REM  run start_app.ps1 directly or make a minimized shortcut to it.
REM
REM  NOTE: keep this file ASCII-only and CRLF. Non-ASCII text in .bat comments
REM  is decoded with the console code page and can break cmd's parser.
REM
REM  Logs: logs\start_app.log  logs\desktop.log  logs\app-stderr.log
REM ===========================================================================

setlocal
cd /d "%~dp0"

REM Prefer PowerShell 7 when present, otherwise use built-in Windows PowerShell.
set "PS_EXE=powershell.exe"
where pwsh.exe >nul 2>nul && set "PS_EXE=pwsh.exe"

REM -WindowStyle Hidden: do not show a window for the PowerShell process.
REM -ExecutionPolicy Bypass: do not let the machine policy block the script.
"%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0start_app.ps1" %*

endlocal