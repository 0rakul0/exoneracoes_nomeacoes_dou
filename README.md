# Exoneracoes e nomeacoes nos diarios oficiais

Este projeto busca criar uma base historica de atos de exoneracao e nomeacao publicados em diarios oficiais brasileiros. A primeira etapa foca no Governo do Estado do Rio de Janeiro, acompanhando o Diario Oficial do Estado do Rio de Janeiro (DOERJ/IOERJ) em ordem cronologica, da edicao online mais antiga disponivel no portal atual ate as publicacoes mais recentes.

## Objetivos

- Baixar e preservar as edicoes consultadas dos diarios oficiais em `LAKE/UF`.
- Converter os PDFs oficiais para Markdown com Docling, mantendo o Markdown como fonte preferencial de leitura quando ja existir.
- Identificar atos de `NOMEAR` e `EXONERAR`.
- Catalogar data, caderno, nome da pessoa, tipo do ato, cargo, orgao, trecho e URL de origem.
- Produzir CSVs auditaveis para analise jornalistica, historica e civica.
- Evoluir para outros estados mantendo a mesma estrutura de coleta e dados.

## Fonte inicial: Rio de Janeiro

A fonte inicial e o portal da Imprensa Oficial do Estado do Rio de Janeiro:

- Calendario de edicoes: <https://www.ioerj.com.br/portal/modules/conteudoonline/do_seleciona_data.php>
- O calendario online atual lista edicoes a partir de julho de 2005.
- O proprio portal informa atendimento separado para edicoes pre-2008, entao essas edicoes podem exigir outra estrategia de obtencao no futuro.

## Como usar

Instale as dependencias:

```powershell
python -m pip install -r requirements.txt
```

Liste as datas disponiveis no calendario da IOERJ:

```powershell
python -m diarios_oficiais.rj_ioerj --list-dates
```

Colete a primeira data disponivel, salvando os documentos em `LAKE/RJ`:

```powershell
python -m diarios_oficiais.rj_ioerj --limit 1
```

Colete um intervalo especifico:

```powershell
python -m diarios_oficiais.rj_ioerj --start 2005-07-01 --end 2005-07-31 --output data/processed/rj_2005_07.csv
```

Os PDFs e os Markdowns ficam em `LAKE/RJ/`. Se o Markdown de uma edicao ja existir, o coletor usa esse arquivo diretamente e nao baixa nem converte o PDF de novo. O CSV padrao fica em `data/processed/rj_movimentacoes.csv`.

## Estrutura do CSV

| Campo | Descricao |
| --- | --- |
| `estado` | Unidade federativa da fonte. |
| `diario` | Nome do diario oficial. |
| `data_publicacao` | Data da edicao. |
| `caderno` | Caderno/secao da edicao. |
| `tipo_ato` | `nomeacao` ou `exoneracao`. |
| `nome` | Nome extraido do ato. |
| `cargo` | Cargo ou funcao, quando detectado. |
| `orgao` | Orgao, quando detectado. |
| `trecho` | Trecho usado para justificar a extracao. |
| `fonte_url` | URL da pagina oficial consultada. |
| `arquivo_pdf` | Caminho do PDF preservado em cache. |
| `arquivo_markdown` | Caminho do Markdown gerado pelo Docling. |

## Observacoes

O parser atual e heuristico. Ele foi feito para iniciar a coleta com rastreabilidade, nao para prometer 100% de precisao. A validacao humana, amostragens e testes com diferentes anos/cadernos devem guiar os proximos ajustes.

Proximos passos naturais:

- Ampliar testes com edicoes recentes do Poder Executivo.
- Separar atos coletivos de atos individuais.
- Melhorar extracao de cargo e orgao.
- Registrar metricas por edicao, como total de atos encontrados e paginas processadas.
- Criar conectores equivalentes para outros estados.
