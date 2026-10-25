@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial de Sergipe...
call "%~dp0\.venv\Scripts\python.exe" "%~dp0main.py" --se-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de SE concluida.
exit /b 0
