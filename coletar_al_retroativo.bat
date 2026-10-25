@echo off
setlocal
cd /d "%~dp0"
echo Coleta retroativa do Diario Oficial de Alagoas...
call python main.py --al-retroativo --ignorar-year-complete
if errorlevel 1 exit /b 1
echo Coleta de AL concluida.
exit /b 0
