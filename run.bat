@echo off
echo Iniciando Backend y Frontend...

start "Backend Flask" cmd /k "cd /d %~dp0BACKEND && call venv\Scripts\activate.bat && python app.py"
start "Frontend Flask" cmd /k "cd /d %~dp0FRONTEND && call venv\Scripts\activate.bat && python app.py"

echo Servidores iniciados en ventanas separadas.
