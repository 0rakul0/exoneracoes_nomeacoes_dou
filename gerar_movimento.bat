@echo off
setlocal

cd /d "%~dp0"
".\.venv\Scripts\python.exe" analise_temporal\analisar_movimentacoes.py --uf RJ --incluir-anos-incompletos %*
