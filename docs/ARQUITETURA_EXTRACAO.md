# Arquitetura nacional de extracao (migracao incremental)

A descoberta e o download continuam nos coletores por portal em
`diarios_oficiais/estadual`. A extração de atos passa a ter uma interface
compartilhada em `diarios_oficiais/extracao/engine.py`. As regras
existentes de `diarios_oficiais/utils_regex` permanecem ativas por estado.

## Compatibilidade

A primeira etapa usa um adaptador para o parser historico em
`estadual/rj_ioerj.py`. Esta mudanca reorganiza as dependencias e
**nao** constitui uma nova implementacao nacional de NER. Migrar as
funcoes internas do parser em outra etapa, validando paridade antes da troca.

## Integridade da coleta

- SP: intervalos incrementais e retroativos tratados separadamente.
- PDF diario: erro de rede e HTTP inesperado nao significam arquivo ausente.
- A rotina compartilhada nao cria novos marcadores de ano completo sem
  reconciliar calendario oficial e edicoes; marcadores antigos ainda
  precisam de auditoria.
- BA/RS: verificacao TLS ativada. Ajustar a cadeia de certificados no
  sistema ou por CA confiavel quando necessario.

## Validacao

```powershell
python -m unittest discover -s tests
```

Validar tambem a comunicacao HTTPS de BA e RS no ambiente real.
