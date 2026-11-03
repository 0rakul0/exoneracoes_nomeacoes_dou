# Arquitetura nacional de extração

## Responsabilidades

1. **Coletores** (`diarios_oficiais/estadual/`, `municipal/`): descobrem
   edições, preservam metadados, baixam documentos e os convertem para Markdown.
2. **Parser nacional** (`diarios_oficiais/extracao/parser.py`): identifica atos
   e extrai nomes, cargos, órgãos, assinantes e trechos. O código foi movido do
   parser histórico do RJ sem alterar os padrões de correspondência.
3. **Engine** (`diarios_oficiais/extracao/engine.py`): oferece API uniforme de
   extração, recebendo um perfil com as regras da fonte.
4. **Regras** (`diarios_oficiais/utils_regex/`): diferenças de linguagem ou
   estrutura permanecem por diário e podem ser aprimoradas isoladamente.
5. **Tratamento e análise**: preservados os contratos de `Act`, CSV e Parquet.

## Migração e compatibilidade

Todos os coletores estaduais e municipais que usavam a função `parse_acts`
do módulo RJ passam a utilizar a engine. `rj_ioerj.py` mantém as antigas
funções como reexportações de compatibilidade, mas não contém mais o parser.

O extrator especializado de Minas Gerais continua com sua implementação
específica; suas funções auxiliares de normalização apontam para a camada
compartilhada. Esse extrator pode ser migrado para um perfil próprio em uma
próxima etapa sem perder os padrões específicos de MG.

Coletores com regras especiais (Judiciário, Legislativo, municípios)
continuam passando suas expressões regulares explicitamente, quando aplicável.

## Exemplo

```python
from pathlib import Path
from diarios_oficiais.extracao.engine import ExtractionProfile, ExtractorEngine

engine = ExtractorEngine(ExtractionProfile(state="SP"))
atos = engine.extract_file(collector, edition, Path("edicao.md"))
```

## Verificação de regressão

```powershell
python -m unittest discover -s tests -v
```

Os testes de compatibilidade verificam a identidade dos símbolos reexportados
e a propagação das regras, e os testes estaduais existentes cobrem padrões
reais de edições dos estados. A migração preserva os CSVs já existentes e
**não reprocessa o LAKE automaticamente**.

## Limitações e próximos controles

- Sem uma base anotada por UF, não se deve afirmar uma precisão nacional.
- Verificar completude de publicações por fonte antes de usar marcadores
  históricos `.year_complete`.
- Medir precisão, revocação e F1 de ato e de cada campo para as fontes.
- Não fundir pessoas com mesmo nome sem evidência adicional.
- TLS de BA/RS foi reativado no commit anterior; cadeias inválidas exigem
  certificados confiáveis, nunca `verify=False`.
