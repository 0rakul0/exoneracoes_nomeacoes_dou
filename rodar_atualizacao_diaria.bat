@echo off
setlocal

set "MODO=INTERATIVO"
if /I "%~1"=="--agendado" set "MODO=AGENDADO"

cd /d "%~dp0"
set "LOG=%~dp0logs\atualizacao_diaria.log"

if not exist "%~dp0logs" mkdir "%~dp0logs"

echo.>> "%LOG%"
echo ==================================================>> "%LOG%"
echo Inicio: %DATE% %TIME% - Modo: %MODO%>> "%LOG%"

for /f %%D in ('powershell -NoProfile -Command "(Get-Date).DayOfWeek"') do set "DIA_SEMANA=%%D"
if /I "%DIA_SEMANA%"=="Saturday" (
    echo Fim de semana: nenhuma coleta sera executada.
    echo Fim de semana: nenhuma coleta sera executada.>> "%LOG%"
    echo Fim: %DATE% %TIME% - Codigo: 0>> "%LOG%"
    if not "%MODO%"=="AGENDADO" pause
    exit /b 0
)
if /I "%DIA_SEMANA%"=="Sunday" (
    echo Fim de semana: nenhuma coleta sera executada.
    echo Fim de semana: nenhuma coleta sera executada.>> "%LOG%"
    echo Fim: %DATE% %TIME% - Codigo: 0>> "%LOG%"
    if not "%MODO%"=="AGENDADO" pause
    exit /b 0
)

if "%MODO%"=="AGENDADO" (
    call "%~dp0atualizar_dados_readme_dashboard.bat" >> "%LOG%" 2>&1
) else (
    title Atualizacao diaria - Exoneracoes e Nomeacoes
    echo.
    echo A atualizacao sera exibida nesta janela.
    echo O inicio e o resultado tambem ficam em "%LOG%".
    echo Nao feche esta janela enquanto a coleta estiver em andamento.
    echo.
    call "%~dp0atualizar_dados_readme_dashboard.bat"
)
set "CODIGO=%ERRORLEVEL%"

echo Fim: %DATE% %TIME% - Codigo: %CODIGO%>> "%LOG%"

if not "%MODO%"=="AGENDADO" (
    echo.
    if "%CODIGO%"=="0" (
        echo Atualizacao concluida com sucesso.
    ) else (
        echo A atualizacao terminou com erro. Codigo: %CODIGO%
    )
    echo Log: "%LOG%"
    pause
)

exit /b %CODIGO%
