@echo off
setlocal EnableExtensions
call "%~dp0executar_coleta_uf.bat" SE %*
set "CODIGO=%ERRORLEVEL%"
exit /b %CODIGO%
