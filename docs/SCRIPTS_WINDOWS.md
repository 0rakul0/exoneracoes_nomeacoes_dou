# Lancadores Windows (.bat)

Os 27 scripts `coletar_UF_retroativo.bat` sao wrappers de
`executar_coleta_uf.bat`, que executa o `main.py` na `.venv` do projeto.
As regras estaduais e o motor compartilhado sao importados pelo Python;
o .bat **nao** chama os arquivos individuais de regex nem o parser do RJ.

Exemplos:

```cmd
coletar_sp_retroativo.bat
coletar_mg_retroativo.bat --mg-data-inicial 2026-01-01 --mg-data-final 2026-10-31
coletar_pe_retroativo.bat
coletar_retroativos.bat 3600
extrai.bat
```

Os scripts repassam argumentos adicionais ao `main.py` e retornam o codigo de
saida do Python. Todos usam `.venv\Scripts\python.exe` e solicitam
`--ignorar-year-complete` para nao confiar cegamente nos marcadores
historicos; isso pode aumentar bastante o tempo de coleta.

O `coletar_retroativos.bat` permanece em rodizio continuo. O `extrai.bat`
usa a rotina padrao do `main.py` e nao executa a coleta municipal do RJ,
pois os respectivos blocos estao comentados no Python.

**Nao alterados nesta migracao:** scripts de agendamento, atualizacao do
README/dados, deploy do dashboard e `subir_dash.bat`. O fluxo diario de
analise ainda enfatiza RJ/SP e nao deve ser confundido com uma consolidacao
automaticamente validada de todas as 27 UFs.

Validacao funcional requer executar cada portal no Windows. A padronizacao
do comando nao garante disponibilidade dos sites ou qualidade dos extratores.
