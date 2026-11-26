@echo off
setlocal
cd /d "%~dp0\.."
python -m inventario_desktop
if errorlevel 1 (
    echo.
    echo Nao foi possivel iniciar o INVENTARIO. Verifique o Python e o openpyxl.
    pause
)
