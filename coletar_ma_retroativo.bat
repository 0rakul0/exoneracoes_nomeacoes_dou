@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial do Maranhao...
call python main.py --ma-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de MA concluida.
exit /b 0
