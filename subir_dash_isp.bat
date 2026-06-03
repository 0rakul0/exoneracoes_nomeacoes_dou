@echo off
setlocal

cd /d "%~dp0"
".\.venv\Scripts\python.exe" diarios_oficiais\dashboard\painel_normativas_isp.py
