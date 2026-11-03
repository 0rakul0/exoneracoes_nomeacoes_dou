# Lancadores Windows (.bat)

Os 27 arquivos `coletar_UF_retroativo.bat` chamam
`executar_coleta_uf.bat`, transmitindo a UF pela variavel local
`DOU_UF` e os argumentos opcionais pela linha de comando. O executor
usa a `.venv`, executa `main.py` e repassa o codigo de saida.

```cmd
coletar_sp_retroativo.bat
coletar_mg_retroativo.bat --mg-data-inicial 2026-01-01 --mg-data-final 2026-10-31
coletar_pe_retroativo.bat
coletar_retroativos.bat 3600
extrai.bat
```

Os scripts ativam `--ignorar-year-complete`, evitando confiar em
marcadores historicos sem auditoria. Isso pode tornar a coleta demorada.
O `coletar_retroativos.bat` continua executando rodadas em loop.
O `extrai.bat` usa a coleta padrao; a coleta municipal do RJ continua
desativada no `main.py` e nao e invocada por esse lancador.

Os scripts de agendamento, atualizacao do README, dashboard e deploy
nao foram mudados. O processamento analitico diario ainda foca RJ/SP.

Esta padronizacao dos lancadores nao substitui testes funcionais nos
portais reais. Execute `python -m unittest discover -s tests -v`
na `.venv` e teste os retroativos no Windows.
