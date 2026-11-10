@echo off
setlocal
cd /d "%~dp0"
title Coleta de Diarios Oficiais - Rodizio Estadual

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERRO: Python nao encontrado. Crie o .venv ou instale Python.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=python"
)

echo Iniciando coleta estadual continua...
echo Para parar: Ctrl+C
"%PYTHON_EXE%" -u coletar_continuamente.py
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo Coleta encerrada com codigo %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
