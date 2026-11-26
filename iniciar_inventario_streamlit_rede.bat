@echo off
setlocal
cd /d "%~dp0"
echo Use o IPv4 do adaptador Wi-Fi do PC, exibido por ipconfig.
set /p "LAN_IP=Digite o IPv4 do PC: "
if not defined LAN_IP (
    echo.
    echo O endereco IP e obrigatorio para limitar o servidor ao Wi-Fi.
    pause
    exit /b 1
)
if exist "%~dp0\.venv\Scripts\python.exe" (
    "%~dp0\.venv\Scripts\python.exe" -m streamlit run "%~dp0\streamlit_app.py" --server.address "%LAN_IP%" --server.port 8501
) else (
    python -m streamlit run "%~dp0\streamlit_app.py" --server.address "%LAN_IP%" --server.port 8501
)
if errorlevel 1 (
    echo.
    echo Nao foi possivel iniciar o Streamlit. Instale as dependencias de requirements.txt.
    pause
)
