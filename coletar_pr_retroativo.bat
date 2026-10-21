@echo off
setlocal

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)

echo Coletando todos os tipos do Diario Oficial do PR a partir de hoje, retrocedendo ate PR_START_DATE...
"%PYTHON%" main.py --pr-retroativo --ignorar-year-complete
set "CODIGO=%ERRORLEVEL%"

if not "%CODIGO%"=="0" (
    echo A coleta retroativa do PR terminou com erro. Codigo: %CODIGO%
    exit /b %CODIGO%
)

echo Coleta retroativa do PR concluida.
exit /b 0
