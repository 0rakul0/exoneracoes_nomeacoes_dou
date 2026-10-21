@echo off
setlocal
cd /d "%~dp0"
echo Coletando os cadernos do DOE/CE de hoje para tras...
.\.venv\Scripts\python.exe main.py --ce-retroativo
if errorlevel 1 (
    echo Falha na coleta retroativa do CE.
    exit /b 1
)
echo Coleta retroativa do CE concluida.
endlocal
