@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial do Piaui...
call python main.py --pi-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de PI concluida.
exit /b 0
