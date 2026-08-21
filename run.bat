@echo off
setlocal

echo ============================================
echo   TravelPlanner - Backend + Frontend
echo ============================================

if not exist "%~dp0BACKEND\.env" (
    echo [ERROR] Falta BACKEND\.env  ^(copia BACKEND\.env.example y completalo^)
    pause
    exit /b 1
)
if not exist "%~dp0FRONTEND\.env" (
    echo [ERROR] Falta FRONTEND\.env  ^(copia FRONTEND\.env.example y completalo^)
    pause
    exit /b 1
)

set "VENV=%~dp0.venv\Scripts\activate.bat"
if not exist "%VENV%" (
    echo [ERROR] No se encontro el entorno virtual en .venv
    echo         Crealo con:  python -m venv .venv
    pause
    exit /b 1
)

start "TravelPlanner Backend"  cmd /k "cd /d %~dp0BACKEND  && call "%VENV%" && python app.py"
start "TravelPlanner Frontend" cmd /k "cd /d %~dp0FRONTEND && call "%VENV%" && python app.py"

echo.
echo Backend  -^> http://localhost:5000
echo Frontend -^> http://localhost:8080
echo.
endlocal
