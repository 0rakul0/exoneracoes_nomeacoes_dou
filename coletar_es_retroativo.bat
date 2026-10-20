@echo off
setlocal

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)

echo Coletando Diario Oficial do ES a partir de hoje, retrocedendo ate ES_START_DATE...
"%PYTHON%" main.py --es-retroativo --ignorar-year-complete
set "CODIGO=%ERRORLEVEL%"

if not "%CODIGO%"=="0" (
    echo A coleta retroativa do ES terminou com erro. Codigo: %CODIGO%
    exit /b %CODIGO%
)

echo Coleta retroativa do ES concluida.
exit /b 0
