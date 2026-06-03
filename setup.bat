@echo off
REM Setup inicial: cria o .venv, instala dependencias e o navegador Edge do Playwright.
REM Rode apenas UMA VEZ por maquina. Depois use BOM_Jira.bat para abrir a interface.

setlocal
cd /d "%~dp0"

echo ============================================================
echo  Setup do BOM -^> Jira Automation
echo ============================================================
echo.

REM 1) Verifica Python
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale o Python 3.10 ou superior em https://www.python.org/downloads/
    echo e marque "Add python.exe to PATH" durante a instalacao.
    pause
    exit /b 1
)

REM 2) Cria o .venv se nao existir
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Criando ambiente virtual .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o .venv.
        pause
        exit /b 1
    )
) else (
    echo [1/3] .venv ja existe - pulando.
)

REM 3) Instala dependencias
echo.
echo [2/3] Instalando dependencias Python ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)

REM 4) Instala o navegador Edge controlado pelo Playwright
echo.
echo [3/3] Instalando o navegador Edge para o Playwright ...
".venv\Scripts\python.exe" -m playwright install msedge
if errorlevel 1 (
    echo [AVISO] Falha ao instalar o Edge via Playwright.
    echo Verifique se o Microsoft Edge esta instalado na maquina.
)

echo.
echo ============================================================
echo  Setup concluido com sucesso!
echo  Agora rode BOM_Jira.bat para abrir a interface.
echo ============================================================
pause
endlocal
