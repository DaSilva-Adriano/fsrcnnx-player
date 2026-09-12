@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "UVPY=%USERPROFILE%\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe"
set "PY="

if exist "%UVPY%" (
  "%UVPY%" -c "import tkinter" >nul 2>&1
  if not errorlevel 1 set "PY=%UVPY%"
)

if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -c "import tkinter" >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
  )
)

if not defined PY (
  where python >nul 2>&1
  if not errorlevel 1 (
    python -c "import tkinter" >nul 2>&1
    if not errorlevel 1 set "PY=python"
  )
)

if not defined PY (
  echo Could not find a Python with tkinter.
  echo Install Python 3, or run:
  echo   uv python install 3.12
  pause
  exit /b 1
)

if not exist "vendor\mpv\mpv.exe" (
  echo Installing mpv and FSRCNNX shaders...
  %PY% install.py
  if errorlevel 1 (
    echo Install failed.
    pause
    exit /b 1
  )
)

%PY% mpvai.py %*
exit /b %ERRORLEVEL%
