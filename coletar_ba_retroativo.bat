@echo off
setlocal

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)

echo Coletando DOE, DOEL e DJE da BA a partir de hoje, retrocedendo ate BA_START_DATE...
"%PYTHON%" main.py --ba-retroativo --ignorar-year-complete
set "CODIGO=%ERRORLEVEL%"

if not "%CODIGO%"=="0" (
    echo A coleta retroativa da BA terminou com erro. Codigo: %CODIGO%
    exit /b %CODIGO%
)

echo Coleta retroativa da BA concluida.
exit /b 0
