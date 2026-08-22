@echo off
setlocal

echo ============================================
echo   TravelPlanner - Backend + Frontend
echo ============================================
echo.

set "VENV=%~dp0.venv\Scripts\activate.bat"
if not exist "%VENV%" (
    echo [ERROR] No se encontro el entorno virtual en .venv
    echo         Crealo con:  python -m venv .venv
    echo         Y despues:   .venv\Scripts\activate ^&^& pip install -r BACKEND\requirements.txt -r FRONTEND\requirements.txt
    pause
    exit /b 1
)

call "%VENV%"

REM Genera los .env que falten y sincroniza la clave compartida.
REM Sin esto el backend rechaza todo con 401 y no se puede ni loguear.
python "%~dp0setup.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la preparacion del entorno.
    pause
    exit /b 1
)

echo.
echo Levantando servidores...
echo   El backend aplica las migraciones pendientes al arrancar.
echo.

start "TravelPlanner Backend"  cmd /k "cd /d %~dp0BACKEND  && call "%VENV%" && python app.py"
start "TravelPlanner Frontend" cmd /k "cd /d %~dp0FRONTEND && call "%VENV%" && python app.py"

echo Backend  -^> http://localhost:5000
echo Frontend -^> http://localhost:8080
echo.
endlocal
