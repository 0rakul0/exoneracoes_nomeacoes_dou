@echo off
setlocal EnableExtensions
set "DOU_UF=RS"
call "%~dp0executar_coleta_uf.bat" %*
set "CODIGO=%ERRORLEVEL%"
exit /b %CODIGO%
