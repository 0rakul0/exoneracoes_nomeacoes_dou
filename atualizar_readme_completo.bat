@echo off
setlocal

cd /d "%~dp0"

echo [1/3] Gerando movimentacoes...
call "%~dp0gerar_movimento.bat"
if errorlevel 1 goto erro

echo.
echo [2/3] Gerando imagens do README...
".\.venv\Scripts\python.exe" docs\gerar_imagens_readme.py --somente-imagens
if errorlevel 1 goto erro

echo.
echo [3/3] Atualizando README...
".\.venv\Scripts\python.exe" docs\gerar_imagens_readme.py --somente-readme
if errorlevel 1 goto erro

echo.
echo README atualizado com sucesso.
exit /b 0

echo.
echo começando a extração sucesso.
cd /d "%~dp0"
".\.venv\Scripts\python.exe" main.py

:erro
echo.
echo Falha na atualizacao do README. Codigo: %ERRORLEVEL%
exit /b %ERRORLEVEL%
