@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial do Tocantins...
call "%~dp0\.venv\Scripts\python.exe" "%~dp0main.py" --to-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de TO concluida.
exit /b 0
