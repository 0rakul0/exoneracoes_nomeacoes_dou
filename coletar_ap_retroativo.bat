@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial do Amapa...
call python main.py --ap-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de AP concluida.
exit /b 0
