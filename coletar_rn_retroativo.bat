@echo off
setlocal EnableExtensions
call "%~dp0executar_coleta_uf.bat" RN %*
set "CODIGO=%ERRORLEVEL%"
exit /b %CODIGO%
