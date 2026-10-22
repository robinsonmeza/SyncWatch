@echo off
REM Inicia SyncWatch en Windows (crea el entorno virtual la primera vez)
cd /d "%~dp0"
if not exist .venv (
    echo Creando entorno virtual...
    py -3 -m venv .venv
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python app.py
pause
