@echo off
setlocal
cd /d "%~dp0"
title Diarios Oficiais - Download e Docling CPU
if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo ERRO: Python nao encontrado.
    pause
    exit /b 1
  )
  set "PYTHON_EXE=python"
)
echo Iniciando download e conversao em processos separados...
start "Download Diarios" /D "%CD%" "%PYTHON_EXE%" -u baixar_diarios_windows.py
start "Docling CPU" /D "%CD%" "%PYTHON_EXE%" -u converter_diarios_cpu.py
echo Duas janelas foram iniciadas. Para parar, use Ctrl+C em cada uma.
pause
