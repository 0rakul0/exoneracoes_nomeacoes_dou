@echo off
call "%~dp0rodar_atualizacao_diaria.bat" --agendado
exit /b %ERRORLEVEL%
