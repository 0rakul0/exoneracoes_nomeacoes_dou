@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)
echo Coletando o Diario Oficial de Goias de hoje para tras ate GO_START_DATE...
"%PYTHON%" main.py --go-retroativo --ignorar-year-complete
if errorlevel 1 exit /b %ERRORLEVEL%
echo Coleta retroativa de GO concluida.
exit /b 0
