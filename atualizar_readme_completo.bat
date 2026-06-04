@echo off
setlocal

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)

echo [1/4] Deduplicando CSVs anuais...
"%PYTHON%" diarios_oficiais\tratamentos\deduplicar_atos_anuais.py --uf RJ
if errorlevel 1 goto erro

echo.
echo [2/4] Gerando movimentacoes...
"%PYTHON%" analise_temporal\analisar_movimentacoes.py --uf RJ --incluir-anos-incompletos --incremental
if errorlevel 1 goto erro

echo.
echo [3/4] Gerando imagens do README...
"%PYTHON%" docs\gerar_imagens_readme.py --somente-imagens
if errorlevel 1 goto erro

echo.
echo [4/4] Atualizando README...
"%PYTHON%" docs\gerar_imagens_readme.py --somente-readme
if errorlevel 1 goto erro

echo.
echo README atualizado com sucesso.
exit /b 0

:erro
echo.
echo Falha na atualizacao do README. Codigo: %ERRORLEVEL%
exit /b %ERRORLEVEL%
