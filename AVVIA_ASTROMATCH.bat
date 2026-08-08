@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AstroMatch V7

echo.
echo ==========================================
echo       ASTROMATCH V7 - CONFIGURAZIONE
echo ==========================================
echo.

set "PY312="

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY312=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY312 if exist "%ProgramFiles%\Python312\python.exe" set "PY312=%ProgramFiles%\Python312\python.exe"

where py >nul 2>nul
if not defined PY312 if %errorlevel%==0 (
    py -3.12 -c "import sys; print(sys.executable)" >nul 2>nul
    if not errorlevel 1 set "PY312=py -3.12"
)

if not defined PY312 (
    echo Python 3.12 non trovato. Provo winget...
    where winget >nul 2>nul
    if %errorlevel%==0 winget install --id Python.Python.3.12 -e --source winget --accept-source-agreements --accept-package-agreements
)

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY312=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY312 if exist "%ProgramFiles%\Python312\python.exe" set "PY312=%ProgramFiles%\Python312\python.exe"

if not defined PY312 (
    echo.
    echo Python 3.12 non disponibile.
    echo Installa Python 3.12 per Windows e seleziona "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo Python 3.12: %PY312%
echo.

REM If an old environment exists, keep it only when it is really Python 3.12.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo Ricreo l'ambiente con Python 3.12...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    "%PY312%" -m venv .venv
    if errorlevel 1 goto :err
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

echo Aggiorno pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :err

echo.
echo Rimuovo eventuale vecchio pyswisseph...
"%VENV_PY%" -m pip uninstall -y pyswisseph >nul 2>nul

echo.
echo Installo Swiss Ephemeris precompilato per Python 3.12...
"%VENV_PY%" -m pip install --only-binary=:all: pysweph==2.10.3.6
if errorlevel 1 (
    echo.
    echo ERRORE: non e' stata trovata la wheel Windows precompilata.
    echo.
    goto :err
)

echo.
echo Verifico Swiss Ephemeris...
"%VENV_PY%" -c "import swisseph as swe; print('Swiss Ephemeris OK:', swe.version)"
if errorlevel 1 goto :err

echo.
echo Installo/aggiorno i componenti di AstroMatch...
"%VENV_PY%" -m pip install -r requirements.txt --only-binary=:all:
if errorlevel 1 goto :err

echo.
echo ==========================================
echo       ASTROMATCH E' PRONTO
echo ==========================================
echo.

start "" http://127.0.0.1:8000
"%VENV_PY%" -m uvicorn app:app --host 127.0.0.1 --port 8000

pause
exit /b 0

:err
echo.
echo ERRORE durante la configurazione di AstroMatch.
echo Nessun componente C++/Visual Studio deve essere necessario.
pause
exit /b 1
