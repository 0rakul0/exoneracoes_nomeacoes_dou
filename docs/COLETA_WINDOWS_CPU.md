# Coleta continua + conversao Docling CPU (Windows, sem args)

## Inicio rapido

1. Atualize a branch main: `git pull origin main`.
2. Instale as dependencias Python do projeto em um `.venv`.
3. Abra `iniciar_coletas_windows.bat` com dois cliques.
4. O .bat abre **dois processos**: download e conversao/extracao.
5. Para encerrar, Ctrl+C em cada janela.

Os scripts individuais continuam disponiveis:
- `iniciar_download_diarios.bat`: apenas baixar.
- `python converter_diarios_cpu.py`: apenas processar fila pendente.
- `python baixar_diarios_windows.py`: download sem args.

## Como funciona

`baixar_diarios_windows.py` consulta hoje, ontem e anteontem em todas
as UFs, depois percorre o historico em ordem decrescente. Durante o
historico, consulta novamente as datas recentes periodicamente.

Ao encontrar PDF oficial baixado ou ja existente, registra o arquivo na
fila SQLite `.cache/fila_diarios.sqlite3` (caminho, UF, codigo do
diario, data, caderno, URL). O PDF fica em
`LAKE/UF/AAAA/MM/*.pdf` para conversao posterior. No DOE/BA, a versao
publica HTML e salva em Markdown e enfileirada para extracao de atos.

`converter_diarios_cpu.py` abre a fila em processo separado. Converte
PDF para Markdown com Docling na **CPU** (OCR somente quando necessario,
conforme o codigo existente do coletor), grava no mesmo diretorio e
extrai nomeacoes/exoneracoes para os CSVs anuais em `saida/UF`.

O downloader **nao aguarda** a conversao. Se reiniciar, a fila
`processando` e recuperada; falhas recebem retentativas com intervalo
crescente. O sistema nao possui controlador de servico do Windows.
Nao inicie dois conversores simultaneamente.

## Configuracoes sem args

Edite as constantes no inicio dos arquivos:
- `baixar_diarios_windows.py`: intervalo de revisita aos dias recentes,
  intervalo de nova rodada, politica para PDFs ja armazenados.
- `converter_diarios_cpu.py`: `THREADS_DOCLING_CPU=6`,
  `EXTRAIR_ATOS_CSV=True`, intervalo quando a fila esta vazia.

Ajuste `THREADS_DOCLING_CPU` conforme numero de nucleos e RAM.
Apenas um worker de conversao e iniciado pelo .bat, para limitar a
concorrencia e evitar escrita simultanea nos CSVs.

## Logs, recuperacao e ressalvas

- `logs/download_diarios.log`
- `logs/conversao_diarios.log`
- `.cache/fila_diarios.sqlite3`
- `LAKE/UF/AAAA/falhas_coleta.csv` (quando o coletor registrar falhas)

Nenhum comando usa argparse. Mantenha o Windows sem suspensao,
espaco em disco suficiente e as janelas abertas.

**Dependencias:** Docling, torch CPU, pypdf e demais bibliotecas do
projeto precisam estar instalados no ambiente. O `requirements.txt`
principal aponta para o indice CUDA 11.8 do PyTorch: nao use essa
instalacao como recomendacao automatica para servidor sem GPU.
Prefira um ambiente CPU dedicado com rodas PyTorch CPU compativeis
com a versao de Python instalada.

**Limitacoes:** nao houve teste de ponta a ponta em todos os portais.
Alguns coletores podem ter comportamento especifico para HTML,
autenticacao, PDF e OCR. O download valida cabecalho PDF, nao faz
validacao criptografica integral. O Markdown pode ser reutilizado
caso ja exista, sem reconversao automatica.

O conversor processa os PDFs registrados na fila. Arquivos PDF antigos
que ja existam em LAKE mas nunca sejam encontrados pelo catalogo
precisam de importacao separada para entrar na fila.

## Falha de uma UF

O downloader faz somente uma tentativa por arquivo (timeout configurado em 15 segundos). Se houver falha, registra o erro e coloca a UF em pausa por 30 minutos, seguindo para outra UF sem travar o rodizio. Durante essa pausa, edicoes da UF sao puladas e serao verificadas novamente em uma rodada futura; a fila SQLite preserva os downloads ja concluidos. Esses ajustes ficam nas constantes de `baixar_diarios_windows.py`.
