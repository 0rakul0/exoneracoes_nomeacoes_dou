@echo off
setlocal

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "REPO_ORIGEM=%~dp0"
set "MENSAGEM_COMMIT=Atualiza dados e README RJ"
set "AVISOS=0"

if not exist "%PYTHON%" (
    echo Python da .venv nao encontrado: %PYTHON%
    exit /b 1
)

echo [1/7] Baixando e atualizando dados...
"%PYTHON%" main.py
if errorlevel 1 goto erro

echo.
echo [2/7] Deduplicando CSVs anuais...
"%PYTHON%" diarios_oficiais\tratamentos\deduplicar_atos_anuais.py --uf RJ
if errorlevel 1 goto erro

echo.
echo [3/7] Gerando movimentacoes...
"%PYTHON%" analise_temporal\analisar_movimentacoes.py --uf RJ --incluir-anos-incompletos --incremental
if errorlevel 1 goto erro

echo.
echo [4/7] Consolidando dados...
"%PYTHON%" scripts\consolidar_dados.py
if errorlevel 1 goto erro

echo.
echo [5/7] Gerando imagens do README (etapa opcional)...
"%PYTHON%" docs\gerar_imagens_readme.py --somente-imagens
if errorlevel 1 (
    echo AVISO: nao foi possivel gerar as imagens do README.
    echo AVISO: o consolidado foi gerado, mas as imagens do README falharam.
    set "AVISOS=1"
)

echo.
echo [6/7] Atualizando README (etapa opcional)...
"%PYTHON%" docs\gerar_imagens_readme.py --somente-readme
if errorlevel 1 (
    echo AVISO: nao foi possivel atualizar o README.
    echo AVISO: o consolidado foi gerado, mas o README falhou.
    set "AVISOS=1"
)

echo.
echo [7/7] Commitando e enviando o repositorio principal...
pushd "%REPO_ORIGEM%"
if errorlevel 1 goto erro
echo.
echo Atualizando Git em "%REPO_ORIGEM%"...
git status --porcelain > "%TEMP%\git_status_atualizacao.txt"
if errorlevel 1 popd & goto erro
for %%A in ("%TEMP%\git_status_atualizacao.txt") do set TAMANHO=%%~zA
if "%TAMANHO%"=="0" (
    echo Nenhuma alteracao para commitar em "%REPO_ORIGEM%".
    del "%TEMP%\git_status_atualizacao.txt" >nul 2>nul
    popd
) else (
    del "%TEMP%\git_status_atualizacao.txt" >nul 2>nul
    git add -A
    if errorlevel 1 popd & goto erro
    git commit -m "%MENSAGEM_COMMIT%"
    if errorlevel 1 popd & goto erro
    git push
    if errorlevel 1 popd & goto erro
    popd
)

echo.
echo Dados e consolidado atualizados no repositorio principal.
echo O envio do dash_temporal fica para a tarefa dedicada das 10h.
if "%AVISOS%"=="1" (
    echo Atualizacao concluida com avisos nas etapas opcionais de README/imagens.
) else (
    echo README e imagens atualizados com sucesso.
)
exit /b 0

:erro
set "CODIGO_ERRO=%ERRORLEVEL%"
echo.
echo Falha na atualizacao. Codigo: %CODIGO_ERRO%
exit /b %CODIGO_ERRO%
