@echo off
setlocal

cd /d "%~dp0"
".\.venv\Scripts\python.exe" main.py --ignorar-year-complete
if errorlevel 1 goto erro

".\.venv\Scripts\python.exe" main.py --coletar-municipais-rj
if errorlevel 1 goto erro

echo.
echo Coleta finalizada. Pressione qualquer tecla para fechar.
pause >nul
exit /b 0

:erro
set "CODIGO=%ERRORLEVEL%"
echo.
echo A coleta terminou com erro. Codigo: %CODIGO%
pause >nul
exit /b %CODIGO%
