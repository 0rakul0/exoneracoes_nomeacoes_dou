@echo off
setlocal

set "MODO=INTERATIVO"
if /I "%~1"=="--agendado" set "MODO=AGENDADO"

cd /d "%~dp0"

if not exist "%~dp0logs" mkdir "%~dp0logs"

echo.>> "%~dp0logs\atualizacao_diaria.log"
echo ==================================================>> "%~dp0logs\atualizacao_diaria.log"
echo Inicio: %DATE% %TIME%>> "%~dp0logs\atualizacao_diaria.log"

if "%MODO%"=="AGENDADO" (
    call "%~dp0atualizar_dados_readme_dashboard.bat" >> "%~dp0logs\atualizacao_diaria.log" 2>&1
) else (
    title Atualizacao diaria - Exoneracoes e Nomeacoes
    echo.
    echo A atualizacao sera exibida nesta janela.
    echo O inicio e o resultado tambem ficam em "%~dp0logs\atualizacao_diaria.log".
    echo Nao feche esta janela enquanto a coleta estiver em andamento.
    echo.
    call "%~dp0atualizar_dados_readme_dashboard.bat"
)
set "CODIGO=%ERRORLEVEL%"

echo Fim: %DATE% %TIME% - Codigo: %CODIGO%>> "%~dp0logs\atualizacao_diaria.log"

if not "%MODO%"=="AGENDADO" (
    echo.
    if "%CODIGO%"=="0" (
        echo Atualizacao concluida com sucesso.
    ) else (
        echo A atualizacao terminou com erro. Codigo: %CODIGO%
    )
    echo Log: "%~dp0logs\atualizacao_diaria.log"
    pause
)

exit /b %CODIGO%
