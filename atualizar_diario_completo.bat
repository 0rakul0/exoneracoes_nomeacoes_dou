@echo off
setlocal

cd /d "%~dp0"

echo [1/5] Coletando edicoes novas do RJ...
".\.venv\Scripts\python.exe" -c "import main; raise SystemExit(main.main())"
if errorlevel 1 goto erro

echo.
echo [2/5] Gerando movimentacoes...
call "%~dp0gerar_movimento.bat"
if errorlevel 1 goto erro

echo.
echo [3/5] Exportando HTML...
".\.venv\Scripts\python.exe" analise_temporal\exportar_html.py
if errorlevel 1 goto erro

echo.
echo [4/5] Gerando imagens do README...
".\.venv\Scripts\python.exe" docs\gerar_imagens_readme.py --somente-imagens
if errorlevel 1 goto erro

echo.
echo [5/5] Atualizando README...
".\.venv\Scripts\python.exe" docs\gerar_imagens_readme.py --somente-readme
if errorlevel 1 goto erro

echo.
echo Rotina diaria concluida com sucesso.
exit /b 0

:erro
echo.
echo Falha na rotina diaria. Codigo: %ERRORLEVEL%
exit /b %ERRORLEVEL%
