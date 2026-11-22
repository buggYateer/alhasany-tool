@echo off
setlocal
pushd "%~dp0"
title Alhasany tool
set "PY="
rem python.txt = path to an existing python that already has the libraries (per device)
if exist "python.txt" set /p PY=<"python.txt"
if not defined PY goto venv
if exist "%PY%" goto run
echo [!] python.txt points to: "%PY%" - file not found
goto stop
:venv
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe" & goto run)
if /i "%~1"=="install" goto install
echo.
echo No Python environment for the tool on this device yet.
echo To set it up (downloads libraries, about 2 GB), run:  Alhasany.bat install
goto stop
:run
"%PY%" -m alhasany %*
if errorlevel 1 pause
popd
exit /b
:install
echo Creating Python environment (uses libraries already on this device when possible)...
python -m venv --system-site-packages .venv
if not exist ".venv\Scripts\python.exe" (echo [!] Python not found - install Python 3.12 from python.org & goto stop)
".venv\Scripts\python.exe" -m alhasany setup
pause
popd
exit /b
:stop
echo Nothing was downloaded.
pause
popd
exit /b 1