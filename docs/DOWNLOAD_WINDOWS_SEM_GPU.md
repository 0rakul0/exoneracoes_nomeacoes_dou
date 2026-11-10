# Download continuo de diarios no Windows sem GPU

Execute **iniciar_download_diarios.bat** com dois cliques. O script chama
`baixar_diarios_windows.py` sem argumentos. Para executar pelo Python:
`python baixar_diarios_windows.py`.

## Comportamento
- Coleta retroativa em rodizio entre as 27 UFs.
- Salva os PDFs oficiais permanentemente em `LAKE/UF/AAAA/MM/nome.pdf`,
  ao lado do futuro arquivo Markdown da edicao.
- Reaproveita PDFs existentes com cabecalho valido; baixa novamente arquivos
  ausentes/incompletos.
- O DOE-BA exige autenticacao para PDF certificado: baixa o HTML publico e
  salva seu conteudo em Markdown usando o proprio coletor, sem Docling/OCR.
- Nao extrai atos nem gera CSVs nesta etapa.
- Registra progresso em `logs/download_diarios.log`, alem dos arquivos
  de falhas ja mantidos pelos coletores.
- Reexecuta nova rodada seis horas **depois de terminar** a anterior.

## Configuracao
Ajuste as constantes no inicio de `baixar_diarios_windows.py`.
`PULAR_ANOS_COMPLETOS = False` e importante: os marcadores existentes
referem-se ao processamento e nao garantem que um PDF foi salvo.

**Observacao:** algumas fontes so disponibilizam HTML ou podem sofrer
mudancas/bloqueios. O script registra esses erros e continua. O script
nao usa GPU, mas imports dos coletores podem exigir dependencias
presentes no `requirements.txt` original, inclusive PyTorch/Docling.
Sem instalar essas dependencias, use o ambiente ja configurado do projeto.

Mantenha o PC ligado, evite suspensao e nao inicie duas instancias
apontando para o mesmo LAKE. Para parar, pressione Ctrl+C.
