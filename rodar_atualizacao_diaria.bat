@echo off
setlocal

cd /d "%~dp0"

if not exist "%~dp0logs" mkdir "%~dp0logs"

echo.>> "%~dp0logs\atualizacao_diaria.log"
echo ==================================================>> "%~dp0logs\atualizacao_diaria.log"
echo Inicio: %DATE% %TIME%>> "%~dp0logs\atualizacao_diaria.log"

call "%~dp0atualizar_dados_readme_dashboard.bat" >> "%~dp0logs\atualizacao_diaria.log" 2>&1
set "CODIGO=%ERRORLEVEL%"

echo Fim: %DATE% %TIME% - Codigo: %CODIGO%>> "%~dp0logs\atualizacao_diaria.log"

exit /b %CODIGO%
