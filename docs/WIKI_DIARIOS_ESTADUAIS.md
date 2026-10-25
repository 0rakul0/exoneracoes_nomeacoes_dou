# Wiki — Diários Oficiais Estaduais

## Visão geral

O projeto coleta atos de nomeação e exoneração publicados nos Diários Oficiais
estaduais. Cada edição é preservada como Markdown e os atos reconhecidos são
consolidados em CSV anual.

O fluxo padrão é:

1. O coletor consulta o catálogo, a página diária ou a URL oficial da edição.
2. A edição é baixada como PDF (ou HTML oficial quando a fonte não oferece PDF
   público, como parte do DOE/BA).
3. O arquivo é guardado temporariamente em `.cache/diarios`.
4. O texto é convertido para Markdown, com OCR de fallback quando configurado.
5. Os padrões de nomeação/exoneração da UF extraem os atos.
6. O Markdown fica em `LAKE/<UF>/<AAAA>/<MM>` e o CSV em `saida/<UF>`.

Os comandos abaixo são executados na raiz `G:\exoneracoes_nomeacoes_dou`:

```powershell
python main.py --coletar-<uf> --<uf>-data-inicial AAAA-MM-DD --<uf>-data-final AAAA-MM-DD
python main.py --<uf>-retroativo
.\coletar_<uf>_retroativo.bat
```

Substitua `<uf>` pela sigla em minúsculas. O modo retroativo começa na data
final atual e recua até `*_START_DATE` ou até a data inicial informada. Para
uma atualização normal, a coleta retoma pela última data encontrada em
`LAKE/<UF>`.

## Matriz de fontes e APIs

