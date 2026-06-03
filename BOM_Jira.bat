@echo off
REM Launcher da interface grafica do BOM -> Jira Automation.
REM Roda sem janela de terminal (usa pythonw do .venv).

setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "gui.py"
) else (
    REM Fallback: pythonw do PATH; se nao houver, usa python (com console).
    where pythonw >nul 2>nul
    if %errorlevel%==0 (
        start "" pythonw "gui.py"
    ) else (
        python "gui.py"
    )
)
endlocal
