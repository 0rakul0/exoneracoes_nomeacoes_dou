@echo off
setlocal EnableExtensions
call "%~dp0executar_coleta_uf.bat" MT %*
set "CODIGO=%ERRORLEVEL%"
exit /b %CODIGO%