| UF | Diário/código | Fonte oficial | API pública usada? | Método de listagem/download |
|---|---|---|---|---|
| AC | DOE-AC `DOEAC` e DJE-AC `DJEAC` | [Diário do Acre](https://diario.ac.gov.br/) e [DJE TJAC](https://diario.tjac.jus.br/edicoes.php) | Parcial: não para o DOE/DJE | Formulário mensal do DOE e página de edições do DJE; PDFs oficiais |
| AL | DOE-AL `DOEAL` | [Imprensa Oficial de Alagoas](https://diario.imprensaoficial.al.gov.br/portal/) | Sim | API mensal `apinova/api/editions/published/AAAA/MM`; download por ID |
| AM | DOE-AM `DOEAM` | [Imprensa Oficial do Amazonas](https://diario.imprensaoficial.am.gov.br/) | Sim | Catálogo diário `edicoes_from_data/AAAA-MM-DD.json`; download por ID |
| AP | DOE-AP `DOEAP` | [DIOFE](https://diofe.portal.ap.gov.br/) | Sim | Catálogo diário; download por ID |
| BA | DOE-BA `DOBA`, DOEL-BA `DOELBA` e DJE-BA | [DOE-BA](https://doe.ba.gov.br/) e [EGBA/ALBA](https://egbanet.egba.ba.gov.br/alba/) | Sim para catálogos | API de edições; DOE usa conteúdo HTML público, DOEL/DJE usam arquivos oficiais |
| CE | DOE-CE `DOECE` | [Diário Oficial do Ceará](https://www.ce.gov.br/diario-oficial/) | Sim | API WordPress `search_portal`; exportação oficial de PDF |
| DF | DODF `DODF` | [Diário Oficial do DF](https://www.dodf.df.gov.br/) | Não | Página HTML diária estruturada com `lstLinkPdf`; baixa edição e extras |
| ES | DOE-ES `DOES` | [DIO-ES](https://ioes.dio.es.gov.br/) | Sim | Catálogo diário `edicoes_from_data`; download por ID |
| GO | DOE-GO `DOEG` | [Diário Oficial de Goiás](https://diariooficial.abc.go.gov.br/) | Sim | Catálogo diário; preserva edição principal e suplementos |
| MA | DOE-MA `DOEMA` | [Diário Oficial do Maranhão](https://www.diariooficial.ma.gov.br/) | Sim | API mensal por caderno; inclui Executivo, Judiciário, Terceiros, suplementos e extras |
| MG | Diário do Executivo `DOEMG` | [Jornal Minas Gerais](https://www.jornalminasgerais.mg.gov.br/) | Sim | API `api/v1`, calendário e edição por data; baixa cadernos por ID |
| MS | Diário Oficial `DOEMS` | [Diário Oficial de MS](https://www.diariooficial.ms.gov.br/) | Sim | API paginada por intervalo; baixa `caminhoArquivo` |
| MT | Diário Oficial `DOEMT` | [IOMAT](https://api.iomat.mt.gov.br/transparencia/swagger) | Sim | API REST por data; download por ID em PDF |
| PA | DOE-PA `DOEPA` | [IOEPA](https://www.ioepa.com.br/portal/) | Não | Sondagem direta de `pages/AAAA/AAAA.MM.DD.DOE.pdf` e `EXTRA.pdf` |
| PB | DOE-PB `DOEPB` e DJE-PB `DJEPB` | [A União](https://auniao.pb.gov.br/servicos/doe) e [DJE TJPB](https://app.tjpb.jus.br/dje/paginas/diario_justica/publico/buscas.jsf) | Não | Índice HTML mensal e URL oficial diária do DJE |
| PE | DOE-PE `DOEPE` | [CEPE — Diário Oficial](https://portal.cepe.com.br/diario-oficial) | Sim | API pública CEPE para metadados; arquivo no armazenamento oficial `cepebr-prod` |
| PI | DOE-PI `DOEPI` | [Diário Oficial do Piauí](https://www.diario.pi.gov.br/doe/) | Sim | `POST /doe/Api/listardiarios.json`; o catálogo retorna o link PDF |
| PR | DIOE-PR `DOEP` | [DIOE-PR](https://www.dioe.pr.gov.br/) | Sim | Catálogo de últimas edições; download por ID |
| RJ | DOERJ `DOERJ` | [IOERJ](https://www.ioerj.com.br/portal/modules/conteudoonline/) | Não | Formulários HTML por data; preserva as partes e extras retornados |
| RS | DOE-RS `DOERS` | [DOE-RS](https://doe.rs.gov.br/) | Sim | Backend público por data/tipo; PDF por ID |
| SC | DOE-SC `DOESC` | [Repositório DOE-SC](https://portal.doe.sea.sc.gov.br/) | Não | Sondagem `HEAD` no padrão de caminho do repositório |
| SP | DOE-SP `DOESP` | [DOE-SP](https://doe.sp.gov.br/) | Sim | APIs públicas de jornais, seções e URL de PDF |

## Detalhes por estado

### AC — Acre

O coletor mantém dois diários: o DOE estadual e o DJE do TJAC. O DOE é
consultado por mês e o DJE pela página pública de edições. Não há uma API
pública utilizada; os links oficiais de PDF são preservados em `fonte_url`.

### AL — Alagoas

Usa a API mensal da Imprensa Oficial. A resposta pode trazer edição principal e
suplemento, ambos preservados separadamente em `LAKE/AL`. O download usa o ID
retornado por `downloadPdf`.

### AM — Amazonas

Consulta a API diária do catálogo. Cada item possui ID, número e eventual
suplemento; o PDF é baixado pelo endpoint oficial de edição.

### AP — Amapá

Segue o mesmo catálogo público diário de edições. A edição é identificada por
ID e número, e o PDF é baixado pelo portal DIOFE.

### BA — Bahia

O projeto separa DOE-BA, DOEL-BA e DJE-BA. O catálogo é acessível por API, mas
o PDF certificado do DOE exige autenticação; por isso o coletor público usa o
conteúdo HTML oficial. DOEL e DJE têm arquivos próprios e saídas separadas.

### CE — Ceará

O portal expõe busca pública via API WordPress. Os cadernos retornados são
preservados separadamente, e o download usa a exportação oficial em PDF.

### DF — Distrito Federal

Não há API pública equivalente. O coletor lê a página diária, interpreta o
objeto JavaScript `lstLinkPdf` e baixa a edição integrada e os arquivos extras.

### ES — Espírito Santo

Usa o catálogo diário público e baixa a edição consolidada. O PDF pode conter
o caderno do Executivo e atos municipais; essa característica é mantida na
extração.

### GO — Goiás

Usa API diária. Quando o catálogo retorna edição principal e suplemento, os
dois são mantidos, com Markdown e atos vinculados à edição correta.

### MA — Maranhão

Consulta o acervo por mês e por caderno. O coletor percorre Executivo,
Judiciário, Terceiros, suplementos e extras; cada arquivo recebido tem seu
próprio registro no LAKE.

### MG — Minas Gerais

Usa a API do Jornal Minas Gerais, incluindo calendário, consulta por data e
download dos cadernos. O foco integrado é o Diário do Executivo, incluindo
edições extras.

### MS — Mato Grosso do Sul

Consulta a API paginada por intervalo de datas. O caminho do arquivo vem no
catálogo e pode apontar para o domínio de ativos da Imprensa Oficial.

### MT — Mato Grosso

Usa a API REST do IOMAT. A edição principal e as edições extras são baixadas
por ID no formato PDF.

### PA — Pará

Não depende de API: testa as URLs oficiais previsíveis da IOEPA para a edição
normal e para eventual extra. O padrão é
`https://www.ioepa.com.br/pages/AAAA/AAAA.MM.DD.DOE.pdf`.

### PB — Paraíba

O DOE/PB é obtido por índice HTML mensal. O DJE/PB usa o portal do TJPB e a
URL oficial diária. São fontes diferentes, com códigos e arquivos próprios.

### PE — Pernambuco

O portal CEPE fornece metadados de edição pela API pública. O coletor consulta
a edição normal e a extra e monta o caminho do arquivo no armazenamento oficial
S3. Se o armazenamento responder com erro de acesso, a falha é registrada e a
edição permanece pendente para nova tentativa.

### PI — Piauí

O portal usa uma tabela server-side. O coletor envia `POST` com o filtro de
data para `listardiarios.json`, extrai o link PDF do HTML retornado e valida a
assinatura `%PDF` antes de processar o arquivo.

### PR — Paraná

Usa o catálogo público de últimas edições da DIOE. Todos os tipos retornados
pela fonte são preservados e baixados por ID.

### RJ — Rio de Janeiro

Não há API pública usada pelo coletor. A IOERJ é consultada por formulários
HTML e cada parte do DOERJ é salva separadamente, inclusive extras e
municipalidades quando retornados.

### RS — Rio Grande do Sul

Usa o backend público do DOE-RS para consultar data e tipo de diário. O PDF
oficial é baixado por ID e convertido para o formato comum do projeto.

### SC — Santa Catarina

Não possui API pública usada pelo projeto. O coletor testa o repositório oficial
por `HEAD`, identifica a edição ordinária ou extra e baixa o PDF existente.

### SP — São Paulo

Usa as APIs atuais do DOE-SP para jornais, seções e URLs de PDF. O coletor
regular cobre o acervo atual; o acervo legado da Seção II do Executivo possui
comando separado.

## Formato dos dados

### Markdown por edição

```text
LAKE/<UF>/<AAAA>/<MM>/<CODIGO>_<EDICAO>_<AAAA-MM-DD>.md
```

O Markdown preserva o texto extraído da publicação e a identificação da fonte.
Ele é reutilizado em execuções futuras; se já existir, o PDF não é baixado e
convertido novamente.

### CSV anual

```text
saida/<UF>/<CODIGO>_<AAAA>.csv
```

As colunas principais são estado, diário, data, seção, tipo de ação, nome,
matrícula, cargo, órgão, trecho, URL da fonte e caminho do Markdown. A escrita
é deduplicada para que uma nova execução não duplique os atos.

### Cache e falhas

- PDFs temporários: `.cache/diarios`.
- Falhas por edição: registro gerado pelo coletor na estrutura de saída.
- Marcador de ano completo: usado para evitar reprocessamento de anos fechados.
- OCR: acionado quando o texto embutido no PDF é insuficiente e a configuração
  permite.

## Comandos úteis

Coleta de uma data:

```powershell
python main.py --coletar-pa --pa-data-inicial 2026-10-23 --pa-data-final 2026-10-23
python main.py --coletar-pe --pe-data-inicial 2026-10-23 --pe-data-final 2026-10-23
python main.py --coletar-pi --pi-data-inicial 2026-10-23 --pi-data-final 2026-10-23
```

Coleta retroativa por estado:

```powershell
.\coletar_pa_retroativo.bat
.\coletar_pe_retroativo.bat
.\coletar_pi_retroativo.bat
```

Coleta retroativa de todos os estados que possuem BAT:

```powershell
.\coletar_retroativos.bat
```
