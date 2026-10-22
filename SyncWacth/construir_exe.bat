@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title SyncWatch - Construccion del ejecutable
cd /d "%~dp0"

echo.
echo  ==========================================================
echo    SyncWatch - generar SyncWatch.exe y el instalador
echo  ==========================================================
echo.

REM ---------------------------------------------------------------- 1. Python
echo [1/5] Buscando Python...
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    echo   No se encontro Python. Instale Python 3.10+ desde https://www.python.org
    echo   ^(marque "Add python.exe to PATH"^) y vuelva a ejecutar este archivo.
    pause & exit /b 1
)
%PY% --version

REM ---------------------------------------------------------------- 2. Entorno
echo.
echo [2/5] Preparando entorno de construccion (.venv-build)...
if not exist .venv-build ( %PY% -m venv .venv-build || ( echo   Error creando el entorno virtual & pause & exit /b 1 ) )
set "VPY=.venv-build\Scripts\python.exe"
%VPY% -m pip install --upgrade pip --quiet
%VPY% -m pip install -r requirements.txt pyinstaller --quiet || ( echo   Error instalando dependencias ^(revise su conexion^) & pause & exit /b 1 )

REM ---------------------------------------------------------------- 3. Pruebas
echo.
echo [3/5] Ejecutando pruebas automatizadas (unos 40 s)...
if not exist evidencias mkdir evidencias
%VPY% -m pytest -q -p no:cacheprovider > evidencias\pruebas_pytest_windows.txt 2>&1
if errorlevel 1 (
    type evidencias\pruebas_pytest_windows.txt
    echo   Algunas pruebas fallaron. Revise evidencias\pruebas_pytest_windows.txt
    pause & exit /b 1
)
for /f "delims=" %%L in ('findstr /c:"passed" evidencias\pruebas_pytest_windows.txt') do echo   %%L

REM ---------------------------------------------------------------- 4. PyInstaller
echo.
echo [4/5] Generando dist\SyncWatch.exe con PyInstaller...
%VPY% -m PyInstaller --noconfirm --clean --log-level WARN SyncWatch.spec
if not exist dist\SyncWatch.exe ( echo   No se genero el ejecutable. & pause & exit /b 1 )
echo   OK: dist\SyncWatch.exe

REM ---------------------------------------------------------------- 5. Instalador
echo.
echo [5/5] Generando el instalador con Inno Setup...
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
    if exist %%P set "ISCC=%%~P"
)
if not defined ISCC (
    where winget >nul 2>nul
    if not errorlevel 1 (
        choice /c SN /m "  Inno Setup no esta instalado. Instalarlo ahora con winget"
        if !errorlevel! == 1 (
            winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
            for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
                if exist %%P set "ISCC=%%~P"
            )
        )
    )
)
if defined ISCC (
    "!ISCC!" /Q instalador.iss && echo   OK: dist\SyncWatch_Instalador_1.0.0.exe
) else (
    echo   Se omite el instalador. Puede instalar Inno Setup desde https://jrsoftware.org/isdl.php
    echo   y volver a ejecutar este archivo. dist\SyncWatch.exe ya funciona por si solo.
)

echo.
echo  ==========================================================
echo    Listo. Archivos en la carpeta "dist":
dir /b dist\*.exe
echo  ==========================================================
echo.
pause
