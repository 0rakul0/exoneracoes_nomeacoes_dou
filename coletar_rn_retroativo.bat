@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial do Rio Grande do Norte...
call "%~dp0\.venv\Scripts\python.exe" "%~dp0main.py" --rn-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de RN concluida.
exit /b 0
