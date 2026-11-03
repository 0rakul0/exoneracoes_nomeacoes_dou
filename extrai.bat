@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 exit /b 2
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERRO: Ambiente virtual nao encontrado. Crie a .venv antes de executar.
    exit /b 2
)
echo Coletando diarios estaduais com motor compartilhado...
"%PYTHON%" "%~dp0main.py" --ignorar-year-complete %*
set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" (
    echo Falha na coleta de diarios. Codigo: %CODIGO%
    exit /b %CODIGO%
)
echo Coleta estadual concluida.
echo AVISO: a coleta municipal RJ permanece desativada no main.py.
exit /b 0
