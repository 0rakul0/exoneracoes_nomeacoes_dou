@echo off
setlocal
cd /d "%~dp0"
title Download dos Diarios Oficiais - Windows CPU
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python nao encontrado. Instale Python e configure o ambiente.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=python"
)
echo Baixando diarios sem GPU e sem conversao OCR...
"%PYTHON_EXE%" -u baixar_diarios_windows.py
set "EXIT_CODE=%ERRORLEVEL%"
echo Processo encerrado com codigo %EXIT_CODE%
pause
exit /b %EXIT_CODE%
