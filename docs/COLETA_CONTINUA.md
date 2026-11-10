# Coleta continua sem argumentos de linha de comando

## Inicializacao no Windows

1. Abra a raiz do repositorio (onde esta `main.py`).
2. Instale as dependencias conforme a configuracao do projeto; use um ambiente virtual `.venv`.
3. Execute `iniciar_coleta.bat` com duplo clique.
4. Para encerrar com seguranca, pressione **Ctrl+C**.

Alternativa direta: `python coletar_continuamente.py`.

## Configuracoes

Edite apenas as constantes no inicio de `coletar_continuamente.py`:

- `INTERVALO_ENTRE_RODADAS_HORAS = 6`: tempo **apos o fim** de uma rodada completa.
- `INTERVALO_APOS_ERRO_MINUTOS = 15`: espera apos erro geral.
- `PULAR_ANOS_COMPLETOS = True`: respeita os marcadores de ano completo.
- `EXECUTAR_CONTINUAMENTE = True`: repete as rodadas ate Ctrl+C.

Nao e necessario informar `args` ou flags na linha de comando.

## O que acontece

O inicializador chama `collect_estaduais_em_rodizio()`, implementado em
`diarios_oficiais/rodizio_estadual.py`. A rotina visita as 27 UFs,
intercalando cadernos e percorrendo datas das mais recentes as antigas.
Cada coletor reutiliza Markdown ja existente e grava os CSVs anuais
conforme suas regras. Anos marcados como completos podem ser ignorados.

**Importante:** uma rodada retroativa longa pode durar dias. A repeticao
de seis em seis horas ocorre somente depois de ela terminar, nao
durante a rodada. A coleta nao se torna um servico do Windows; manter
o computador ligado, acordado e a janela aberta e necessario.

## Logs e retomada

- Log do inicializador: `logs/coleta_continua.log`.
- Mensagens detalhadas dos extratores aparecem no terminal.
- A retomada aproveita os arquivos persistidos e as verificacoes
  de cada extrator. Nao ha checkpoint por edicao novo neste inicializador.
- Erros tratados dentro do rodizio sao registrados e a coleta segue;
  erros gerais da rodada acionam nova tentativa.

Evite iniciar duas instancias simultaneas sobre a mesma pasta `LAKE`,
para nao disputar escrita nos mesmos arquivos.

## Destinos

As configuracoes atuais de `diarios_oficiais/config.py` determinam:
`LAKE/<UF>/<ano>/<mes>/` para Markdown e `saida/<UF>/` para CSVs.
O arquivo de log e criado na raiz do checkout, em `logs/`.

## Limitacoes

Este inicializador e voltado a coleta **retroativa em rodizio**.
Nao inclui agendamento de tarefas do Windows, dashboard de progresso,
retry por edicao nem um worker diario independente.
