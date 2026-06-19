@echo off
setlocal

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "ORIGEM=%~dp0saida\analises\RJ"
set "REPO_ORIGEM=%~dp0"
set "REPO_DASH=D:\github\dash_temporal"
set "DESTINO=%REPO_DASH%\saida\analises\RJ"
set "MENSAGEM_COMMIT=Atualiza dados e README RJ"
set "AVISOS=0"

if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)

echo [1/8] Baixando e atualizando dados...
"%PYTHON%" main.py
if errorlevel 1 goto erro

echo.
echo [2/8] Deduplicando CSVs anuais...
"%PYTHON%" diarios_oficiais\tratamentos\deduplicar_atos_anuais.py --uf RJ
if errorlevel 1 goto erro

echo.
echo [3/8] Gerando movimentacoes...
"%PYTHON%" analise_temporal\analisar_movimentacoes.py --uf RJ --incluir-anos-incompletos --incremental
if errorlevel 1 goto erro

echo.
echo [4/8] Copiando dados para o dashboard temporal...
if not exist "%ORIGEM%\movimentacoes_pessoas.parquet" (
    echo Arquivo nao encontrado: "%ORIGEM%\movimentacoes_pessoas.parquet"
    exit /b 1
)

if not exist "%ORIGEM%\retornos_apos_exoneracao.csv" (
    echo Arquivo nao encontrado: "%ORIGEM%\retornos_apos_exoneracao.csv"
    exit /b 1
)

if not exist "%DESTINO%" (
    mkdir "%DESTINO%"
    if errorlevel 1 goto erro
)

copy /Y "%ORIGEM%\movimentacoes_pessoas.parquet" "%DESTINO%\movimentacoes_pessoas.parquet"
if errorlevel 1 goto erro

copy /Y "%ORIGEM%\retornos_apos_exoneracao.csv" "%DESTINO%\retornos_apos_exoneracao.csv"
if errorlevel 1 goto erro

echo.
echo [5/8] Commitando e enviando primeiro o dashboard temporal...
call :commit_e_push "%REPO_DASH%" "%MENSAGEM_COMMIT%"
if errorlevel 1 goto erro

echo.
echo [6/8] Gerando imagens do README (etapa opcional)...
"%PYTHON%" docs\gerar_imagens_readme.py --somente-imagens
if errorlevel 1 (
    echo AVISO: nao foi possivel gerar as imagens do README.
    echo AVISO: os dados do dashboard ja foram atualizados e enviados.
    set "AVISOS=1"
)

echo.
echo [7/8] Atualizando README (etapa opcional)...
"%PYTHON%" docs\gerar_imagens_readme.py --somente-readme
if errorlevel 1 (
    echo AVISO: nao foi possivel atualizar o README.
    echo AVISO: os dados do dashboard ja foram atualizados e enviados.
    set "AVISOS=1"
)

echo.
echo [8/8] Commitando e enviando o repositorio principal...
call :commit_e_push "%REPO_ORIGEM%" "%MENSAGEM_COMMIT%"
if errorlevel 1 goto erro

echo.
echo Dados atualizados em "%DESTINO%".
echo Repositorios commitados e enviados para o GitHub.
if "%AVISOS%"=="1" (
    echo Atualizacao concluida com avisos nas etapas opcionais de README/imagens.
) else (
    echo README e imagens atualizados com sucesso.
)
exit /b 0

:commit_e_push
set "REPO=%~1"
set "MSG=%~2"

if not exist "%REPO%\.git" (
    echo Repositorio Git nao encontrado: "%REPO%"
    exit /b 1
)

echo.
echo Atualizando Git em "%REPO%"...
git -C "%REPO%" status --porcelain > "%TEMP%\git_status_atualizacao.txt"
if errorlevel 1 exit /b 1

for %%A in ("%TEMP%\git_status_atualizacao.txt") do if %%~zA==0 (
    echo Nenhuma alteracao para commitar em "%REPO%".
    del "%TEMP%\git_status_atualizacao.txt" >nul 2>nul
    exit /b 0
)

del "%TEMP%\git_status_atualizacao.txt" >nul 2>nul

git -C "%REPO%" add -A
if errorlevel 1 exit /b 1

git -C "%REPO%" commit -m "%MSG%"
if errorlevel 1 exit /b 1

git -C "%REPO%" push
if errorlevel 1 exit /b 1

exit /b 0

:erro
set "CODIGO_ERRO=%ERRORLEVEL%"
echo.
echo Falha na atualizacao. Codigo: %CODIGO_ERRO%
exit /b %CODIGO_ERRO%
