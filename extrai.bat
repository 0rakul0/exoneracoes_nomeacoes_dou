@echo off
setlocal

cd /d "%~dp0"
".\.venv\Scripts\python.exe" main.py --ignorar-year-complete

echo.
echo Coleta finalizada. Pressione qualquer tecla para fechar.
pause >nul
