@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial de Rondonia...
call "%~dp0\.venv\Scripts\python.exe" "%~dp0main.py" --ro-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de RO concluida.
exit /b 0
