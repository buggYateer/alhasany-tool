@echo off
cd /d %~dp0
if exist .venv\Scripts\python.exe (.venv\Scripts\python -m alhasany) else (python -m alhasany)
pause
