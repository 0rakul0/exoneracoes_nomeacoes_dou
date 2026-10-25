@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial de Pernambuco...
call python main.py --pe-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de PE concluida.
exit /b 0
