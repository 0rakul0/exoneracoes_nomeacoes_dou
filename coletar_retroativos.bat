@echo off
setlocal

cd /d "%~dp0"

echo Coleta retroativa dos diarios estaduais em rodizio...
echo Ordem: RJ, SP, ES, BA, SC, PR, RS, PB, AC e CE.
echo A cada rodada e processado um caderno de cada estado.
call "%~dp0\.venv\Scripts\python.exe" "%~dp0main.py" --estaduais-rodizio-retroativo --ignorar-year-complete
if errorlevel 1 goto erro

echo.
echo Todas as coletas retroativas foram concluidas.
exit /b 0

:erro
set "CODIGO=%ERRORLEVEL%"
echo.
echo A coleta retroativa terminou com erro. Codigo: %CODIGO%
exit /b %CODIGO%
