@echo off
setlocal

cd /d "%~dp0"
".\.venv\Scripts\python.exe" docs\gerar_imagens_readme.py

echo.
echo Imagens e README atualizados. Pressione qualquer tecla para fechar.
pause >nul
