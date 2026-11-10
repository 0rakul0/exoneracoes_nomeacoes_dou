# Download continuo de diarios no Windows sem GPU

Execute **iniciar_download_diarios.bat** com dois cliques. O script chama
`baixar_diarios_windows.py` sem argumentos. Para executar pelo Python:
`python baixar_diarios_windows.py`.

## Comportamento
- Primeiro consulta **hoje em todas as 27 UFs**, depois ontem e anteontem.\n- Em seguida baixa retroativamente todas as edicoes historicas, na ordem de data mais recente para mais antiga, alternando fontes conforme a disponibilidade.\n- Durante a fase historica, reconsulta os tres dias recentes a cada 60 minutos, inclusive se a rodada durar dias.\n- Pula PDFs persistidos e validos; retenta arquivos ausentes ou incompletos.
- Salva os PDFs oficiais permanentemente em `LAKE/UF/AAAA/MM/nome.pdf`,
  ao lado do futuro arquivo Markdown da edicao.
- Reaproveita PDFs existentes com cabecalho valido; baixa novamente arquivos
  ausentes/incompletos.
- O DOE-BA exige autenticacao para PDF certificado: baixa o HTML publico e
  salva seu conteudo em Markdown usando o proprio coletor, sem Docling/OCR.
- Nao extrai atos nem gera CSVs nesta etapa.
- Registra progresso em `logs/download_diarios.log`, alem dos arquivos
  de falhas ja mantidos pelos coletores.
- Reexecuta nova rodada seis horas **depois de terminar** a anterior.\n- Edite `INTERVALO_ATUALIZACAO_RECENTES_MINUTOS`, `QUANTIDADE_DIAS_RECENTES` e `VERIFICAR_RECENTES_A_CADA_EDICOES` para ajustar a prioridade do acervo recente.

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
