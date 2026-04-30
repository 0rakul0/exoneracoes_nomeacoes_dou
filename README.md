# Exoneracoes e nomeacoes nos diarios oficiais

Este projeto busca criar uma base historica de atos de exoneracao e nomeacao publicados em diarios oficiais brasileiros. A primeira etapa foca no Governo do Estado do Rio de Janeiro, acompanhando o Diario Oficial do Estado do Rio de Janeiro (DOERJ/IOERJ) da edicao online mais recente disponivel no portal atual para as mais antigas.

## Objetivos

- Converter as edicoes oficiais para Markdown com Docling e preservar somente o `.md` em `LAKE/UF`.
- Identificar atos de `NOMEAR` e `EXONERAR`.
- Catalogar data, caderno, nome da pessoa, tipo do ato, cargo, orgao, trecho e URL de origem.
- Produzir CSVs anuais auditaveis para analise jornalistica, historica e civica.
- Evoluir para outros estados mantendo a mesma estrutura de coleta e dados.

## Fonte inicial: Rio de Janeiro

A fonte inicial e o portal da Imprensa Oficial do Estado do Rio de Janeiro:

- Calendario de edicoes: <https://www.ioerj.com.br/portal/modules/conteudoonline/do_seleciona_data.php>
- O calendario online atual lista edicoes a partir de julho de 2005.
- O proprio portal informa atendimento separado para edicoes pre-2008, entao essas edicoes podem exigir outra estrategia de obtencao no futuro.

## Como usar

Instale as dependencias:

```powershell
python -m pip install -r requirements-cuda.txt
python -m pip install -r requirements.txt
```

Rode o coletor:

```powershell
python main.py
```

O `main.py` nao recebe argumentos. A lista de UFs a coletar fica em `STATES_TO_COLLECT`, dentro do proprio arquivo. Para `RJ`, ele procura as datas da IOERJ da mais recente para a mais antiga e percorre as edicoes disponiveis do caderno de Poder Executivo. Para cada edicao, reutiliza o Markdown quando ele ja existe; quando precisa converter, reaproveita PDFs em `.cache/diarios` antes de baixar novamente. A analise temporal fica no script separado em `analise_temporal/analisar_movimentacoes.py`.

O padrao dos arquivos Markdown e:

```text
LAKE/UF/ano/mes/<sigla>_<caderno>_<data>.md
```

Exemplo:

```text
LAKE/RJ/2026/04/DOERJ_PARTE_I_PODER_EXECUTIVO_2026-04-29.md
```

O CSV consolidado por ano fica em:

```text
saida/UF/<sigla>_<ano>.csv
```

Exemplo:

```text
saida/RJ/DOERJ_2026.csv
```

Se o `.md` da edicao ja existir no repositorio, o coletor usa esse arquivo diretamente e nao baixa nem converte o PDF de novo. O CSV anual e atualizado em `saida/RJ`, sem duplicar atos ja gravados.

Durante a gravacao do CSV anual, o coletor pode usar spaCy para validar se o nome extraido parece uma pessoa. Esses campos sao gravados junto do ato:

```text
spacy_pessoa
spacy_entidades
nome_parse_confiavel
```

As chaves ficam em `diarios_oficiais/config.py`: `ENABLE_SPACY_VALIDATION`, `SPACY_MODEL` e `SPACY_MODE`. O modo padrao e `annotate`, que apenas anota a validacao sem bloquear a coleta.

Por padrao, o Docling usa o texto embutido no PDF, sem OCR, para manter a coleta mais rapida. Para edicoes escaneadas, altere a constante `ENABLE_OCR` em `diarios_oficiais/config.py`.

As configuracoes compartilhadas de coleta, cache, saida, Docling e parse em blocos ficam em `diarios_oficiais/config.py`. A classe base para novos extratores fica em `diarios_oficiais/base.py`.

## Fluxo

