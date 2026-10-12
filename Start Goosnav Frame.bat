@echo off
rem Start Goosnav Frame on Windows (x64). Double-click, or run from a terminal:
rem   "Start Goosnav Frame.bat" [--no-browser] [--port 9000] [--local]
rem The first run downloads Python and the locked libraries (about 100 MB). Close this window to stop.
setlocal
set "ROOT=%~dp0"
set "APP=%ROOT%app"
set "DATA=%LOCALAPPDATA%\GoosnavFrame"
if not exist "%APP%\launcher\bootstrap.py" (
  echo Cannot find the app folder next to this script: %APP%
  pause & exit /b 1
)
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
  echo Windows on ARM is not supported yet.
  pause & exit /b 1
)

set "UV=%APP%\launcher\tools\windows-x64\uv.exe"
if not exist "%UV%" (
  where uv >nul 2>nul || (
    echo No setup tool found. Extract the complete ZIP so app\launcher\tools is present.
    pause & exit /b 1
  )
  set "UV=uv"
)

if not exist "%DATA%\data" mkdir "%DATA%\data"
if not exist "%DATA%\config" mkdir "%DATA%\config"
set "UV_PROJECT_ENVIRONMENT=%DATA%\runtimes\manual"
set "UV_PYTHON_INSTALL_DIR=%DATA%\python"
set "UV_CACHE_DIR=%DATA%\cache\uv"

echo Preparing Goosnav Frame (first run downloads about 100 MB)...
"%UV%" sync --project "%APP%" --locked --no-dev --managed-python --quiet
if errorlevel 1 (
  echo Setup failed. Check your network connection and run this again.
  pause & exit /b 1
)

set "PYTHONPATH="
set "GOOSNAV_APP_ROOT=%APP%"
set "GOOSNAV_APP_DATA=%DATA%"
set "GOOSNAV_DATA_DIR=%DATA%\data"
set "GOOSNAV_CONFIG_DIR=%DATA%\config"
if not defined GOOSNAV_PORT_PREFERENCE set "GOOSNAV_PORT_PREFERENCE=8787"
"%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe" "%APP%\launcher\bootstrap.py" --open %*
pause
