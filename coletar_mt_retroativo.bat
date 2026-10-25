@echo off
setlocal

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)

echo Coletando o Diario Oficial de Mato Grosso de hoje para tras ate MT_START_DATE...
"%PYTHON%" main.py --mt-retroativo --ignorar-year-complete
set "CODIGO=%ERRORLEVEL%"

if not "%CODIGO%"=="0" (
    echo A coleta retroativa de MT terminou com erro. Codigo: %CODIGO%
    exit /b %CODIGO%
)

echo Coleta retroativa de MT concluida.
exit /b 0
