# Deploy do dashboard temporal

Esta pasta contem uma versao enxuta do dashboard temporal para deploy no Render.

## Arquivos incluidos

- `app.py`: ponto de entrada do Dash.
- `requirements.txt`: dependencias necessarias para rodar o painel.
- `analise_temporal/`: modulos usados pelo dashboard em tempo de execucao.
- `saida/analises/RJ/retornos_apos_exoneracao.csv`: base de retornos.
- `saida/analises/RJ/movimentacoes_pessoas.parquet`: base de movimentacoes.

## Render

Crie um Web Service apontando para este repositorio e configure:

```text
Root Directory:
deploy/dash_temporal
```

```text
Build Command:
pip install -r requirements.txt
```

```text
Start Command:
gunicorn app:server --bind 0.0.0.0:$PORT
```

O Render define a variavel `PORT` automaticamente. O app precisa escutar em `0.0.0.0:$PORT` para ficar acessivel publicamente.

## Teste local

Dentro desta pasta:

```powershell
python app.py
```

Depois acesse:

```text
http://127.0.0.1:8052
```
