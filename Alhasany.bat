@echo off
cd /d %~dp0
set PY=
rem python.txt = path to an existing python that already has the libraries (optional, per device)
if exist python.txt set /p PY=<python.txt
if not defined PY if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
if not defined PY goto makevenv
goto run
:makevenv
echo First run: preparing Python environment...
python -m venv --system-site-packages .venv
if errorlevel 1 (echo Python not found - install Python 3.12 from python.org & pause & exit /b 1)
set PY=.venv\Scripts\python.exe
:run
"%PY%" -m alhasany %*
if errorlevel 1 pause
