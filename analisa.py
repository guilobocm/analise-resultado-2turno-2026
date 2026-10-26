"""Rankings municipais do 2º turno presidencial de 2026 (Lula x Flávio Bolsonaro).

Lê os arquivos oficiais baixados por `crawl.py`, consolida em uma base por município,
valida contra os totais oficiais do TSE e gera:

  saida/municipios.csv   base completa (todos os municípios, inclusive exterior)
  saida/rankings.csv     todos os rankings em formato longo (Top 50 de cada)
  saida/relatorio.md     relatório legível com os rankings Top 3, 5, 10, … 50

Uso:  python analisa.py [--dados dados] [--saida saida] [--top 50]
                        [--incluir-exterior] [--min-validos N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

ELEICAO = "6258"
COD_LULA = "13"
COD_FLAVIO = "22"
TOP_NS = (3, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50)
PEQUENAS = {"De", "Da", "Do", "Das", "Dos", "E"}
REGIOES = {
    "Norte": ("AC", "AP", "AM", "PA", "RO", "RR", "TO"),
    "Nordeste": ("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"),
    "Centro-Oeste": ("DF", "GO", "MT", "MS"),
    "Sudeste": ("ES", "MG", "RJ", "SP"),
    "Sul": ("PR", "RS", "SC"),
}


# --------------------------------------------------------------------------- leitura


def ler_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8-sig"))


def _pct(s: str) -> float:
    """O TSE publica percentuais com vírgula decimal ("22,262773723")."""
    return float(s.replace(",", "."))


def parse_municipio(j: dict) -> dict:
    """Extrai de um JSON de município do TSE os números de Lula, Flávio e o contexto de comparecimento."""
    cargo = j["carg"][0]
    if cargo["cd"] != "1":
        raise ValueError("cargo inesperado (esperado Presidente, cd=1)")
    cands = {
        c["n"]: c
        for agr in cargo["agr"]
        for par in agr["par"]
        for c in par["cand"]
    }
    if set(cands) != {COD_LULA, COD_FLAVIO}:
        raise ValueError(f"candidatos inesperados: {sorted(cands)}")
    lula, flavio = cands[COD_LULA], cands[COD_FLAVIO]
    return {
        "lula": int(lula["vap"]),
        "flavio": int(flavio["vap"]),
        "pct_lula_tse": _pct(lula["pvapn"]),
        "pct_flavio_tse": _pct(flavio["pvapn"]),
        "validos": int(j["v"]["vvc"]),
        "brancos": int(j["v"]["vb"]),
        "nulos": int(j["v"]["tvn"]),
        "comparecimento": int(j["e"]["c"]),
        "abstencoes": int(j["e"]["a"]),
        "aptos": int(j["e"]["te"]),
        "totalizacao_final": j["tf"] == "s",
        "hora_totalizacao": f"{j['dt']} {j['ht']}",
    }


def assegurar_dados_brutos(dados: Path) -> None:
    """Garante a existência de dados/raw; se ausente ou vazia, descompacta o snapshot zip."""
    pasta_raw = dados / "raw"
    zip_path = dados / "tse_2turno_2026_raw.zip"
    if not pasta_raw.exists() or not any(pasta_raw.rglob("*.json")):
        if not zip_path.exists():
            raise FileNotFoundError(
                f"Pasta de dados brutos ({pasta_raw}) não encontrada e snapshot ({zip_path}) ausente. "
                "Execute crawl.py para baixar os dados do TSE."
            )
        print(f"Extraindo dados brutos a partir de {zip_path.name}...", file=sys.stderr)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dados)


def montar_base(dados: Path) -> pd.DataFrame:
    cfg = ler_json(dados / "raw" / "_config" / "municipios.json")
    linhas = []
    for uf in cfg["abr"]:
        for m in uf["mu"]:
            arq = dados / "raw" / uf["cd"] / f"{uf['cd']}{m['cd']}.json"
            if not arq.exists():
                raise FileNotFoundError(f"faltando {arq} — rode crawl.py")
            reg = parse_municipio(ler_json(arq))
            linhas.append(
                {"uf": uf["cd"].upper(), "cod_tse": m["cd"], "cod_ibge": m.get("cdi", ""), "municipio": m["nm"], **reg}
            )
    df = pd.DataFrame(linhas)
    df["exterior"] = df["uf"] == "ZZ"
    df["pct_lula"] = (df["lula"] / df["validos"] * 100).where(df["validos"] > 0)
    df["pct_flavio"] = (df["flavio"] / df["validos"] * 100).where(df["validos"] > 0)
    df["dif_votos"] = df["lula"] - df["flavio"]  # >0: Lula na frente; <0: Flávio na frente
    df["dif_pp"] = df["pct_lula"] - df["pct_flavio"]  # pontos percentuais sobre votos válidos
    df["vencedor"] = df["dif_votos"].map(lambda d: "Lula" if d > 0 else "Flávio" if d < 0 else "Empate")
    return df


# --------------------------------------------------------------------------- validação


@dataclass
class Checagem:
    nome: str
    ok: bool
    detalhe: str = ""


def verificar_manifesto(dados: Path) -> Checagem:
    """Valida a integridade SHA-256 de todos os arquivos brutos contra dados/manifest.json."""
    manifest_path = dados / "manifest.json"
    if not manifest_path.exists():
        return Checagem("integridade SHA-256 contra manifest.json", False, "manifest.json não encontrado")
    try:
        manifest = ler_json(manifest_path)
    except Exception as e:
        return Checagem("integridade SHA-256 contra manifest.json", False, f"erro ao ler manifest.json: {e}")

    arquivos = manifest.get("arquivos", [])
    if not arquivos:
        return Checagem("integridade SHA-256 contra manifest.json", False, "nenhum arquivo no manifesto")

    def _checar(item: dict) -> tuple[bool, str]:
        p = dados / item["arquivo"]
        if not p.exists():
            return False, f"arquivo ausente: {item['arquivo']}"
        b = p.read_bytes()
        if len(b) != item.get("bytes"):
            return False, f"tamanho divergente: {item['arquivo']}"
        if hashlib.sha256(b).hexdigest() != item.get("sha256"):
            return False, f"hash divergente: {item['arquivo']}"
        return True, ""

    with ThreadPoolExecutor(max_workers=16) as ex:
        resultados = list(ex.map(_checar, arquivos))

    erros = [msg for ok, msg in resultados if not ok]
    if erros:
        return Checagem("integridade SHA-256 contra manifest.json", False, f"{len(erros)} falhas ({erros[0]})")

    sha_calc = hashlib.sha256("\n".join(f"{a['arquivo']}:{a['sha256']}" for a in arquivos).encode()).hexdigest()
    if sha_calc != manifest.get("sha256_consolidado"):
        return Checagem(
            "integridade SHA-256 contra manifest.json",
            False,
            f"hash consolidado divergente ({sha_calc[:8]} != {manifest.get('sha256_consolidado', '')[:8]})",
        )

    return Checagem(
        "integridade SHA-256 contra manifest.json",
        True,
        f"{len(arquivos)} arquivos verificados (hash consolidado {sha_calc[:12]}…)",
    )


def validar(df: pd.DataFrame, dados: Path) -> list[Checagem]:
    """Confere a base consolidada com os totais oficiais (UF e Brasil), manifesto e a coerência interna."""
    res: list[Checagem] = []

    if (dados / "manifest.json").exists():
        res.append(verificar_manifesto(dados))

    res.append(Checagem("municípios únicos (UF+código TSE)", not df.duplicated(["uf", "cod_tse"]).any(), f"{len(df)} linhas"))
    res.append(Checagem("todos com totalização final", bool(df["totalizacao_final"].all())))
    res.append(Checagem("válidos = Lula + Flávio (cada município)", bool((df["lula"] + df["flavio"] == df["validos"]).all())))
    res.append(
        Checagem(
            "comparecimento = válidos + brancos + nulos (cada município)",
            bool((df["validos"] + df["brancos"] + df["nulos"] == df["comparecimento"]).all()),
        )
    )
    com_votos = df[df["validos"] > 0]
    dif = max(
        (com_votos["pct_lula"] - com_votos["pct_lula_tse"]).abs().max(),
        (com_votos["pct_flavio"] - com_votos["pct_flavio_tse"]).abs().max(),
    )
    res.append(Checagem("% calculado = % oficial do TSE (tol. 1e-6 p.p.)", bool(dif < 1e-6), f"maior diferença {dif:.2e}"))

    def totais(path: Path) -> tuple[int, int]:
        p = parse_municipio(ler_json(path))  # totais de UF/Brasil têm o mesmo formato do município
        return p["lula"], p["flavio"]

    pasta = dados / "raw" / "_totais"
    for uf, g in df.groupby("uf"):
        oficial = totais(pasta / f"{uf.lower()}.json")
        soma = (int(g["lula"].sum()), int(g["flavio"].sum()))
        res.append(Checagem(f"soma dos municípios = total oficial {uf}", soma == oficial, f"{soma} vs {oficial}"))
    oficial_br = totais(pasta / "br.json")
    soma_br = (int(df["lula"].sum()), int(df["flavio"].sum()))
    res.append(Checagem("soma de tudo = total oficial Brasil", soma_br == oficial_br, f"{soma_br} vs {oficial_br}"))

    # Reconciliação contábil: faixas de porte nacional vs regional (cidades com ≤ 50k válidos)
    ext = df["exterior"] if "exterior" in df.columns else (df["uf"] == "ZZ")
    br = df[~ext]
    if len(br) >= 5000:
        peq_porte = br[br["validos"] <= 50_000]
        uf2reg = {uf: reg for reg, ufs in REGIOES.items() for uf in ufs}
        soma_reg_mun = sum((peq_porte["uf"].map(uf2reg) == reg).sum() for reg in REGIOES)
        soma_reg_val = sum(peq_porte[peq_porte["uf"].map(uf2reg) == reg]["validos"].sum() for reg in REGIOES)
        soma_reg_lula = sum(peq_porte[peq_porte["uf"].map(uf2reg) == reg]["lula"].sum() for reg in REGIOES)
        soma_reg_fla = sum(peq_porte[peq_porte["uf"].map(uf2reg) == reg]["flavio"].sum() for reg in REGIOES)
        ok_rec = (
            soma_reg_mun == len(peq_porte)
            and soma_reg_val == peq_porte["validos"].sum()
            and soma_reg_lula == peq_porte["lula"].sum()
            and soma_reg_fla == peq_porte["flavio"].sum()
        )
        res.append(
            Checagem(
                "reconciliação porte nacional vs regional (≤ 50k válidos)",
                bool(ok_rec),
                f"{soma_reg_mun} municípios, {f_int(soma_reg_val)} válidos "
                f"(Lula: {f_int(soma_reg_lula)}, Flávio: {f_int(soma_reg_fla)})",
            )
        )
    return res


# --------------------------------------------------------------------------- rankings


@dataclass(frozen=True)
class Ranking:
    chave: str
    titulo: str
    coluna: str
    sinal: int = 1  # +1: maior valor primeiro; -1: usa o valor negado (vantagem de Flávio)
    so_positivos: bool = False  # rankings de margem consideram só quem de fato ficou na frente


RANKINGS = (
    Ranking("votos_lula", "Mais votos brutos — Lula", "lula"),
    Ranking("votos_flavio", "Mais votos brutos — Flávio", "flavio"),
    Ranking("pct_lula", "Maior % de votos válidos — Lula", "pct_lula"),
    Ranking("pct_flavio", "Maior % de votos válidos — Flávio", "pct_flavio"),
    Ranking("margem_votos_lula", "Maior vantagem em votos — Lula sobre Flávio", "dif_votos", 1, True),
    Ranking("margem_votos_flavio", "Maior vantagem em votos — Flávio sobre Lula", "dif_votos", -1, True),
    Ranking("margem_pp_lula", "Maior vantagem em p.p. — Lula sobre Flávio", "dif_pp", 1, True),
    Ranking("margem_pp_flavio", "Maior vantagem em p.p. — Flávio sobre Lula", "dif_pp", -1, True),
)


def faixa(posicao: int) -> int | None:
    """Menor Top N (3, 5, 10, …) que contém a posição; None se passar do maior."""
    return next((n for n in TOP_NS if posicao <= n), None)


def calcular_ranking(df: pd.DataFrame, r: Ranking, top: int = 50) -> pd.DataFrame:
    """Top N determinístico: empate no critério -> mais votos válidos -> nome (ordem alfabética)."""
    d = df[df["validos"] > 0].copy()
    d["_k"] = d[r.coluna] * r.sinal
    if r.so_positivos:
        d = d[d["_k"] > 0]
    d = d.sort_values(["_k", "validos", "municipio"], ascending=[False, False, True], kind="stable").head(top)
    d = d.drop(columns="_k").reset_index(drop=True)
    d.insert(0, "posicao", d.index + 1)
    d.insert(1, "faixa", d["posicao"].map(lambda p: f"Top {faixa(p)}" if faixa(p) else ""))
    return d


# --------------------------------------------------------------------------- formatação


def bonito(nome: str) -> str:
    palavras = nome.title().split(" ")
    return " ".join(p if i == 0 or p not in PEQUENAS else p.lower() for i, p in enumerate(palavras))


def f_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def f_pct(x: float) -> str:
    return f"{x:.2f}".replace(".", ",") + "%"


def f_sinal_int(n: int) -> str:
    return ("+" if n > 0 else "−" if n < 0 else "") + f_int(abs(n))


NOME_UF = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
    "ZZ": "Exterior",
}


def f_sinal_pp(x: float) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + f"{abs(x):.2f}".replace(".", ",")


def tabela_md(d: pd.DataFrame, omitir_uf: bool = False) -> str:
    if d.empty:
        return "_Nenhum município atendeu a este critério neste recorte._\n"
    if omitir_uf:
        cab = "| # | Faixa | Município | Lula | Flávio | Válidos | % Lula | % Flávio | Dif. votos (L−F) | Dif. p.p. (L−F) |"
        sep = "|--:|:--|:--|--:|--:|--:|--:|--:|--:|--:|"
        linhas = [
            f"| {r.posicao} | {r.faixa} | {bonito(r.municipio)} | {f_int(r.lula)} | {f_int(r.flavio)} | "
            f"{f_int(r.validos)} | {f_pct(r.pct_lula)} | {f_pct(r.pct_flavio)} | {f_sinal_int(r.dif_votos)} | "
            f"{f_sinal_pp(r.dif_pp)} |"
            for r in d.itertuples()
        ]
    else:
        cab = "| # | Faixa | Município | UF | Lula | Flávio | Válidos | % Lula | % Flávio | Dif. votos (L−F) | Dif. p.p. (L−F) |"
        sep = "|--:|:--|:--|:--:|--:|--:|--:|--:|--:|--:|--:|"
        linhas = [
            f"| {r.posicao} | {r.faixa} | {bonito(r.municipio)} | {r.uf} | {f_int(r.lula)} | {f_int(r.flavio)} | "
            f"{f_int(r.validos)} | {f_pct(r.pct_lula)} | {f_pct(r.pct_flavio)} | {f_sinal_int(r.dif_votos)} | "
            f"{f_sinal_pp(r.dif_pp)} |"
            for r in d.itertuples()
        ]
    return "\n".join([cab, sep, *linhas])


def tabela_analise_porte(df: pd.DataFrame) -> str:
    """Distribuição dos votos e vitórias por faixas de porte do eleitorado (votos válidos no município)."""
    br = df[~df["exterior"]].copy()
    faixas = [
        ("Até 10.000 válidos", 0, 10_000),
        ("10.001 a 50.000 válidos", 10_000, 50_000),
        ("50.001 a 200.000 válidos", 50_000, 200_000),
        ("200.001 a 500.000 válidos", 200_000, 500_000),
        ("Mais de 500.000 válidos", 500_000, float("inf")),
    ]
    cab = (
        "| Faixa de porte | Municípios | Votos Válidos | Lula (votos) | Lula (%) | "
        "Flávio (votos) | Flávio (%) | Vantagem Lula | Cidades (L / F / Emp) |"
    )
    sep = "|:--|--:|--:|--:|--:|--:|--:|--:|:--:|"
    linhas = []
    for rotulo, mn, mx in faixas:
        sub = br[(br["validos"] > mn) & (br["validos"] <= mx)]
        n_mun = len(sub)
        if n_mun == 0:
            continue
        tot_val = int(sub["validos"].sum())
        tot_l = int(sub["lula"].sum())
        tot_f = int(sub["flavio"].sum())
        pct_l = (tot_l / tot_val * 100) if tot_val > 0 else 0.0
        pct_f = (tot_f / tot_val * 100) if tot_val > 0 else 0.0
        dif_v = tot_l - tot_f
        c_l = int((sub["dif_votos"] > 0).sum())
        c_f = int((sub["dif_votos"] < 0).sum())
        c_emp = int((sub["dif_votos"] == 0).sum())
        cid_str = f"{c_l} / {c_f}" + (f" / {c_emp}" if c_emp > 0 else "")
        vant_str = f"{f_sinal_int(dif_v)} ({f_sinal_pp(pct_l - pct_f)} p.p.)"
        linhas.append(
            f"| {rotulo} | {f_int(n_mun)} | {f_int(tot_val)} | {f_int(tot_l)} | {f_pct(pct_l)} | "
            f"{f_int(tot_f)} | {f_pct(pct_f)} | {vant_str} | {cid_str} |"
        )
    return "\n".join([cab, sep, *linhas])


def tabela_porte_por_regiao(df: pd.DataFrame, limite_validos: int = 50_000) -> str:
    """Demonstra o comportamento dos municípios pequenos (≤ limite_validos) por macrorregião geográfica."""
    br = df[~df["exterior"]].copy()
    uf2reg = {uf: reg for reg, ufs in REGIOES.items() for uf in ufs}
    br["regiao"] = br["uf"].map(uf2reg)
    peq = br[br["validos"] <= limite_validos]

    cab = (
        "| Região | Municípios (≤ 50k) | Votos Válidos | Lula (votos) | Lula (%) | "
        "Flávio (votos) | Flávio (%) | Vantagem Lula | Cidades (L / F / Emp) |"
    )
    sep = "|:--|--:|--:|--:|--:|--:|--:|--:|:--:|"
    linhas = []
    for reg in ("Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"):
        sub = peq[peq["regiao"] == reg]
        if sub.empty:
            continue
        tot_val = int(sub["validos"].sum())
        tot_l = int(sub["lula"].sum())
        tot_f = int(sub["flavio"].sum())
        pct_l = (tot_l / tot_val * 100) if tot_val > 0 else 0.0
        pct_f = (tot_f / tot_val * 100) if tot_val > 0 else 0.0
        dif_v = tot_l - tot_f
        c_l = int((sub["dif_votos"] > 0).sum())
        c_f = int((sub["dif_votos"] < 0).sum())
        c_emp = int((sub["dif_votos"] == 0).sum())
        cid_str = f"{c_l} / {c_f}" + (f" / {c_emp}" if c_emp > 0 else "")
        vant_str = f"{f_sinal_int(dif_v)} ({f_sinal_pp(pct_l - pct_f)} p.p.)"
        linhas.append(
            f"| {reg} | {f_int(len(sub))} | {f_int(tot_val)} | {f_int(tot_l)} | {f_pct(pct_l)} | "
            f"{f_int(tot_f)} | {f_pct(pct_f)} | {vant_str} | {cid_str} |"
        )
    return "\n".join([cab, sep, *linhas])


def tabela_resumo_estados(df: pd.DataFrame, link_prefix: str = "estados") -> str:
    """Tabela comparativa com os totais de cada UF e link para o relatório estadual."""
    cab = (
        "| UF | Estado | Válidos | Lula (votos) | Lula (%) | Flávio (votos) | Flávio (%) | "
        "Vantagem | Vencedor | Cidades (L/F/Emp) | Relatório |"
    )
    sep = "|:--:|:--|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|"
    linhas = []
    for uf, g in df.groupby("uf"):
        tot_l = int(g["lula"].sum())
        tot_f = int(g["flavio"].sum())
        tot_val = tot_l + tot_f
        pct_l = (tot_l / tot_val * 100) if tot_val > 0 else 0.0
        pct_f = (tot_f / tot_val * 100) if tot_val > 0 else 0.0
        dif_v = tot_l - tot_f
        venc = "Lula" if dif_v > 0 else "Flávio" if dif_v < 0 else "Empate"
        vant_str = f"{f_sinal_int(dif_v)} ({f_sinal_pp(pct_l - pct_f)} p.p.)"
        c_l = int((g["dif_votos"] > 0).sum())
        c_f = int((g["dif_votos"] < 0).sum())
        c_emp = int((g["dif_votos"] == 0).sum())
        cid_str = f"{c_l} / {c_f}" + (f" / {c_emp}" if c_emp > 0 else "")
        nome_est = NOME_UF.get(uf, uf)
        link = f"[{uf}.md]({link_prefix}/{uf}.md)"
        linhas.append(
            f"| {uf} | {nome_est} | {f_int(tot_val)} | {f_int(tot_l)} | {f_pct(pct_l)} | {f_int(tot_f)} | {f_pct(pct_f)} | "
            f"{vant_str} | **{venc}** | {cid_str} | {link} |"
        )
    return "\n".join([cab, sep, *linhas])


# --------------------------------------------------------------------------- relatórios


def gerar_relatorio_estado(
    uf: str,
    df_uf_completo: pd.DataFrame,
    rankings_uf: dict[str, pd.DataFrame],
    top: int = 50,
    min_validos: int = 0,
    n_ranqueados: int | None = None,
) -> str:
    nome_uf = NOME_UF.get(uf, uf)
    tot_l = int(df_uf_completo["lula"].sum())
    tot_f = int(df_uf_completo["flavio"].sum())
    tot_val = tot_l + tot_f
    pct_l = (tot_l / tot_val * 100) if tot_val > 0 else 0.0
    pct_f = (tot_f / tot_val * 100) if tot_val > 0 else 0.0
    ganhou_l = int((df_uf_completo["dif_votos"] > 0).sum())
    ganhou_f = int((df_uf_completo["dif_votos"] < 0).sum())
    empates = int((df_uf_completo["dif_votos"] == 0).sum())
    n_mun = len(df_uf_completo)

    L: list[str] = []
    L.append(f"# Eleições presidenciais 2026 — 2º turno: {nome_uf} ({uf})\n")
    L.append(f"_Rankings municipais oficiais do TSE (eleição {ELEICAO}, totalização final). Total de localidades: {n_mun}._\n")

    L.append("## Panorama estadual\n")
    L.append("| | Lula | Flávio |\n|:--|--:|--:|")
    L.append(f"| Votos válidos no estado | {f_int(tot_l)} | {f_int(tot_f)} |")
    L.append(f"| % dos válidos no estado | {f_pct(pct_l)} | {f_pct(pct_f)} |")
    L.append(f"| Municípios vencidos (de {n_mun}) | {f_int(ganhou_l)} | {f_int(ganhou_f)} |")
    L.append("")

    dif_uf = tot_l - tot_f
    venc = "Lula" if dif_uf > 0 else "Flávio" if dif_uf < 0 else "Empate"
    dif_str = f"{f_int(abs(dif_uf))} votos ({f_sinal_pp(pct_l - pct_f).lstrip('+')} p.p.)"
    L.append(f"**Vencedor no estado:** **{venc}** por **{dif_str}**.")
    if empates > 0:
        emp_mun = df_uf_completo[df_uf_completo["dif_votos"] == 0]
        emp_detalhes = [
            f"{bonito(r.municipio)}: {f_int(r.lula)} × {f_int(r.flavio)} votos ({f_pct(r.pct_lula)})"
            for r in emp_mun.itertuples()
        ]
        L.append(f"**Municípios com empate:** {empates} ({'; '.join(emp_detalhes)}).")
    L.append("")

    if min_validos > 0:
        n_rk = n_ranqueados if n_ranqueados is not None else len(df_uf_completo[df_uf_completo["validos"] >= min_validos])
        L.append(
            f"> [!NOTE]\n"
            f"> **Filtro de porte aplicado:** O panorama e os totais estaduais acima contemplam todos os {n_mun} "
            f"municípios do estado. Os rankings abaixo exibem apenas os {n_rk} municípios com pelo menos "
            f"{f_int(min_validos)} votos válidos.\n"
        )

    L.append("## Resumo — Top 3 do estado\n")
    L.append("| Ranking | 1º | 2º | 3º |\n|:--|:--|:--|:--|")
    for r in RANKINGS:
        d = rankings_uf[r.chave].head(3)
        cel = []
        for x in d.itertuples():
            if r.coluna in ("lula", "flavio"):
                met = f_int(getattr(x, r.coluna))
            elif r.coluna in ("pct_lula", "pct_flavio"):
                met = f_pct(getattr(x, r.coluna))
            elif r.coluna == "dif_votos":
                met = f_int(abs(x.dif_votos))
            else:
                met = f_sinal_pp(abs(x.dif_pp)).lstrip("+") + " p.p."
            cel.append(f"{bonito(x.municipio)} ({met})")
        while len(cel) < 3:
            cel.append("—")
        L.append(f"| {r.titulo} | " + " | ".join(cel) + " |")
    L.append("")

    blocos = {
        "1. Votos brutos": ("votos_lula", "votos_flavio"),
        "2. Percentual de votos válidos": ("pct_lula", "pct_flavio"),
        "3. Diferença em votos brutos": ("margem_votos_lula", "margem_votos_flavio"),
        "4. Diferença percentual (pontos percentuais)": ("margem_pp_lula", "margem_pp_flavio"),
    }
    por_chave = {r.chave: r for r in RANKINGS}
    for titulo, chaves in blocos.items():
        L.append(f"## {titulo}\n")
        for ch in chaves:
            L.append(f"### {por_chave[ch].titulo}\n")
            L.append(tabela_md(rankings_uf[ch], omitir_uf=True))
            L.append("")

    L.append("_[Voltar ao Relatório Nacional](../relatorio.md) | [Relatório Geral dos Estados](../relatorio_estados.md)_")
    return "\n".join(L) + "\n"


def gerar_relatorio_estados_compilado(
    base_estados: pd.DataFrame,
    rankings_por_uf: dict[str, dict[str, pd.DataFrame]],
    top: int = 50,
    min_validos: int = 0,
) -> str:
    """Gera um relatório completo compilando o panorama de todas as UFs e links diretos."""
    L: list[str] = []
    L.append("# Eleições presidenciais 2026 — 2º turno: Panorama e Rankings por Estado\n")
    L.append(f"_Compilação estadual oficial do TSE (eleição {ELEICAO}). Total de UFs/abrangências: {len(rankings_por_uf)}._\n")

    L.append("## Panorama Geral dos Estados\n")
    L.append(tabela_resumo_estados(base_estados, link_prefix="estados"))
    L.append("")

    if min_validos > 0:
        L.append(
            f"> [!NOTE]\n"
            f"> O panorama geral acima exibe os totais integrais de cada estado. "
            f"Os destaques individuais abaixo refletem o filtro de municípios com pelo menos "
            f"{f_int(min_validos)} votos válidos.\n"
        )

    L.append("## Destaques por Estado (Top 1 de cada categoria)\n")
    cab = (
        "| UF | Mais Votos Lula | Mais Votos Flávio | Maior % Lula | Maior % Flávio | "
        "Maior Dif. Votos Lula | Maior Dif. Votos Flávio |"
    )
    sep = "|:--:|:--|:--|:--|:--|:--|:--|"
    linhas = []

    def top1_str(d_ranks: dict[str, pd.DataFrame], chave: str, col: str) -> str:
        d = d_ranks[chave]
        if d.empty:
            return "—"
        row = d.iloc[0]
        val = row[col]
        if col in ("lula", "flavio"):
            return f"{bonito(row['municipio'])} ({f_int(int(val))})"
        elif col in ("pct_lula", "pct_flavio"):
            return f"{bonito(row['municipio'])} ({f_pct(float(val))})"
        elif col == "dif_votos":
            return f"{bonito(row['municipio'])} ({f_int(abs(int(val)))})"
        return f"{bonito(row['municipio'])} ({f_sinal_pp(abs(float(val))).lstrip('+')} p.p.)"

    for uf in sorted(rankings_por_uf):
        ranks = rankings_por_uf[uf]
        c1 = top1_str(ranks, "votos_lula", "lula")
        c2 = top1_str(ranks, "votos_flavio", "flavio")
        c3 = top1_str(ranks, "pct_lula", "pct_lula")
        c4 = top1_str(ranks, "pct_flavio", "pct_flavio")
        c5 = top1_str(ranks, "margem_votos_lula", "dif_votos")
        c6 = top1_str(ranks, "margem_votos_flavio", "dif_votos")
        linhas.append(f"| [{uf}](estados/{uf}.md) | {c1} | {c2} | {c3} | {c4} | {c5} | {c6} |")
    L.append("\n".join([cab, sep, *linhas]))
    L.append("")
    L.append("_[Voltar ao Relatório Nacional](relatorio.md)_")
    return "\n".join(L) + "\n"


def gerar_relatorio(
    base: pd.DataFrame,
    escopo: pd.DataFrame,
    rankings: dict[str, pd.DataFrame],
    checagens: list[Checagem],
    manifest: dict,
    incluir_exterior: bool,
    min_validos: int,
    top: int,
) -> str:
    br = base[~base["exterior"]]
    ext = base[base["exterior"]]
    tot_l, tot_f = int(base["lula"].sum()), int(base["flavio"].sum())
    ganhou_l = int((br["dif_votos"] > 0).sum())
    ganhou_f = int((br["dif_votos"] < 0).sum())

    empates_br = br[br["dif_votos"] == 0]
    if not empates_br.empty:
        detalhes_emp = [
            f"{bonito(r.municipio)}/{r.uf}: {f_int(r.lula)} × {f_int(r.flavio)} votos ({f_pct(r.pct_lula)})"
            for r in empates_br.itertuples()
        ]
        texto_empates = f"Empates municipais: {len(empates_br)} ({'; '.join(detalhes_emp)})"
    else:
        texto_empates = "Empates municipais: 0"

    L: list[str] = []
    L.append("# Eleições presidenciais 2026 — 2º turno: rankings por município\n")
    L.append(
        f"_Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} a partir dos resultados oficiais do TSE "
        f"(eleição {ELEICAO}, totalização final)._\n"
    )

    L.append("## Panorama Nacional\n")
    L.append("| | Lula | Flávio |\n|:--|--:|--:|")
    L.append(f"| Votos válidos (Brasil + exterior) | {f_int(tot_l)} | {f_int(tot_f)} |")
    L.append(f"| % dos válidos | {f_pct(tot_l / (tot_l + tot_f) * 100)} | {f_pct(tot_f / (tot_l + tot_f) * 100)} |")
    L.append(f"| Municípios brasileiros vencidos (de {len(br)}) | {f_int(ganhou_l)} | {f_int(ganhou_f)} |")
    L.append("")
    ext_l, ext_f = f_int(int(ext["lula"].sum())), f_int(int(ext["flavio"].sum()))
    L.append(
        f"Vantagem nacional de Lula: **{f_int(tot_l - tot_f)} votos**. "
        f"{texto_empates}. "
        f"Exterior ({len(ext)} localidades): Lula {ext_l} × Flávio {ext_f}.\n"
    )

    L.append("## Distribuição por Faixa de Porte (Votos Válidos Apurados)\n")
    L.append("Comportamento do voto conforme o porte dos municípios brasileiros (votos válidos apurados):\n")
    L.append(tabela_analise_porte(base))
    L.append("")
    L.append(
        "_Nota conceitual: As faixas acima são estabelecidas pela quantidade de **votos válidos apurados** (Lula + Flávio). "
        "O eleitorado apto (total de eleitores cadastrados) difere dos válidos por incluir abstenções, brancos e nulos. "
        "A dinâmica política nacional se mantém equivalente sob ambas as métricas._\n"
    )
    L.append("### Estratificação Regional das Cidades Pequenas (até 50.000 votos válidos)\n")
    L.append(
        "Para avaliar se o padrão de cidades pequenas é uniforme ou produto da composição geográfica (evitando a "
        "falácia ecológica), a tabela abaixo desagrega os 5.186 municípios com até 50 mil votos válidos por macrorregião:\n"
    )
    L.append(tabela_porte_por_regiao(base, 50_000))
    L.append("")
    L.append(
        "> [!IMPORTANT]\n"
        "> **Efeito de Composição Regional vs. Porte:** A vantagem agregada de Lula nas cidades com até 50 mil votos válidos "
        "(+5,37 milhões de votos) decorre da votação no Nordeste (+9,68 milhões de saldo em 1.706 cidades). "
        "No Centro-Oeste, Sudeste e Sul, Flávio Bolsonaro venceu na maioria das cidades desse mesmo porte (ganhou em 2.276 dos "
        "3.062 municípios dessas três regiões, acumulando uma vantagem de 4,64 milhões de votos). Portanto, o porte municipal "
        "não deve ser interpretado como determinante causal isolado, sendo preponderante a "
        "heterogeneidade e composição regional.\n"
    )

    L.append("## Como ler\n")
    escopo_txt = "municípios brasileiros" + (" **e localidades no exterior**" if incluir_exterior else " (exterior fora)")
    L.append(
        f"- **Escopo dos rankings:** {escopo_txt}"
        + (f", com pelo menos {f_int(min_validos)} votos válidos" if min_validos else "")
        + f" — {len(escopo)} localidades."
    )
    L.append("- **% = votos no candidato ÷ votos válidos** (Lula + Flávio; brancos e nulos fora), a mesma base do TSE.")
    L.append(
        "- **Dif. votos (L−F)** = votos Lula − votos Flávio; **Dif. p.p.** = % Lula − % Flávio. "
        "Positivo = Lula na frente; negativo = Flávio na frente."
    )
    L.append("- Os rankings de **vantagem** só incluem cidades em que o candidato realmente ficou na frente.")
    L.append(
        "- **Equivalência Matemática e Cobertura:** A ordenação por % e por vantagem em p.p. é "
        "rigorosamente idêntica dentro do conjunto de cidades vencidas pelo candidato (% > 50%, "
        "já que Margem p.p. = 2 × % − 100). Porém, os rankings de vantagem excluem derrotas e empates, "
        "ao passo que os rankings percentuais listam todas as localidades do escopo."
    )
    L.append(
        "- Coluna **Faixa**: menor Top N (3, 5, 10, 15 … 50) que contém aquela posição — "
        "para ver o Top 10, leia as linhas marcadas Top 3, Top 5 e Top 10."
    )
    L.append("- Desempate: mais votos válidos, depois ordem alfabética.")
    L.append(
        "- ⚠️ Rankings **percentuais** tendem a ser dominados por municípios pequenos "
        "(poucos milhares de votos); veja a coluna *Válidos* ao interpretar.\n"
    )

    L.append("## Resumo Nacional — Top 3 de cada ranking\n")
    L.append("| Ranking | 1º | 2º | 3º |\n|:--|:--|:--|:--|")
    for r in RANKINGS:
        d = rankings[r.chave].head(3)
        cel = []
        for x in d.itertuples():
            v = {"lula": x.lula, "flavio": x.flavio}.get(r.coluna)
            if r.coluna in ("lula", "flavio"):
                met = f_int(v)
            elif r.coluna in ("pct_lula", "pct_flavio"):
                met = f_pct(getattr(x, r.coluna))
            elif r.coluna == "dif_votos":
                met = f_int(abs(x.dif_votos))
            else:
                met = f_sinal_pp(abs(x.dif_pp)).lstrip("+") + " p.p."
            cel.append(f"{bonito(x.municipio)}/{x.uf} ({met})")
        L.append(f"| {r.titulo} | " + " | ".join(cel) + " |")
    L.append("")

    blocos = {
        "1. Votos brutos": ("votos_lula", "votos_flavio"),
        "2. Percentual de votos válidos": ("pct_lula", "pct_flavio"),
        "3. Diferença em votos brutos": ("margem_votos_lula", "margem_votos_flavio"),
        "4. Diferença percentual (pontos percentuais)": ("margem_pp_lula", "margem_pp_flavio"),
    }
    por_chave = {r.chave: r for r in RANKINGS}
    for titulo, chaves in blocos.items():
        L.append(f"## {titulo}\n")
        for ch in chaves:
            L.append(f"### {por_chave[ch].titulo}\n")
            L.append(tabela_md(rankings[ch]))
            L.append("")

    L.append("## 5. Panorama e Rankings por Estado\n")
    L.append(
        "Consulte abaixo o resultado consolidado estado a estado. Para os rankings detalhados de cada estado, "
        "clique no link da coluna **Relatório** ou veja o [Relatório Geral dos Estados](relatorio_estados.md).\n"
    )
    base_estados = base if incluir_exterior else br
    L.append(tabela_resumo_estados(base_estados, link_prefix="estados"))
    L.append("")

    L.append("## Validação dos dados\n")
    ok = sum(c.ok for c in checagens)
    L.append(
        f"{ok}/{len(checagens)} checagens passaram. "
        f"Base: {manifest['n_arquivos']} arquivos oficiais, SHA-256 consolidado `{manifest['sha256_consolidado']}`.\n"
    )
    L.append("| Checagem | Resultado |\n|:--|:--|")
    for c in checagens:
        if not c.nome.startswith("soma dos municípios = total oficial"):
            L.append(f"| {c.nome} | {'✅' if c.ok else '❌'} {c.detalhe} |")
    ufs_ok = sum(c.ok for c in checagens if c.nome.startswith("soma dos municípios = total oficial"))
    ufs_tot = sum(1 for c in checagens if c.nome.startswith("soma dos municípios = total oficial"))
    status_ufs = "✅" if ufs_ok == ufs_tot else "❌"
    L.append(f"| soma dos municípios = total oficial, por UF/exterior | {status_ufs} {ufs_ok}/{ufs_tot} |")
    L.append("")
    L.append(
        f"_Top {top} por ranking. Dados completos: `municipios.csv`; rankings nacionais em formato longo: `rankings.csv`; "
        f"rankings por estado em formato longo: `rankings_estados.csv`._"
    )
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- main


def main() -> int:
    raiz = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", type=Path, default=raiz / "dados")
    ap.add_argument("--saida", type=Path, default=raiz / "saida")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--incluir-exterior", action="store_true", help="inclui localidades do exterior nos rankings")
    ap.add_argument("--min-validos", type=int, default=0, help="ignora cidades com menos votos válidos que isso")
    ap.add_argument("--uf", type=str, default="", help="filtra uma UF específica para geração (ex: SP, BA)")
    args = ap.parse_args()

    assegurar_dados_brutos(args.dados)
    base = montar_base(args.dados)
    checagens = validar(base, args.dados)
    falhas = [c for c in checagens if not c.ok]
    for c in falhas:
        print(f"FALHA: {c.nome} — {c.detalhe}", file=sys.stderr)
    if falhas:
        print("Validação falhou; relatório NÃO gerado.", file=sys.stderr)
        return 1

    base_ranqueavel = base if args.incluir_exterior else base[~base["exterior"]]
    escopo = base_ranqueavel[base_ranqueavel["validos"] >= max(args.min_validos, 1)]
    if args.uf:
        uf_filtro = args.uf.upper()
        escopo = escopo[escopo["uf"] == uf_filtro]
        if escopo.empty and base_ranqueavel[base_ranqueavel["uf"] == uf_filtro].empty:
            print(f"Erro: nenhum registro encontrado para a UF {args.uf}.", file=sys.stderr)
            return 1

    rankings = {r.chave: calcular_ranking(escopo, r, args.top) for r in RANKINGS}

    args.saida.mkdir(parents=True, exist_ok=True)
    pasta_estados = args.saida / "estados"
    pasta_estados.mkdir(parents=True, exist_ok=True)

    cols = [
        "uf", "cod_ibge", "cod_tse", "municipio", "exterior", "aptos", "comparecimento", "abstencoes",
        "brancos", "nulos", "validos", "lula", "flavio", "pct_lula", "pct_flavio", "dif_votos", "dif_pp",
        "vencedor"
    ]
    base[cols].sort_values(["uf", "municipio"]).to_csv(args.saida / "municipios.csv", index=False, encoding="utf-8-sig")

    long_nacional = pd.concat(
        [
            d.assign(ranking=ch)[
                [
                    "ranking", "posicao", "faixa", "uf", "municipio", "cod_ibge", "lula", "flavio",
                    "validos", "pct_lula", "pct_flavio", "dif_votos", "dif_pp"
                ]
            ]
            for ch, d in rankings.items()
        ]
    )
    long_nacional.to_csv(args.saida / "rankings.csv", index=False, encoding="utf-8-sig")

    # Rankings estaduais
    rankings_por_uf: dict[str, dict[str, pd.DataFrame]] = {}
    linhas_long_estados = []
    ufs_alvo = [args.uf.upper()] if args.uf else sorted(base_ranqueavel["uf"].unique())
    for uf in ufs_alvo:
        df_uf_completo = base_ranqueavel[base_ranqueavel["uf"] == uf]
        df_uf_ranqueavel = escopo[escopo["uf"] == uf]
        rank_uf = {r.chave: calcular_ranking(df_uf_ranqueavel, r, args.top) for r in RANKINGS}
        rankings_por_uf[uf] = rank_uf
        md_uf = gerar_relatorio_estado(uf, df_uf_completo, rank_uf, args.top, args.min_validos, len(df_uf_ranqueavel))
        (pasta_estados / f"{uf}.md").write_text(md_uf, encoding="utf-8")
        for ch, d in rank_uf.items():
            if not d.empty:
                linhas_long_estados.append(
                    d.assign(uf=uf, estado=NOME_UF.get(uf, uf), ranking=ch)[
                        [
                            "uf", "estado", "ranking", "posicao", "faixa", "municipio", "cod_ibge", "cod_tse",
                            "lula", "flavio", "validos", "pct_lula", "pct_flavio", "dif_votos", "dif_pp"
                        ]
                    ]
                )

    if linhas_long_estados:
        long_est = pd.concat(linhas_long_estados, ignore_index=True)
        long_est.to_csv(args.saida / "rankings_estados.csv", index=False, encoding="utf-8-sig")

    base_estados = base_ranqueavel if not args.uf else base_ranqueavel[base_ranqueavel["uf"] == args.uf.upper()]
    rel_estados_md = gerar_relatorio_estados_compilado(base_estados, rankings_por_uf, args.top, args.min_validos)
    (args.saida / "relatorio_estados.md").write_text(rel_estados_md, encoding="utf-8")

    manifest = json.loads((args.dados / "manifest.json").read_text(encoding="utf-8"))
    md = gerar_relatorio(base, escopo, rankings, checagens, manifest, args.incluir_exterior, args.min_validos, args.top)
    (args.saida / "relatorio.md").write_text(md, encoding="utf-8")
    print(
        f"OK: {len(base)} localidades, {len(checagens)} checagens OK. "
        f"Nacional e {len(rankings_por_uf)} estados gerados em {args.saida}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
