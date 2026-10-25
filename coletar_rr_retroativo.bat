@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial de Roraima...
call "%~dp0\.venv\Scripts\python.exe" "%~dp0main.py" --rr-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de RR concluida.
exit /b 0
