@echo off
setlocal

cd /d "%~dp0"

echo Coleta retroativa dos diarios estaduais em rodizio...
echo Ordem do rodizio: RJ, SP, ES, BA, SC, PR, RS, PB, AC e CE.
echo A cada rodada e processado um caderno de cada estado.
call "%~dp0\.venv\Scripts\python.exe" "%~dp0main.py" --estaduais-rodizio-retroativo --ignorar-year-complete
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de MG...
call "%~dp0coletar_mg_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de MT...
call "%~dp0coletar_mt_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de MS...
call "%~dp0coletar_ms_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de AM...
call "%~dp0coletar_am_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de DF...
call "%~dp0coletar_df_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de GO...
call "%~dp0coletar_go_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de AL...
call "%~dp0coletar_al_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de AP...
call "%~dp0coletar_ap_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de MA...
call "%~dp0coletar_ma_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de PA...
call "%~dp0coletar_pa_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de PE...
call "%~dp0coletar_pe_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Coleta retroativa especifica de PI...
call "%~dp0coletar_pi_retroativo.bat"
if errorlevel 1 goto erro

echo.
echo Todas as coletas retroativas foram concluidas.
exit /b 0

:erro
set "CODIGO=%ERRORLEVEL%"
echo.
echo A coleta retroativa terminou com erro. Codigo: %CODIGO%
exit /b %CODIGO%
