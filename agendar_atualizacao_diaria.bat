@echo off
setlocal

set "TAREFA=Atualizar DOU RJ e Dashboard"
set "SCRIPT=%~dp0rodar_atualizacao_diaria.bat"

if not exist "%SCRIPT%" (
    echo Script nao encontrado: "%SCRIPT%"
    exit /b 1
)

schtasks /Create /TN "%TAREFA%" /TR "%SCRIPT%" /SC DAILY /ST 09:00 /F
if errorlevel 1 (
    echo.
    echo Nao foi possivel criar a tarefa agendada.
    echo Tente executar este arquivo como Administrador.
    exit /b 1
)

echo.
echo Tarefa "%TAREFA%" criada para rodar todos os dias as 09:00.
echo Log: "%~dp0logs\atualizacao_diaria.log"
exit /b 0
