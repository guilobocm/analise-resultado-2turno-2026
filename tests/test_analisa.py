"""Testes da lógica de parsing, ranking e validação (sem rede)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import analisa as a

FIXTURE = Path(__file__).parent / "fixtures" / "ac01120.json"  # Acrelândia/AC, resultado real do TSE


def test_parse_municipio_real_acrelandia():
    r = a.parse_municipio(a.ler_json(FIXTURE))
    assert (r["lula"], r["flavio"], r["validos"]) == (1647, 5751, 7398)
    assert r["brancos"] == 57 and r["nulos"] == 258
    assert r["comparecimento"] == 7713 == r["validos"] + r["brancos"] + r["nulos"]
    assert r["totalizacao_final"] is True
    assert r["pct_lula_tse"] == pytest.approx(1647 / 7398 * 100, abs=1e-6)


def test_parse_rejeita_candidatos_inesperados():
    j = a.ler_json(FIXTURE)
    j["carg"][0]["agr"][0]["par"][0]["cand"][0]["n"] = "99"
    with pytest.raises(ValueError, match="candidatos inesperados"):
        a.parse_municipio(j)


def test_parse_rejeita_outro_cargo():
    j = a.ler_json(FIXTURE)
    j["carg"][0]["cd"] = "3"
    with pytest.raises(ValueError, match="cargo inesperado"):
        a.parse_municipio(j)


def _df(linhas):
    df = pd.DataFrame(linhas, columns=["municipio", "uf", "lula", "flavio"])
    df["validos"] = df["lula"] + df["flavio"]
    df["pct_lula"] = df["lula"] / df["validos"] * 100
    df["pct_flavio"] = df["flavio"] / df["validos"] * 100
    df["dif_votos"] = df["lula"] - df["flavio"]
    df["dif_pp"] = df["pct_lula"] - df["pct_flavio"]
    df["exterior"] = df["uf"] == "ZZ"
    return df


R = {r.chave: r for r in a.RANKINGS}


def test_ranking_votos_brutos_e_ordem():
    df = _df([("A", "SP", 100, 50), ("B", "SP", 300, 10), ("C", "BA", 200, 400)])
    assert list(a.calcular_ranking(df, R["votos_lula"])["municipio"]) == ["B", "C", "A"]
    assert list(a.calcular_ranking(df, R["votos_flavio"])["municipio"]) == ["C", "A", "B"]


def test_ranking_margem_so_inclui_quem_ficou_na_frente():
    df = _df([("A", "SP", 100, 50), ("B", "SP", 30, 10), ("C", "BA", 200, 400), ("D", "RJ", 5, 5)])
    lula = a.calcular_ranking(df, R["margem_votos_lula"])
    flavio = a.calcular_ranking(df, R["margem_votos_flavio"])
    assert list(lula["municipio"]) == ["A", "B"]  # C perdeu, D empatou
    assert list(flavio["municipio"]) == ["C"]
    assert list(a.calcular_ranking(df, R["margem_pp_flavio"])["municipio"]) == ["C"]


def test_ranking_percentual_e_margem_pp_ordenam_diferente_de_votos():
    df = _df([("Grande", "SP", 600_000, 400_000), ("Pequena", "PI", 900, 100)])
    assert a.calcular_ranking(df, R["pct_lula"]).iloc[0]["municipio"] == "Pequena"
    assert a.calcular_ranking(df, R["margem_votos_lula"]).iloc[0]["municipio"] == "Grande"
    assert a.calcular_ranking(df, R["margem_pp_lula"]).iloc[0]["municipio"] == "Pequena"


def test_desempate_por_validos_depois_nome():
    df = _df([("Zeta", "SP", 10, 10), ("Alfa", "SP", 5, 5), ("Beta", "SP", 5, 5)])
    # mesmo pct_lula (50%): mais válidos primeiro; entre iguais, ordem alfabética
    assert list(a.calcular_ranking(df, R["pct_lula"])["municipio"]) == ["Zeta", "Alfa", "Beta"]


def test_faixas_top():
    assert [a.faixa(p) for p in (1, 3, 4, 5, 6, 10, 11, 50, 51)] == [3, 3, 5, 5, 10, 10, 15, 50, None]
    df = _df([(f"M{i:02d}", "SP", 1000 - i, 1) for i in range(60)])
    d = a.calcular_ranking(df, R["votos_lula"], top=50)
    assert len(d) == 50
    assert d.loc[0, "faixa"] == "Top 3" and d.loc[3, "faixa"] == "Top 5" and d.loc[49, "faixa"] == "Top 50"


def test_cidades_sem_votos_validos_sao_ignoradas():
    df = _df([("A", "SP", 10, 5), ("Vazia", "SP", 0, 0)]).fillna(0)
    d = a.calcular_ranking(df, R["votos_lula"])
    assert list(d["municipio"]) == ["A"]


def test_formatacao_pt_br():
    assert a.f_int(1234567) == "1.234.567"
    assert a.f_pct(55.3) == "55,30%"
    assert a.f_sinal_int(-2500) == "−2.500" and a.f_sinal_int(10) == "+10"
    assert a.bonito("SÃO JOSÉ DOS CAMPOS") == "São José dos Campos"
    assert a.bonito("PORTO DE PEDRAS") == "Porto de Pedras"


def test_validar_detecta_total_divergente(tmp_path):
    reg = a.parse_municipio(a.ler_json(FIXTURE))
    base = pd.DataFrame([{"uf": "AC", "cod_tse": "01120", **reg}])
    base["pct_lula"] = base["lula"] / base["validos"] * 100
    base["pct_flavio"] = base["flavio"] / base["validos"] * 100
    pasta = tmp_path / "raw" / "_totais"
    pasta.mkdir(parents=True)
    j = json.loads(FIXTURE.read_bytes().decode("utf-8-sig"))
    (pasta / "ac.json").write_text(json.dumps(j), encoding="utf-8")
    (pasta / "br.json").write_text(json.dumps(j), encoding="utf-8")
    assert all(c.ok for c in a.validar(base, tmp_path))

    # adultera o total oficial da UF: a validação precisa acusar
    j["carg"][0]["agr"][0]["par"][0]["cand"][0]["vap"] = "5750"
    (pasta / "ac.json").write_text(json.dumps(j), encoding="utf-8")
    falhas = [c for c in a.validar(base, tmp_path) if not c.ok]
    assert any("AC" in c.nome for c in falhas)


def test_tabela_md_omitir_uf_e_vazia():
    vazia = pd.DataFrame(columns=["posicao", "faixa", "municipio", "uf", "lula", "flavio", "validos",
                                  "pct_lula", "pct_flavio", "dif_votos", "dif_pp"])
    assert "Nenhum município" in a.tabela_md(vazia)

    df = _df([("A", "SP", 100, 50)])
    rank = a.calcular_ranking(df, R["votos_lula"])
    t_uf = a.tabela_md(rank, omitir_uf=False)
    t_sem_uf = a.tabela_md(rank, omitir_uf=True)
    assert "| UF |" in t_uf
    assert "| UF |" not in t_sem_uf
    assert "A" in t_sem_uf


def test_gerar_relatorio_estado():
    df = _df([("Campinas", "SP", 300, 400), ("Santos", "SP", 200, 100)])
    ranks = {r.chave: a.calcular_ranking(df, r) for r in a.RANKINGS}
    md = a.gerar_relatorio_estado("SP", df, ranks)
    assert "São Paulo (SP)" in md
    assert "Campinas" in md and "Santos" in md
    assert "Panorama estadual" in md


def test_relatorio_estado_nao_distorce_totais_com_min_validos():
    df_completo = _df([("Pequena", "SP", 1000, 2000), ("Grande", "SP", 30000, 20000)])
    df_ranqueavel = df_completo[df_completo["validos"] >= 10000]
    ranks = {r.chave: a.calcular_ranking(df_ranqueavel, r) for r in a.RANKINGS}

    md = a.gerar_relatorio_estado("SP", df_completo, ranks, top=50, min_validos=10000, n_ranqueados=len(df_ranqueavel))

    # Totais no panorama devem ser 1.000 + 30.000 = 31.000 (Lula) e 2.000 + 20.000 = 22.000 (Flávio)
    assert "31.000" in md
    assert "22.000" in md
    assert "9.000 votos" in md
    assert "Total de localidades: 2" in md
    assert "Filtro de porte aplicado" in md
    assert "10.000" in md
    # Apenas Grande deve constar no ranking gerado
    assert "Grande" in md
    assert "Pequena" not in md


def test_verificar_manifesto(tmp_path):
    import hashlib

    raw = tmp_path / "raw"
    raw.mkdir()
    f1 = raw / "a.json"
    conteudo = b'{"teste": 1}'
    f1.write_bytes(conteudo)
    h1 = hashlib.sha256(conteudo).hexdigest()
    arquivos = [{"arquivo": "raw/a.json", "bytes": len(conteudo), "sha256": h1}]
    sha_cons = hashlib.sha256(f"raw/a.json:{h1}".encode()).hexdigest()
    manifest = {
        "fonte": "tse",
        "eleicao": "6258",
        "gerado_em": "2026-10-26T00:00:00Z",
        "n_arquivos": 1,
        "sha256_consolidado": sha_cons,
        "arquivos": arquivos,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    chk = a.verificar_manifesto(tmp_path)
    assert chk.ok is True

    # Adultera o arquivo: o validador precisa acusar
    f1.write_bytes(b'{"teste": 2}')
    chk_adulterado = a.verificar_manifesto(tmp_path)
    assert chk_adulterado.ok is False
    assert "falhas" in chk_adulterado.detalhe


def test_assegurar_dados_brutos_extrai_zip(tmp_path):
    import zipfile

    zip_path = tmp_path / "tse_2turno_2026_raw.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("raw/teste.json", '{"ok": true}')

    a.assegurar_dados_brutos(tmp_path)
    assert (tmp_path / "raw" / "teste.json").exists()


def test_empates_descobertos_dinamicamente():
    # Caso 1: sem empate
    df_sem_empate = _df([("A", "SP", 100, 200), ("B", "MG", 300, 100)])
    ranks1 = {r.chave: a.calcular_ranking(df_sem_empate, r) for r in a.RANKINGS}
    md1 = a.gerar_relatorio(
        df_sem_empate, df_sem_empate, ranks1, [], {"n_arquivos": 0, "sha256_consolidado": ""},
        incluir_exterior=False, min_validos=0, top=50
    )
    assert "Empates municipais: 0" in md1

    # Caso 2: com empate descoberto nos dados
    df_com_empate = _df([("Empatada", "PR", 1530, 1530), ("Vencedora", "SC", 500, 200)])
    ranks2 = {r.chave: a.calcular_ranking(df_com_empate, r) for r in a.RANKINGS}
    md2 = a.gerar_relatorio(
        df_com_empate, df_com_empate, ranks2, [], {"n_arquivos": 0, "sha256_consolidado": ""},
        incluir_exterior=False, min_validos=0, top=50
    )
    assert "Empates municipais: 1 (Empatada/PR: 1.530 × 1.530 votos (50,00%))" in md2


def test_tabela_analise_porte():
    df = _df([
        ("Pequena", "SP", 4000, 3000),       # 7k válidos -> Até 10.000
        ("Media", "BA", 12000, 8000),        # 20k válidos -> 10.001 a 50.000
        ("Metropole", "RJ", 400000, 300000)  # 700k válidos -> Mais de 500.000
    ])
    tab = a.tabela_analise_porte(df)
    assert "Até 10.000 válidos" in tab
    assert "10.001 a 50.000 válidos" in tab
    assert "Mais de 500.000 válidos" in tab
    assert "7.000" in tab and "20.000" in tab and "700.000" in tab


