@echo off
setlocal
cd /d "%~dp0"
echo Coletando DOE/PB e DJE/PB de hoje para tras...
.\.venv\Scripts\python.exe main.py --pb-retroativo
if errorlevel 1 (
    echo Falha na coleta retroativa da PB.
    exit /b 1
)
echo Coleta retroativa da PB concluida.
endlocal
