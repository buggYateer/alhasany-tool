@echo off
setlocal
pushd "%~dp0"
echo Alhasany tool folder: %CD%
set "PY="
rem python.txt = path to an existing python that already has the libraries (optional, per device)
if exist "python.txt" set /p PY=<"python.txt"
if defined PY if not exist "%PY%" (
  echo [!] python.txt points to a missing file: %PY%
  set "PY="
)
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if defined PY goto run
echo First run: preparing Python environment...
where py >nul 2>nul && (py -3.12 -m venv --system-site-packages .venv || py -3 -m venv --system-site-packages .venv) || python -m venv --system-site-packages .venv
if not exist ".venv\Scripts\python.exe" (
  echo [!] Python not found. Install Python 3.12 from python.org - tick "Add python.exe to PATH"
  pause
  exit /b 1
)
set "PY=.venv\Scripts\python.exe"
:run
echo Using: %PY%
"%PY%" -m alhasany %*
if errorlevel 1 pause
popd