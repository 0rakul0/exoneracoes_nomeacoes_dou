@echo off
setlocal EnableExtensions
set "DOU_UF=BA"
call "%~dp0executar_coleta_uf.bat" %*
set "CODIGO=%ERRORLEVEL%"
exit /b %CODIGO%
