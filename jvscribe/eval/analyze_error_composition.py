#!/usr/bin/env python3
"""Composição do erro do ASR: quanto é ATACÁVEL por "corrigir palavra fora do léxico"?

⚠️ O `main()` depende do runtime Rust, REMOVIDO deste repositório em 2026-07-30 (commit
266253f). O módulo fica pela proveniência da medição e porque `normalize_ptbr` continua
importada pelos testes. Ver `eval/eval_runtime_wer.py` para o mesmo caso, documentado.

Testa empiricamente a ideia (Paulo, 2026-07-26): "se a palavra existe em PT-BR não
mexe; se não existe, corrige". Classifica cada erro de substituição do runtime contra
um dicionário PT-BR (hashmap = /usr/share/dict/brazilian ∪ hunspell), medindo:

  - non_word_hyp  : hyp ∉ dict E ref ∈ dict  → ATACÁVEL pelo léxico (o alvo do método)
  - real_word_hyp : hyp ∈ dict E ref ∈ dict  → INATACÁVEL (hyp passa no filtro; erro sobrevive)
  - rare_ref      : ref ∉ dict               → nome próprio/rare (alvo de BIASING, não de léxico)
  - false_flag    : palavra CORRETA porém ∉ dict → risco de CORROMPER (o método a "corrige" sem precisar)

Alinhamento por difflib (stdlib). Transcrição pelo runtime real (macaw-cli). `[MEDIDO]`.

Uso (histórico): ORT_DYLIB_PATH=... python3 jvscribe/eval/analyze_error_composition.py --n 100
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import io
import pathlib
import subprocess
import sys
from collections.abc import Sequence, Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
# `find_test_parquet` era a TERCEIRA cópia da mesma busca no cache do HF — o kernel já a tem,
# e o docstring de lá registra que ela mora no kernel justamente porque `eval/` e `probes/`
# precisam do MESMO test set.
from metrics import escrever_relatorio, find_test_parquet  # noqa: E402
from report import ambiente as ambiente_de_relatorio  # noqa: E402
# Este módulo compara ref×hyp para classificar erro → régua de COMPARAÇÃO (remove acento).
# Rodava a régua de TREINO, que preserva — inflando o erro por acento `[MEDIDO]`.
#
# A régua tem de ser a MESMA nos três usos deste arquivo (léxico, ref, hyp): o léxico é
# consultado com as palavras do hyp já normalizadas. Se o dicionário guardasse acento e o hyp
# não, toda palavra acentuada ficaria inalcançável e um acerto viraria "palavra inexistente"
# — o `false_flag` que esta análise existe justamente para contar.
from text import normalize_for_wer_compare as normalize_ptbr  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "target" / "release" / "macaw-cli"   # runtime removido — ver docstring

CLASSES = ("non_word_hyp", "real_word_hyp", "rare_ref")
_SEED_BOOTSTRAP = 20260726            # data da hipótese; fixa → IC reprodutível
_MIN_UTTERANCES_PARA_IC = 3           # mesma recusa de `common/stats.comparar_pareado`

_AMBIENTE = ambiente_de_relatorio(Path(__file__).resolve().parent / "templates")
_DADOS_BRUTOS = REPO / "wiki" / "medicoes" / "dados-brutos"


def caminho_da_corrida(n: int, *, raiz: Path | None = None) -> Path:
    """Nomeado pelo tamanho da amostra — a única variável livre desta sonda."""
    return (raiz or _DADOS_BRUTOS) / f"composicao-do-erro-n{n}.md"


def classificar(ref_word: str, hyp_word: str, lexico: AbstractSet[str]) -> str:
    """Em qual das três classes cai esta substituição — e portanto que ação ela admite.

    A ORDEM dos testes é a regra, não detalhe: `rare_ref` vem primeiro. Se a referência não
    está no dicionário, o dicionário não é a ferramenta — corrigir por léxico ali destruiria
    uma referência correta. Testar `hyp` antes contaria um par OOV→OOV como "atacável" e a
    sonda superestimaria o ganho do método exatamente onde ele não se aplica.
    """
    if ref_word not in lexico:
        return "rare_ref"          # nome próprio/OOV → alvo de BIASING, não de léxico
    if hyp_word not in lexico:
        return "non_word_hyp"      # ref é palavra, hyp não → ATACÁVEL, o alvo do método
    return "real_word_hyp"         # ambas palavras → o erro passa no filtro, INATACÁVEL


@dataclass(frozen=True)
class Utterance:
    """A **unidade de amostragem** da sonda.

    Guardar por utterance (em vez de somar tudo num `Counter`) é o que torna o IC honesto:
    substituições dentro da mesma utterance são correlacionadas — mesmo locutor, mesmo áudio,
    mesmo contexto. Reamostrá-las como se fossem independentes estreitaria o intervalo
    artificialmente, que é a falácia § 3 #12 com uma casa decimal a mais.
    """

    substituicoes: tuple[str, ...]                 # uma classe por substituição
    pares: tuple[tuple[str, str], ...]             # (ref, hyp) na mesma ordem
    corretas: int
    corretas_fora_do_lexico: int
    falsos_positivos: tuple[str, ...]              # palavras certas que o método "corrigiria"


def analisar(ref: Sequence[str], hyp: Sequence[str],
             lexico: AbstractSet[str]) -> Utterance:
    """Alinha ref×hyp (difflib, stdlib) e classifica cada substituição."""
    subs: list[str] = []
    pares: list[tuple[str, str]] = []
    corretas = fora = 0
    falsos: list[str] = []

    sm = difflib.SequenceMatcher(a=list(ref), b=list(hyp), autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for w in ref[i1:i2]:
                corretas += 1
                if w not in lexico:
                    fora += 1          # acertou, e o método "corrigiria" — dano do lado oposto
                    falsos.append(w)
        elif tag == "replace":
            # zip: alinhamento aproximado par-a-par dentro do bloco substituído
            for rw, hw in zip(ref[i1:i2], hyp[j1:j2]):
                subs.append(classificar(rw, hw, lexico))
                pares.append((rw, hw))
    return Utterance(tuple(subs), tuple(pares), corretas, fora, tuple(falsos))


@dataclass(frozen=True)
class Composicao:
    """Agregado sobre utterances. Nenhum método aqui inventa denominador."""

    utterances: tuple[Utterance, ...]

    @property
    def n_utterances(self) -> int:
        return len(self.utterances)

    @property
    def total_substituicoes(self) -> int:
        return sum(len(u.substituicoes) for u in self.utterances)

    @property
    def corretas(self) -> int:
        return sum(u.corretas for u in self.utterances)

    @property
    def corretas_fora_do_lexico(self) -> int:
        return sum(u.corretas_fora_do_lexico for u in self.utterances)

    def contagem(self, classe: str) -> int:
        return sum(u.substituicoes.count(classe) for u in self.utterances)

    def fracao(self, classe: str) -> float | None:
        """`None` quando não há substituição — **não** zero.

        `max(subs, 1)` devolvia `0.0`, que afirma "medimos e nada é atacável". A ausência de
        dado afirma outra coisa: "não há substituição para classificar". A primeira é falsa, e
        saía sob o rótulo `[MEDIDO]`.
        """
        total = self.total_substituicoes
        return self.contagem(classe) / total if total else None

    def risco_de_falso_positivo(self) -> float | None:
        total = self.corretas
        return self.corretas_fora_do_lexico / total if total else None

    def ic95(self, classe: str, n_boot: int = 2000) -> tuple[float, float] | None:
        """IC95% da fração, reamostrando **utterances** (a unidade de amostragem).

        `None` com menos de 3 utterances: um intervalo sobre duas amostras é aritmética, não
        estatística, e publicado sob `[MEDIDO]` seria pior que a ausência dele.
        """
        if self.n_utterances < _MIN_UTTERANCES_PARA_IC or not self.total_substituicoes:
            return None
        rng = np.random.default_rng(_SEED_BOOTSTRAP)
        acertos = np.array([u.substituicoes.count(classe) for u in self.utterances], dtype=float)
        totais = np.array([len(u.substituicoes) for u in self.utterances], dtype=float)
        idx = rng.integers(0, self.n_utterances, size=(n_boot, self.n_utterances))
        soma_t = totais[idx].sum(axis=1)
        validos = soma_t > 0                       # reamostra sem substituição não informa
        fracoes = acertos[idx].sum(axis=1)[validos] / soma_t[validos]
        if fracoes.size < _MIN_UTTERANCES_PARA_IC:
            return None
        return float(np.percentile(fracoes, 2.5)), float(np.percentile(fracoes, 97.5))

    def exemplos(self, classe: str, limite: int = 8) -> list[str]:
        out: list[str] = []
        for u in self.utterances:
            for cls, (rw, hw) in zip(u.substituicoes, u.pares):
                if cls == classe:
                    out.append(f"{rw}→{hw}")
                    if len(out) >= limite:
                        return out
        return out

    def exemplos_de_falso_positivo(self, limite: int = 8) -> list[str]:
        out: list[str] = []
        for u in self.utterances:
            for w in u.falsos_positivos:
                out.append(w)
                if len(out) >= limite:
                    return out
        return out


def load_lexicon() -> set[str]:
    """O 'hashmap de todas as palavras PT-BR' — wordlists do sistema, normalizadas."""
    words: set[str] = set()
    for p in ["/usr/share/dict/brazilian", "/usr/share/dict/portuguese"]:
        fp = Path(p)
        if fp.exists():
            for enc in ("utf-8", "latin-1"):
                try:
                    for line in fp.read_text(encoding=enc).splitlines():
                        w = normalize_ptbr(line)
                        if w:
                            words.add(w)
                    break
                except UnicodeDecodeError:
                    continue
    return words


ACOES = {
    "non_word_hyp": "ATACÁVEL por léxico",
    "real_word_hyp": "INATACÁVEL — passa no filtro",
    "rare_ref": "BIASING, não léxico",
}


def _cpu_model() -> str:
    try:
        for linha in Path("/proc/cpuinfo").read_text().splitlines():
            if linha.startswith("model name"):
                return linha.split(":", 1)[1].strip()
    except OSError:
        pass
    return "CPU desconhecida"


def render(composicao: Composicao, *, n_lexico: int, cmd: str) -> str:
    """Contexto → Markdown. Nenhuma prosa aqui: ela vive em `templates/`."""
    return _AMBIENTE.get_template("composicao-do-erro.md.j2").render({
        "agora": datetime.datetime.now().isoformat(timespec="seconds"),
        "cpu": _cpu_model(), "cmd": cmd, "n_lexico": n_lexico,
        "n_utterances": composicao.n_utterances,
        "total_substituicoes": composicao.total_substituicoes,
        "corretas": composicao.corretas,
        "corretas_fora_do_lexico": composicao.corretas_fora_do_lexico,
        "risco": composicao.risco_de_falso_positivo(),
        "classes": [
            {"nome": c, "acao": ACOES[c], "n": composicao.contagem(c),
             "fracao": composicao.fracao(c), "ic": composicao.ic95(c),
             "exemplos": composicao.exemplos(c)}
            for c in CLASSES
        ],
        "exemplos_falso_positivo": composicao.exemplos_de_falso_positivo(),
    })


def transcrever(pf, lexico: AbstractSet[str], n: int, tmp: Path) -> Composicao:
    """A ÚNICA parte que precisa do runtime. Isolada para que a ciência acima seja testável."""
    utterances: list[Utterance] = []
    for batch in pf.iter_batches(batch_size=64, columns=["audio", "transcription"]):
        for row in batch.to_pylist():
            if len(utterances) >= n:
                return Composicao(tuple(utterances))
            data, sr = sf.read(io.BytesIO(row["audio"]["bytes"]))
            if data.ndim > 1:
                data = data[:, 0]
            wav = tmp / f"a{len(utterances):03d}.wav"
            sf.write(wav, (np.clip(data, -1, 1) * 32767).astype("int16"), sr, subtype="PCM_16")
            try:
                out = subprocess.run([str(CLI), "transcribe", str(wav)],
                                     capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                continue                      # utterance perdida NÃO entra na amostra
            utterances.append(analisar(
                normalize_ptbr(row["transcription"]).split(),
                normalize_ptbr(out.stdout).split(),
                lexico,
            ))
    return Composicao(tuple(utterances))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--force", action="store_true",
                    help="autoriza substituir a evidência de uma corrida com o mesmo n")
    args = ap.parse_args()

    lexico = load_lexicon()
    if len(lexico) < 10000:
        raise SystemExit(f"léxico suspeito ({len(lexico)} palavras) — cheque /usr/share/dict")
    if not CLI.exists():
        raise SystemExit(
            f"runtime Rust ausente ({CLI}). Removido deste repositório em 2026-07-30 "
            f"(commit 266253f) — não há crate para `cargo build`. Faça checkout do commit "
            f"anterior para reproduzir a medição."
        )

    tmp = REPO / "data" / "eval" / "_eval_wavs"
    tmp.mkdir(parents=True, exist_ok=True)
    composicao = transcrever(pq.ParquetFile(find_test_parquet()), lexico, args.n, tmp)

    cmd = f"python3 jvscribe/eval/analyze_error_composition.py --n {args.n}"
    texto = render(composicao, n_lexico=len(lexico), cmd=cmd)
    destino = args.out or caminho_da_corrida(args.n)
    print(texto)
    try:
        escrever_relatorio(destino, texto, force=args.force)
    except FileExistsError as e:
        print(f"\n⚠️  NÃO gravado: {e}")
        return 1
    print(f"\nevidência gravada em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
