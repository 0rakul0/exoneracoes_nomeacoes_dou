@echo off
setlocal EnableExtensions
set "DOU_UF=TO"
call "%~dp0executar_coleta_uf.bat" %*
set "CODIGO=%ERRORLEVEL%"
exit /b %CODIGO%
