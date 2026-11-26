@echo off
setlocal
cd /d "%~dp0\.."
python -m inventario_desktop.web_app
if errorlevel 1 (
    echo.
    echo Nao foi possivel iniciar a versao web local do INVENTARIO. Verifique o Python.
    pause
)