```mermaid
flowchart TD
    A["python main.py"] --> B["main.py percorre STATES_TO_COLLECT"]
    B --> C["Reporta PyTorch/CUDA disponivel"]
    C --> D["Busca calendario da IOERJ"]
    D --> E["Ordena datas do DOERJ do mais recente ao mais antigo"]
    E --> F["Para cada data, lista cadernos publicados"]
    F --> G["Filtra caderno: Poder Executivo"]
    G --> H{"Markdown da edicao ja existe em LAKE/RJ/ano/mes?"}
    H -- "Sim" --> I["Usa Markdown existente"]
    H -- "Nao" --> J["Reaproveita ou baixa PDF oficial em .cache/diarios"]
    J --> K["Converte PDF para Markdown"]
    K --> L["Salva o .md em LAKE/RJ/ano/mes"]
    L --> M["Mantem PDF em cache"]
    I --> N["Parser procura atos NOMEAR e EXONERAR no Markdown"]
    M --> N
    N --> O["Atualiza CSV anual em saida/RJ"]
    O --> P{"Ainda ha datas no calendario?"}
    P -- "Sim" --> F
    P -- "Nao" --> Q["Percorre UFs em saida"]
    Q --> R["Gera analises temporais em saida/analises/UF"]
```

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
| `arquivo_markdown` | Caminho do Markdown gerado pelo Docling. |

## Analises temporais

Para gerar uma serie temporal por pessoa e identificar retornos apos exoneracao:

```powershell
python analise_temporal/analisar_movimentacoes.py
```

O script de analise temporal e independente do `main.py`. O ano corrente entra sempre, mesmo ainda em andamento. Anos anteriores so entram quando o coletor termina todos os `.md` daquele ano e cria o marcador:

```text
LAKE/RJ/<ano>/.year_complete
```

Por exemplo, durante 2026: `DOERJ_2026.csv` entra; `DOERJ_2025.csv` entra se tiver o marcador; `DOERJ_2024.csv` fica fora enquanto o ano nao tiver sido totalmente baixado/processado.

Ao rodar o script diretamente, ele abre um menu:

```text
1. Gerar analise para anos prontos
2. Gerar analise incluindo anos incompletos
3. Escolher UF e ano
4. Sair
```

Use esse menu para regerar todas as analises, incluir anos incompletos ou escolher uma UF/ano especifico.

Nesse modo, a saida fica em:

```text
saida/analises/RJ/movimentacoes_pessoas.csv
saida/analises/RJ/retornos_apos_exoneracao.csv
saida/analises/RJ/resumo_pessoas.csv
saida/analises/RJ/nomes_suspeitos.csv
```

Por padrao, o script usa spaCy para validar nomes de pessoas quando o modelo estiver instalado. Para preparar o ambiente:

```powershell
python -m pip install -r requirements.txt
python -m spacy download pt_core_news_sm
```

Se quiser rodar sem spaCy:

```powershell
python analise_temporal/analisar_movimentacoes.py --uf RJ --sem-spacy
```

O script le os CSVs anuais em `saida/UF` e grava:

```text
saida/analises/movimentacoes_pessoas.csv
saida/analises/retornos_apos_exoneracao.csv
saida/analises/resumo_pessoas.csv
saida/analises/nomes_suspeitos.csv
```

Para marcar mudancas de governo ou outros marcos politicos na serie temporal:

```powershell
python analise_temporal/analisar_movimentacoes.py --uf RJ --marco-governo 2023-01-01:Governo_2023
```

## Observacoes

O parser atual e heuristico. Ele foi feito para iniciar a coleta com rastreabilidade, nao para prometer 100% de precisao. A validacao humana, amostragens e testes com diferentes anos/cadernos devem guiar os proximos ajustes.

Proximos passos naturais:

- Ampliar testes com edicoes recentes do Poder Executivo.
- Separar atos coletivos de atos individuais.
- Melhorar extracao de cargo e orgao.
- Registrar metricas por edicao, como total de atos encontrados e paginas processadas.
- Criar conectores equivalentes para outros estados.
