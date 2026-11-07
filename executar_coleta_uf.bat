@echo off
setlocal EnableExtensions
set "UF=%DOU_UF%"
if "%UF%"=="" (
    echo ERRO: use um dos scripts coletar_uf_retroativo.bat.
    exit /b 2
)
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERRO: Python da .venv nao encontrado em "%PYTHON%"
    exit /b 2
)
if not exist "%ROOT%main.py" (
    echo ERRO: main.py nao encontrado na raiz do projeto.
    exit /b 2
)
cd /d "%ROOT%"
if errorlevel 1 exit /b 2
echo ==================================================
echo Coleta retroativa %UF% - %DATE% %TIME%
echo Motor de extracao compartilhado via main.py
echo ==================================================
"%PYTHON%" "%ROOT%main.py" --%UF%-retroativo --ignorar-year-complete %*
set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" (
    echo ERRO: Coleta retroativa %UF% falhou. Codigo: %CODIGO%
) else (
    echo Coleta retroativa %UF% finalizada.
)
exit /b %CODIGO%
