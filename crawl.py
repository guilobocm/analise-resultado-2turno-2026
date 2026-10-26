"""Baixa os resultados oficiais do TSE (Presidente, 2º turno, 25/10/2026) por município.

Fonte: https://resultados.tse.jus.br/oficial/ele2026/6258/
  - config/mun-e006258-cm.json                       -> lista de municípios (UF, código TSE, código IBGE, nome)
  - dados/<uf>/<uf><cod_tse>-c0001-e006258-u.json     -> resultado do município
  - dados/br/br-c0001-e006258-u.json, dados/<uf>/<uf>-c0001-e006258-u.json -> totais (usados só p/ validação)

Características:
  * retomável: arquivos já baixados e válidos são reaproveitados;
  * limitador de taxa + retry com backoff exponencial e jitter;
  * só aceita resultado com totalização final (`tf == "s"`);
  * grava `dados/manifest.json` com SHA-256 de cada arquivo (reprodutibilidade/auditoria).

Uso:  python crawl.py [--rps 10] [--workers 16] [--out dados]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

ELEICAO = "6258"  # Presidente, 2º turno (cdt2 da eleição 6257 no ele-c.json do TSE)
CARGO = "0001"
BASE = f"https://resultados.tse.jus.br/oficial/ele2026/{ELEICAO}"
SUFIXO = f"c{CARGO}-e{int(ELEICAO):06d}-u.json"
USER_AGENT = "Mozilla/5.0 (analise-resultado-2turno-2026)"


class Limiter:
    """Limitador de taxa global (requisições/segundo), thread-safe, com redução em caso de 403/429."""

    def __init__(self, rps: float) -> None:
        self.rps = rps
        self._lock = threading.Lock()
        self._next = time.monotonic()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(self._next, now)
            self._next = slot + 1 / self.rps
        delay = slot - now
        if delay > 0:
            time.sleep(delay)

    def slow_down(self) -> None:
        with self._lock:
            self.rps = max(2.0, self.rps * 0.7)
            self._next = time.monotonic() + 20
        log(f"backoff: rps={self.rps:.1f}")


_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(time.strftime("%H:%M:%S"), msg, flush=True)


def http_get(url: str, limiter: Limiter, tentativas: int = 8) -> bytes:
    """GET com retry/backoff exponencial + jitter. 404 não é repetido."""
    for i in range(tentativas):
        limiter.wait()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            if e.code in (403, 429):
                limiter.slow_down()
        except Exception:  # timeout, reset, DNS...
            if i >= 2:
                limiter.slow_down()
        time.sleep(min(60, 2**i) + random.random())
    raise RuntimeError(f"falhou após {tentativas} tentativas: {url}")


def decodificar(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8-sig"))


def url_municipio(uf: str, cod_tse: str) -> str:
    return f"{BASE}/dados/{uf}/{uf}{cod_tse}-{SUFIXO}"


def valida_municipio(j: dict, cod_tse: str) -> None:
    """Rejeita respostas que não sejam o resultado final do município esperado."""
    if j.get("ele") != ELEICAO or j.get("tpabr") != "mu" or j.get("cdabr") != cod_tse:
        raise ValueError(f"arquivo não corresponde ao município {cod_tse}")
    if j.get("tf") != "s":
        raise ValueError(f"município {cod_tse} sem totalização final (tf={j.get('tf')!r})")


def listar_municipios(limiter: Limiter, out: Path) -> list[dict]:
    raw = http_get(f"{BASE}/config/mun-e{int(ELEICAO):06d}-cm.json", limiter)
    cfg_path = out / "raw" / "_config" / "municipios.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_bytes(raw)
    cfg = decodificar(raw)
    return [
        {"uf": uf["cd"], "cod_tse": m["cd"], "cod_ibge": m.get("cdi", ""), "nome": m["nm"]}
        for uf in cfg["abr"]
        for m in uf["mu"]
    ]


def baixar_municipio(m: dict, limiter: Limiter, out: Path) -> str:
    destino = out / "raw" / m["uf"] / f"{m['uf']}{m['cod_tse']}.json"
    if destino.exists():
        try:
            valida_municipio(decodificar(destino.read_bytes()), m["cod_tse"])
            return "cache"
        except Exception:
            destino.unlink()  # corrompido/incompleto: baixa de novo
    raw = http_get(url_municipio(m["uf"], m["cod_tse"]), limiter)
    valida_municipio(decodificar(raw), m["cod_tse"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(destino)  # escrita atômica
    return "baixado"


def baixar_totais(ufs: list[str], limiter: Limiter, out: Path) -> None:
    """Totais oficiais do Brasil e de cada UF (só para validação cruzada)."""
    pasta = out / "raw" / "_totais"
    pasta.mkdir(parents=True, exist_ok=True)
    for abr in ["br", *ufs]:
        raw = http_get(f"{BASE}/dados/{abr}/{abr}-{SUFIXO}", limiter)
        (pasta / f"{abr}.json").write_bytes(raw)


def escrever_manifest(out: Path) -> None:
    arquivos = []
    for p in sorted((out / "raw").rglob("*.json")):
        b = p.read_bytes()
        arquivos.append(
            {"arquivo": p.relative_to(out).as_posix(), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
        )
    consolidado = hashlib.sha256(
        "\n".join(f"{a['arquivo']}:{a['sha256']}" for a in arquivos).encode()
    ).hexdigest()
    manifest = {
        "fonte": BASE,
        "eleicao": ELEICAO,
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_arquivos": len(arquivos),
        "sha256_consolidado": consolidado,
        "arquivos": arquivos,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"manifest: {len(arquivos)} arquivos, sha256 consolidado {consolidado[:16]}…")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "dados")
    ap.add_argument("--rps", type=float, default=10.0, help="requisições por segundo (padrão 10)")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    limiter = Limiter(args.rps)
    municipios = listar_municipios(limiter, args.out)
    ufs = sorted({m["uf"] for m in municipios})
    log(f"{len(municipios)} municípios (inclui exterior) em {len(ufs)} abrangências")

    falhas: list[tuple[dict, str]] = []
    contagem = {"cache": 0, "baixado": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(baixar_municipio, m, limiter, args.out): m for m in municipios}
        for n, fut in enumerate(as_completed(futs), 1):
            m = futs[fut]
            try:
                contagem[fut.result()] += 1
            except Exception as e:  # noqa: BLE001 - registramos e seguimos; falha final é explícita
                falhas.append((m, str(e)))
            if n % 250 == 0 or n == len(municipios):
                log(f"{n}/{len(municipios)} (baixados={contagem['baixado']} cache={contagem['cache']} falhas={len(falhas)})")

    baixar_totais(ufs, limiter, args.out)
    escrever_manifest(args.out)

    if falhas:
        for m, erro in falhas[:20]:
            log(f"FALHA {m['uf']} {m['cod_tse']} {m['nome']}: {erro}")
        log(f"{len(falhas)} município(s) com falha — rode novamente para retomar.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
