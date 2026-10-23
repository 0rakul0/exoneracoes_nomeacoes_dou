@echo off
setlocal

cd /d "%~dp0"

echo [1/10] Coleta retroativa do RJ...
call "%~dp0coletar_rj_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo [2/10] Coleta retroativa de SP...
call "%~dp0coletar_sp_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo [3/10] Coleta retroativa do ES...
call "%~dp0coletar_es_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo [4/10] Coleta retroativa da BA...
call "%~dp0coletar_ba_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo [5/10] Coleta retroativa de SC...
call "%~dp0coletar_sc_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo [6/10] Coleta retroativa do PR...
call "%~dp0coletar_pr_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo [7/10] Coleta retroativa do RS...
call "%~dp0coletar_rs_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo [8/10] Coleta retroativa da PB...
call "%~dp0coletar_pb_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo [9/10] Coleta retroativa do AC...
call "%~dp0coletar_ac_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo [10/10] Coleta retroativa do CE...
call "%~dp0coletar_ce_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Todas as coletas retroativas foram concluidas.
exit /b 0

:erro
set "CODIGO=%ERRORLEVEL%"
echo.
echo A coleta retroativa terminou com erro. Codigo: %CODIGO%
exit /b %CODIGO%
