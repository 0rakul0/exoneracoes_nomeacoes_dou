@echo off
setlocal EnableExtensions
call "%~dp0executar_coleta_uf.bat" PB %*
set "CODIGO=%ERRORLEVEL%"
exit /b %CODIGO%
