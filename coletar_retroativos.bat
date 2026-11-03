@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 exit /b 2
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERRO: Ambiente virtual nao encontrado em "%PYTHON%"
    exit /b 2
)
rem Um ciclo por rodada, preservando a estrategia de rodizio entre as UFs.
set "INTERVALO_SEGUNDOS=3600"
if not "%~1"=="" set "INTERVALO_SEGUNDOS=%~1"
echo Coleta retroativa em rodizio para as 27 UFs.
echo Intervalo: %INTERVALO_SEGUNDOS% segundos. Ctrl+C para encerrar.
:rodada
echo Iniciando rodada: %DATE% %TIME%
"%PYTHON%" "%~dp0main.py" --estaduais-rodizio-retroativo --ignorar-year-complete
set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" echo AVISO: rodada falhou com codigo %CODIGO%. Tentando novamente apos intervalo.
timeout /t %INTERVALO_SEGUNDOS% /nobreak
if errorlevel 1 exit /b %ERRORLEVEL%
goto rodada
