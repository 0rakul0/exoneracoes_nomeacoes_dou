@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial do Para...
call python main.py --pa-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de PA concluida.
exit /b 0
