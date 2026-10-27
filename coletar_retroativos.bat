@echo off
setlocal EnableExtensions

cd /d "%~dp0"

rem Intervalo entre rodadas, em segundos. Padrao: 1 hora.
set "INTERVALO_SEGUNDOS=3600"
if not "%~1"=="" set "INTERVALO_SEGUNDOS=%~1"

echo Coleta continua dos 27 diarios estaduais em rodizio.
echo Intervalo entre rodadas: %INTERVALO_SEGUNDOS% segundos.
echo Para encerrar, pressione Ctrl+C.

:rodada
echo.
echo ==================================================
echo Inicio da rodada: %DATE% %TIME%
echo ==================================================

echo Coleta retroativa dos 27 diarios estaduais em rodizio...
echo A fila alterna um caderno por estado, incluindo todos os estados e o DF.
call "%~dp0\.venv\Scripts\python.exe" "%~dp0main.py" --estaduais-rodizio-retroativo --ignorar-year-complete
if errorlevel 1 goto erro_rodada

echo.
echo Rodada dos 27 diarios estaduais concluida.
goto aguardar

:erro_rodada
set "CODIGO=%ERRORLEVEL%"
echo.
echo A rodada terminou com erro. Codigo: %CODIGO%
echo A proxima tentativa sera feita apos o intervalo configurado.

:aguardar
echo.
echo Proxima rodada em %INTERVALO_SEGUNDOS% segundos...
timeout /t %INTERVALO_SEGUNDOS% /nobreak
goto rodada
