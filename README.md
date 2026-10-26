# Análise do 2º turno presidencial 2026 — rankings por município

Quais cidades deram mais votos, maior percentual e maior vantagem (em votos e em pontos percentuais) a **Lula** e a **Flávio Bolsonaro** no 2º turno de 25/10/2026, com cortes Top 3, 5, 10, 15 … 50.

Inspirado em [apolinario/urnas-tardias](https://github.com/apolinario/urnas-tardias): mesma fonte (publicação oficial do TSE em `resultados.tse.jus.br`), outro recorte.

## Resultado

- **Relatório Nacional:** [`saida/relatorio.md`](saida/relatorio.md)
- **Relatório dos Estados (compilado):** [`saida/relatorio_estados.md`](saida/relatorio_estados.md)
- **Relatórios por Estado (27 UFs):** pasta [`saida/estados/`](saida/estados/) (ex.: [`SP.md`](saida/estados/SP.md), [`BA.md`](saida/estados/BA.md), [`MG.md`](saida/estados/MG.md))
- **Base completa (todos os municípios):** [`saida/municipios.csv`](saida/municipios.csv)
- **Rankings nacionais em formato longo:** [`saida/rankings.csv`](saida/rankings.csv)
- **Rankings estaduais em formato longo:** [`saida/rankings_estados.csv`](saida/rankings_estados.csv)

## Como funciona

1. `crawl.py` lê a lista de municípios (`config/mun-e006258-cm.json`) e baixa o resultado final de cada um
   (`dados/<uf>/<uf><cod_tse>-c0001-e006258-u.json`), mais os totais oficiais de cada UF e do Brasil. Retomável, com
   limite de taxa, retry com backoff e `dados/manifest.json` (SHA-256 de cada arquivo).
2. `analisa.py` consolida, **valida** contra os totais oficiais e gera os rankings nacionais e estaduais. Se qualquer checagem falhar, o
   relatório não é gerado.

`6258` é o código TSE da eleição *Presidente – 2º turno* (campo `cdt2` da eleição `6257`, 1º turno).

## Como executar

Requer [uv](https://docs.astral.sh/uv/) (ou Python ≥ 3.11 + `pandas`).

```powershell
python crawl.py                 # ~10 min a 10 req/s; pode ser interrompido e retomado
uv run --with pandas python analisa.py
```

Opções de `analisa.py`: `--top 50`, `--uf SP` (filtra UF específica), `--incluir-exterior`, `--min-validos 10000` (ignora cidades pequenas — útil
para rankings percentuais).

## Como testar

```powershell
uv run --with pandas --with pytest pytest -q
uv run --with ruff ruff check .
```

## Definições

- **Votos válidos** = Lula + Flávio (brancos e nulos ficam fora), mesma base de percentual usada pelo TSE.
- **% de votos** = votos do candidato ÷ votos válidos do município.
- **Dif. votos** = votos Lula − votos Flávio. **Dif. p.p.** = % Lula − % Flávio. Os rankings de vantagem só incluem
  cidades em que o candidato ficou na frente.
- **Escopo padrão:** as 5.571 localidades brasileiras do TSE (5.570 municípios + Fernando de Noronha, listado à
  parte). As 186 localidades do exterior (código `ZZ`) entram na base
  (`municipios.csv`) e nos totais de validação, mas não nos rankings, salvo com `--incluir-exterior`.
- **Desempate:** mais votos válidos, depois ordem alfabética.

## Limitações

- Rankings percentuais favorecem municípios pequenos (poucos milhares de votos): leia a coluna *Válidos*.
- Os dados refletem a totalização final publicada pelo TSE na data da execução; retificações posteriores exigem
  rodar `crawl.py` novamente (apague `dados/raw` para forçar download completo).
- A base é de resultados por município; não há granularidade de bairro/seção neste projeto.

## Reprodutibilidade e auditoria

`dados/manifest.json` registra fonte, data/hora do download e SHA-256 de cada arquivo bruto, além de um hash
consolidado (também impresso no relatório). O relatório lista as checagens executadas (soma dos municípios = total
oficial por UF e Brasil, % calculado = % do TSE, coerência de comparecimento etc.).

## Manutenção

Projeto pessoal de análise, sem garantia de suporte.
