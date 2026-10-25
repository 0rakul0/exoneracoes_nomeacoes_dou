@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)
echo Coletando o Diario Oficial do Amazonas de hoje para tras ate AM_START_DATE...
"%PYTHON%" main.py --am-retroativo --ignorar-year-complete
if errorlevel 1 exit /b %ERRORLEVEL%
echo Coleta retroativa de AM concluida.
exit /b 0
