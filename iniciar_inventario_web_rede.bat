@echo off
setlocal
cd /d "%~dp0\.."
echo Use o IPv4 privado do PC, exibido por ipconfig.
set /p "LAN_IP=Digite o IPv4 do PC: "
if not defined LAN_IP (
    echo.
    echo O endereco IP e obrigatorio para limitar o servidor ao adaptador escolhido.
    pause
    exit /b 1
)
python -m inventario_desktop.web_app --lan --host "%LAN_IP%"
if errorlevel 1 (
    echo.
    echo Nao foi possivel iniciar a versao web na rede local. Verifique o Python.
    pause
)
