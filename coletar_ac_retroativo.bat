@echo off
setlocal
cd /d "%~dp0"
echo Coletando DOE/AC e DJE/AC de hoje para tras...
.\.venv\Scripts\python.exe main.py --ac-retroativo
if errorlevel 1 (
    echo Falha na coleta retroativa do AC.
    exit /b 1
)
echo Coleta retroativa do AC concluida.
endlocal
