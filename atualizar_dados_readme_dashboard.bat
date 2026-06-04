@echo off
setlocal

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "ORIGEM=%~dp0saida\analises\RJ"
set "DESTINO=D:\github\dash_temporal\saida\analises\RJ"

if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)

echo [1/6] Baixando e atualizando dados...
"%PYTHON%" main.py
if errorlevel 1 goto erro

echo.
echo [2/6] Deduplicando CSVs anuais...
"%PYTHON%" diarios_oficiais\tratamentos\deduplicar_atos_anuais.py --uf RJ
if errorlevel 1 goto erro

echo.
echo [3/6] Gerando movimentacoes...
"%PYTHON%" analise_temporal\analisar_movimentacoes.py --uf RJ --incluir-anos-incompletos --incremental
if errorlevel 1 goto erro

echo.
echo [4/6] Gerando imagens do README...
"%PYTHON%" docs\gerar_imagens_readme.py --somente-imagens
if errorlevel 1 goto erro

echo.
echo [5/6] Atualizando README...
"%PYTHON%" docs\gerar_imagens_readme.py --somente-readme
if errorlevel 1 goto erro

echo.
echo [6/6] Copiando dados para o dashboard temporal...
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
echo README atualizado com sucesso.
echo Dados atualizados em "%DESTINO%".
echo Revise, commite e envie o repositorio D:\github\dash_temporal para atualizar o Render.
exit /b 0

:erro
echo.
echo Falha na atualizacao. Codigo: %ERRORLEVEL%
exit /b %ERRORLEVEL%
