# Análise Independente do 2º Turno Presidencial de 2026

Análise eleitoral e rankings municipais reproduzíveis do 2º turno da eleição presidencial brasileira de 25 de outubro de 2026 (**Lula** × **Flávio Bolsonaro**), baseada estritamente nos dados oficiais do Tribunal Superior Eleitoral (TSE).

> **Classificação metodológica:** Trata-se de uma **análise independente baseada em dados oficiais do TSE**. A fonte primária de apuração dos votos é oficial e pública, enquanto a extração, consolidação, metodologia de ordenação e relatórios são de autoria deste projeto.

Inspirado na arquitetura e rigor de [apolinario/urnas-tardias](https://github.com/apolinario/urnas-tardias): mesma fonte (`resultados.tse.jus.br`), voltado para a análise do resultado municipal e estadual.

---

## Resultados e Relatórios

- **Relatório Nacional Consolidado:** [`saida/relatorio.md`](saida/relatorio.md)
  - Totais nacionais oficiais (Brasil + Exterior).
  - Distribuição dos votos e vitórias por faixas de porte do eleitorado municipal.
  - Rankings Top 3, 5, 10, 15, 20, 25, 30, 35, 40, 45 e 50 nas 8 categorias.
  - Panorama geral dos 26 estados + DF.
  - Tabela de validação de integridade dos dados e cruzamento com os totais oficiais.
- **Relatório Geral dos Estados (Compilação):** [`saida/relatorio_estados.md`](saida/relatorio_estados.md)
- **Relatórios Detalhados por Estado (27 UFs):** diretório [`saida/estados/`](saida/estados/) (ex.: [`SP.md`](saida/estados/SP.md), [`BA.md`](saida/estados/BA.md), [`MG.md`](saida/estados/MG.md), [`PR.md`](saida/estados/PR.md), [`RJ.md`](saida/estados/RJ.md)).
- **Base Completa por Município:** [`saida/municipios.csv`](saida/municipios.csv) (todos os 5.571 municípios brasileiros + 186 localidades do exterior, com abstenções, brancos, nulos, válidos, votos e percentuais).
- **Rankings Nacionais (formato longo):** [`saida/rankings.csv`](saida/rankings.csv)
- **Rankings Estaduais (formato longo):** [`saida/rankings_estados.csv`](saida/rankings_estados.csv)

---

## Destaques da Análise

### 1. Totais Nacionais Oficiais (TSE — Eleição 6258)
- **Lula:** 64.256.232 votos (51,79%)
- **Flávio Bolsonaro:** 59.826.041 votos (48,21%)
- **Diferença:** +4.430.191 votos a favor de Lula
- **Municípios brasileiros vencidos:** Lula venceu em 2.875 municípios; Flávio venceu em 2.695 municípios; houve exatamente **1 empate** descoberto dinamicamente pela base: **Marquinho/PR** (1.530 × 1.530 votos, 50,00%).
- **Votação no Exterior (ZZ — 186 localidades):** Lula 200.154 votos (53,85%) × Flávio 171.497 votos (46,15%).

[![CI](https://github.com/guilobocm/analise-resultado-2turno-2026/actions/workflows/ci.yml/badge.svg)](https://github.com/guilobocm/analise-resultado-2turno-2026/actions/workflows/ci.yml)

### 2. Comportamento por Faixa de Porte (Votos Válidos Apurados)
A distribuição dos municípios por faixas de votos válidos apurados revela a geografia do resultado:

| Faixa de porte | Municípios | Votos Válidos | Lula (votos) | Lula (%) | Flávio (votos) | Flávio (%) | Vantagem Lula | Cidades (L / F / Emp) |
|:--|--:|--:|--:|--:|--:|--:|--:|:--:|
| **Até 10.000 válidos** | 3.418 | 16.512.661 | 9.057.094 | 54,85% | 7.455.567 | 45,15% | +1.601.527 (+9,70 p.p.) | 1.718 / 1.699 / 1 |
| **10.001 a 50.000 válidos** | 1.768 | 35.095.190 | 19.433.627 | 55,37% | 15.661.563 | 44,63% | +3.772.064 (+10,75 p.p.) | 1.015 / 753 |
| **50.001 a 200.000 válidos** | 310 | 28.209.254 | 13.240.706 | 46,94% | 14.968.548 | 53,06% | −1.727.842 (−6,13 p.p.) | 113 / 197 |
| **200.001 a 500.000 válidos** | 57 | 17.420.377 | 8.372.446 | 48,06% | 9.047.931 | 51,94% | −675.485 (−3,88 p.p.) | 21 / 36 |
| **Mais de 500.000 válidos** | 18 | 26.473.140 | 13.952.205 | 52,70% | 12.520.935 | 47,30% | +1.431.270 (+5,41 p.p.) | 8 / 10 |

> **Distinção conceitual (Votos Válidos vs. Eleitorado Apto):** A classificação acima baseia-se estritamente na quantidade de **votos válidos apurados** (Lula + Flávio), totalizando 123,7 milhões de votos nos municípios brasileiros. O **eleitorado apto** (157,8 milhões de eleitores registrados no TSE) é uma grandeza diferente por incluir abstenções (18,99%), votos brancos (1,37%) e nulos (2,73%). A dinâmica política agregada entre as faixas, todavia, mantém-se equivalente sob ambos os critérios.

#### Estratificação Regional das Cidades Pequenas (até 50.000 votos válidos)
Para evitar generalizações apressadas (falácia ecológica), é indispensável observar como o comportamento das cidades pequenas varia conforme a macrorregião geográfica:

| Região | Municípios (≤ 50k) | Votos Válidos | Lula (votos) | Lula (%) | Flávio (votos) | Flávio (%) | Vantagem Lula | Cidades (L / F / Emp) |
|:--|--:|--:|--:|--:|--:|--:|--:|:--:|
| **Norte** | 418 | 4.675.559 | 2.502.886 | 53,53% | 2.172.673 | 46,47% | +330.213 (+7,06 p.p.) | 254 / 164 / 0 |
| **Nordeste** | 1.706 | 20.067.460 | 14.876.144 | 74,13% | 5.191.316 | 25,87% | +9.684.828 (+48,26 p.p.) | 1.694 / 12 / 0 |
| **Centro-Oeste** | 442 | 3.704.275 | 1.442.808 | 38,95% | 2.261.467 | 61,05% | −818.659 (−22,10 p.p.) | 61 / 381 / 0 |
| **Sudeste** | 1.495 | 14.250.509 | 6.498.937 | 45,60% | 7.751.572 | 54,40% | −1.252.635 (−8,79 p.p.) | 598 / 897 / 0 |
| **Sul** | 1.125 | 8.910.048 | 3.169.946 | 35,58% | 5.740.102 | 64,42% | −2.570.156 (−28,85 p.p.) | 126 / 998 / 1 |

> [!IMPORTANT]
> **Efeito de Composição Regional vs. Porte Municipal:** A vantagem agregada de Lula nas cidades com até 50 mil votos válidos (+5,37 milhões de votos) **não decorre de uma tendência uniforme de pequenas cidades em todo o Brasil**. Ela é explicada pela votação expressiva no Nordeste (+9,68 milhões de saldo em 1.706 cidades pequenas). No Centro-Oeste, Sudeste e Sul, Flávio Bolsonaro foi o vencedor na maioria absoluta dos municípios desse mesmo porte (venceu em 2.276 das 3.062 cidades dessas três regiões, acumulando uma vantagem de 4,64 milhões de votos). Portanto, o porte municipal não deve ser interpretado como fator causal isolado, tratando-se preponderantemente de um efeito de composição e heterogeneidade geográfica.

**Síntese reconciliada por porte:**
- **Localidades com até 50 mil votos válidos (5.186 municípios):** Saldo líquido nacional de Lula de +5.373.591 votos (+1.601.527 na faixa até 10k e +3.772.064 na faixa 10k-50k), impulsionado pelas regiões Nordeste e Norte.
- **Cidades médias e grandes (50 mil a 500 mil válidos, 367 municípios):** Reduto de Flávio Bolsonaro, com saldo pró-Flávio de −2.403.327 votos (−1.727.842 na faixa 50k-200k e −675.485 na faixa 200k-500k).
- **Grandes metrópoles (>500 mil válidos, 18 municípios):** Embora Flávio tenha vencido em 10 das 18 metrópoles, Lula obteve vantagem líquida de +1.431.270 votos nas metrópoles, impulsionado por São Paulo capital (+766 mil), Salvador (+732 mil) e Fortaleza (+313 mil).

---

## Metodologia e Equivalência Matemática dos Rankings

O projeto apresenta 8 tabelas de ranking (nacional e por estado):
1. Mais votos brutos — Lula
2. Mais votos brutos — Flávio
3. Maior % de votos válidos — Lula
4. Maior % de votos válidos — Flávio
5. Maior vantagem em votos brutos — Lula sobre Flávio
6. Maior vantagem em votos brutos — Flávio sobre Lula
7. Maior vantagem percentual (p.p.) — Lula sobre Flávio
8. Maior vantagem percentual (p.p.) — Flávio sobre Lula

### A equivalência entre Percentual (%) e Vantagem em Pontos Percentuais (p.p.)
Em uma eleição de segundo turno com exatamente dois candidatos, os votos válidos são dados por:
$$\text{Válidos} = \text{Votos}_{\text{Lula}} + \text{Votos}_{\text{Flávio}}$$

Portanto, $\% \text{Flávio} = 100\% - \% \text{Lula}$. A vantagem de Lula em pontos percentuais é:
$$\text{Vantagem de Lula (p.p.)} = \% \text{Lula} - \% \text{Flávio} = \% \text{Lula} - (100 - \% \text{Lula}) = 2 \times \% \text{Lula} - 100$$

Como a transformação afim $f(x) = 2x - 100$ é estritamente crescente (derivada positiva igual a 2), ordenar municípios pelo $\% \text{Lula}$ gera **rigorosamente a mesma sequência/ordenação** que ordená-los pela vantagem percentual de Lula em p.p. O mesmo raciocínio se aplica simetricamente a Flávio Bolsonaro.

#### Ressalva Crítica de Cobertura: Vantagem vs. Percentual
Embora a ordenação seja estritamente idêntica para municípios em que o candidato venceu ($\% > 50\%$), as duas tabelas diferem no escopo de inclusão:
- **Rankings de Vantagem:** exigem margem positiva (`so_positivos = True`), incluindo **apenas municípios em que o candidato efetivamente venceu** (exclui derrotas e empates).
- **Rankings Percentuais:** listam todas as localidades do escopo, inclusive municípios onde o candidato obteve votação minoritária (% < 50%).

**Impacto prático nos estados:** Em estados onde um candidato venceu pouquíssimos municípios (como Roraima, onde Lula venceu 1 de 15 cidades, ou Santa Catarina, onde venceu 6 de 295), o ranking de vantagem encerra-se com o número exato de cidades vencidas (1 linha em RR, 6 linhas em SC), enquanto o ranking percentual preenche as posições restantes (até o corte Top N) com cidades onde o candidato foi derrotado.

Ambas as tabelas (% e p.p.) são mantidas nos relatórios para conveniência analítica do leitor (uma permite visualizar o percentual absoluto atingido e a outra quantifica diretamente a margem de separação em relação ao adversário).

---

## Reprodutibilidade, Snapshot Bruto e Auditoria de Integridade

1. **Snapshot Bruto dos Dados (`dados/tse_2turno_2026_raw.zip`):**
   - O repositório armazena o pacote comprimido (6,39 MB) com todos os 5.757 arquivos JSON municipais originais e totais publicados pelo TSE.
   - Caso a pasta `dados/raw` não exista, o script `analisa.py` descompacta automaticamente o snapshot.
2. **Verificação de Hash SHA-256 (`dados/manifest.json`):**
   - Antes de gerar qualquer relatório, `analisa.py` audita concurrentemente todos os arquivos brutos, verificando se seus bytes e hashes SHA-256 individuais coincidem com `manifest.json`.
   - O hash consolidado `98e1cfbb6ec73f81603b25a05587f157ffa25b07796b254f3ed921e27ed7e8d9` é recomputado e validado em tempo de execução.
3. **Validação Contábil Cruzada:**
   - A soma de todos os municípios de cada estado é confrontada com o arquivo de totalização oficial da UF (`dados/raw/_totais/<uf>.json`).
   - A soma nacional é confrontada com o total oficial do Brasil (`dados/raw/_totais/br.json`).
   - O percentual calculado pelo projeto é comparado com os campos de percentual publicados pelo TSE (tolerância `< 1e-6` p.p.).
4. **Descoberta Dinâmica de Empates:**
   - O script não utiliza textos estáticos para empates; qualquer cidade empatada é identificada e descrita dinamicamente em runtime.
5. **Robustez dos Filtros Estaduais (`--min-validos`):**
   - O parâmetro `--min-validos` filtra estritamente os rankings municipais (evitando a distorção típica de municípios diminutos nas tabelas percentuais), mantendo o **Panorama Estadual** com os totais completos e oficiais do estado.

---

## Integração Contínua (CI)

O repositório conta com pipeline automatizado no GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)), testando em múltiplos ambientes:
- **Python 3.11, 3.12 e 3.13** em Ubuntu Linux.
- Análise estática e linting rigoroso com **Ruff** (`ruff check .`).
- Suíte completa de 18 testes unitários com **pytest** (`pytest -v`).
- Execução determinística do pipeline `python analisa.py`, garantindo auditoria de integridade e checagens 100% verdes.

---

## Como Executar

### Pré-requisitos
Python ≥ 3.11 com gerenciador de ambiente ([uv](https://docs.astral.sh/uv/) ou `venv` + `pip`).

```powershell
# 1. Instalar dependências
pip install pandas pytest ruff

# 2. Executar análise completa (extrai snapshot bruto e valida SHA-256)
python analisa.py

# 3. Executar com filtro de porte municipal (ex.: cidades com pelo menos 10.000 votos válidos)
python analisa.py --min-validos 10000

# 4. Executar para um estado específico (ex.: São Paulo)
python analisa.py --uf SP
```

### Como Executar os Testes

```powershell
pytest -v
ruff check .
```

---

## Licença e Fontes

- **Dados:** Tribunal Superior Eleitoral (TSE) — dados públicos oficiais (Eleição Ordinária Presidencial 2026, 2º Turno, código 6258).
- **Código e Análise:** Licença MIT. Desenvolvido para pesquisa e transparência pública de dados eleitorais.
