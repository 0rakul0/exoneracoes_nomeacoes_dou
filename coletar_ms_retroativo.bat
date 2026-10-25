@echo off
setlocal

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)

echo Coletando o Diario Oficial de Mato Grosso do Sul de hoje para tras ate MS_START_DATE...
"%PYTHON%" main.py --ms-retroativo --ignorar-year-complete
set "CODIGO=%ERRORLEVEL%"

if not "%CODIGO%"=="0" (
    echo A coleta retroativa de MS terminou com erro. Codigo: %CODIGO%
    exit /b %CODIGO%
)

echo Coleta retroativa de MS concluida.
exit /b 0
