@echo off
setlocal

set "DASH_REPO=D:\github\dash_temporal"
set "SYNC_SCRIPT=%DASH_REPO%\atualizar_github.bat"

if not exist "%DASH_REPO%" (
    echo Repositorio do dash_temporal nao encontrado: "%DASH_REPO%"
    exit /b 1
)

if not exist "%SYNC_SCRIPT%" (
    echo Script de sincronizacao nao encontrado: "%SYNC_SCRIPT%"
    exit /b 1
)

echo Sincronizando saida\consolidado para "%DASH_REPO%"...
call "%SYNC_SCRIPT%"
exit /b %ERRORLEVEL%
