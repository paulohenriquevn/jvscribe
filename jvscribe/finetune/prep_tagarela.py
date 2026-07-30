"""Prepara um subset do TAGARELA (freds0/TAGARELA, podcasts pt, pseudo-rotulado Whisper)
no formato do datamodule REAL do icefall, para o **mux** de M5 (D4 —
`knowledge-base/plans/m5-scale-model-wer-plan.md` Task 0.3).

TAGARELA agrega ~8.972h totais (1764 shards parquet, ~1,21TB) — muito além do necessário
(D4: mux pesa ~500h de TAGARELA contra ~273h de CORAA humano). Este script NÃO baixa o
corpus inteiro: consome um SUBSET de shards já baixados (`--parquet-dir`), amostrado de
forma estratificada por `download_tagarela_subset.py` (shards espaçados uniformemente ao
longo dos 1764 para reduzir viés de show/episódio — ver esse script para a amostragem
auditável).

Emite `tagarela_cuts_train.jsonl.gz` + fbank 80-dim, o mesmo contrato de
`prep_coraa.py`, então `zipformer/train.py --use-mux` combina os dois
manifests sem modificação.

Reuso (Regra 9 — sem duplicar):
  - `prep_icefall.normalize_ptbr` → mesma normalização de todo M4/M5 (audit D2).
  - `lhotse.Fbank(FbankConfig(num_mel_bins=80))` → mesmo extractor de `prep_coraa.py`.
  - decode→mono→wav→`Recording.from_file` → MESMO padrão de `prep_icefall.build`
    (bounda RAM: NÃO retém os bytes FLAC; garante MONO — F4/F5 da revisão de corpus).

Schema do parquet (freds0/TAGARELA, `[FONTE-REPO]` inspecionado via pyarrow em
2026-07-28): colunas `audio` (struct `{bytes: binary(flac), path: string}`), `path`
(string, redundante ao `audio.path`, codifica show/episódio — usado no relatório de
cobertura F7), `sentence` (string, transcrição pseudo-Whisper), `accent` (`"pt-br"` ou
`"pt-pt"`). SEM coluna de voto/confiança (não é CORAA — não há filtro análogo a
`--min-net-votes`). Como o pseudo-label do Whisper alucina (loop em silêncio/música/
vinheta de podcast), este script aplica um FILTRO DETERMINÍSTICO de alucinação
(`is_hallucinated_text` + bound de char/segundo) — NÃO precisa de votos humanos nem 2º
transcritor (F3 da revisão). Os defaults são conservadores (docstring das constantes).

INVARIANTE ESTRUTURAL (PRD §7.3 / falácia §3 #10): este script SÓ escreve o split
`train` — não existe flag `--split dev` ou `--split test`. TAGARELA é pseudo-label;
NUNCA pode entrar no anchor de eval. A ausência da opção É a garantia (não uma checagem
em runtime que pode ser burlada por flag).

VAZAMENTO CROSS-CORPUS (F2 da revisão): a garantia estrutural acima impede TAGARELA de
VIRAR manifesto de test; ela NÃO cobre overlap de locutor/conteúdo entre o TAGARELA-train
(podcasts) e o test CORAA humano (que inclui TEDx + figuras públicas). Rode
`scripts/tagarela_coraa_leak_check.py` na instância (onde os dois datasets coexistem)
para o cross-check demonstrável; qualquer interseção é BLOCKER. Sem interseção, declarar
o risco residual no deliverable de M5 (Regra 3).

WIRING DO MUX (F9 da revisão — ATENÇÃO no runbook da Fase 4): o manifesto emitido é
`tagarela_cuts_train.jsonl.gz` — prefixo `tagarela_cuts_`, que NÃO casa o glob default
`cv-pt_cuts_{split}` do datamodule. O `--use-mux` da Fase 4 DEVE apontar EXPLICITAMENTE
para este arquivo; caso contrário ele é silenciosamente ignorado e o "mux 1:1" degrada
para CORAA-only sem ninguém perceber (cf. lição B-1 do pipeline de corpus M3:
preparar um manifesto ≠ ele ser carregado).

Uso (na instância, após `download_tagarela_subset.py` ter baixado os shards):
  python3 prep_tagarela.py --out data/tagarela \
      --parquet-dir /workspace/tagarela_raw/data \
      --num-jobs 8
"""

from __future__ import annotations

import argparse
import io
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf
from lhotse import CutSet, Fbank, FbankConfig, Recording, SupervisionSegment, SupervisionSet
from lhotse.audio import RecordingSet
from lhotse.utils import fastcopy

import prep_icefall as PI  # reusa normalize_ptbr — sem duplicar (audit D2)

TARGET_SR = 16000  # mesma taxa do treino de M4/CORAA; fbank misturando SR é bug
ACCENT_KEEP = "pt-br"  # projeto é PT-BR; TAGARELA mistura ~9% pt-PT (doc do dataset)
CUT_ID_PREFIX = "tagarela_train"  # disjunto por construção dos prefixos "coraa_*"

# --- Filtro determinístico de alucinação de pseudo-label (F3 da revisão de corpus) ---
# Defaults CONSERVADORES: alvo é cortar a assinatura de loop do Whisper e razões
# char/segundo fisicamente implausíveis, SEM derrubar fala legítima. Não usa voto humano
# nem 2º transcritor — é o análogo pseudo-label do `--min-net-votes` do CORAA.
MIN_CPS = 0.5       # chars/s mínimo plausível (abaixo: áudio longo + texto ínfimo → miss)
MAX_CPS = 40.0      # chars/s máximo plausível (acima: alucinação/loop cospe texto demais)
REP_MAX_CONSEC = 4  # mesmo token repetido ≥N vezes SEGUIDAS ("obrigado obrigado…") → loop
REP_MIN_WORDS = 8   # só aplica a razão tipos/tokens a textos com ≥N palavras
REP_UNIQUE_MIN = 0.30  # unique/total < isto (com ≥REP_MIN_WORDS palavras) → loop repetitivo
CHAR_RUN_MAX = 6    # ≥N chars idênticos SEGUIDOS ("bêêêêêê") → alucinação char-level do Whisper.
#                     PT-BR não tem 3+ letras idênticas seguidas; 6 é folga p/ elongação enfática.
MAX_WORD_LEN = 30   # palavra única > N chars → alucinação (a maior palavra PT-BR tem ~29 chars).


def is_hallucinated_text(text: str) -> bool:
    """Heurística determinística de alucinação de pseudo-label do Whisper. Quatro sinais,
    todos text-only (baratos, aplicados ANTES de decodificar o áudio):
      (1) repetição consecutiva do mesmo TOKEN ≥ REP_MAX_CONSEC ("obrigado obrigado …");
      (2) razão tipos/tokens (unique/total) < REP_UNIQUE_MIN em texto com ≥ REP_MIN_WORDS
          palavras — pega loop de bigrama/frase ("a b a b a b a b");
      (3) run de CARACTERE idêntico ≥ CHAR_RUN_MAX ("mãe bêêêêêê…") — a assinatura de
          alucinação do Whisper sobre música/silêncio/vinheta, que (1)/(2) não pegam pois é
          uma única "palavra" com centenas de chars;
      (4) palavra única > MAX_WORD_LEN chars — idem, defesa em profundidade sobre (3).
    Fala legítima em pt-br raramente cai abaixo de ~0,5 de unicidade em 8+ palavras nem tem
    3+ letras idênticas seguidas, então os cortes são seguros. True se o texto parece alucinado."""
    words = text.split()
    if not words:
        return False
    # (3) run de caractere idêntico contíguo (reseta em mudança de char ou espaço)
    run = 1
    for prev, cur in zip(text, text[1:]):
        if cur == prev and not cur.isspace():
            run += 1
            if run >= CHAR_RUN_MAX:
                return True
        else:
            run = 1
    # (4) palavra única anormalmente longa
    if any(len(w) > MAX_WORD_LEN for w in words):
        return True
    # (1) repetição consecutiva de token
    run = 1
    for prev, cur in zip(words, words[1:]):
        run = run + 1 if cur == prev else 1
        if run >= REP_MAX_CONSEC:
            return True
    # (2) razão tipos/tokens
    if len(words) >= REP_MIN_WORDS and len(set(words)) / len(words) < REP_UNIQUE_MIN:
        return True
    return False


def show_key(path: str) -> str:
    """Chave de show do TAGARELA para o relatório de cobertura (F7) — NÃO afeta
    inclusão/exclusão. Estrutura real: `dataset/{d}/{L}/show_{ID}/{episode}...` — a
    chave é o componente `show_{ID}` (não o nome do dataset, que é constante). Fallback:
    primeiro segmento (cobre paths sem componente `show_`, ex. fixtures sintéticas)."""
    p = (path or "").strip().lstrip("/")
    if not p:
        return "<unknown>"
    for tok in p.split("/"):
        if tok.startswith("show_"):
            return tok
    return p.split("/", 1)[0]


def _clamp(c):
    """Supervisão não pode exceder a duração do cut (fbank arredonda num_frames p/
    baixo). Mesma correção de prep_coraa/prep_icefall — glue do lhotse."""
    return fastcopy(c, supervisions=[
        fastcopy(sp, duration=round(c.duration - sp.start, 4))
        if sp.start + sp.duration > c.duration else sp
        for sp in c.supervisions])


def iter_parquet_shards(parquet_dir: Path):
    shards = sorted(parquet_dir.glob("*.parquet"))
    if not shards:
        raise FileNotFoundError(
            f"[tagarela] nenhum .parquet encontrado sob {parquet_dir} — rodou "
            f"download_tagarela_subset.py?")
    return shards


def build_split(parquet_dir: Path, wav_dir: Path, limit: int | None):
    """Lê os shards parquet e constrói Recording+Supervision a partir dos bytes FLAC
    embutidos + coluna `sentence`. Espelha `prep_icefall.build` (Regra 9):

      decode(BytesIO(flac)) → downmix MONO (arr.mean(axis=1)) → sf.write(wav) →
      Recording.from_file(wav)

    Esse padrão (F4/F5 da revisão) garante MONO (o `from_bytes` original preservava o
    nº de canais do FLAC → treinava só o canal 0 de podcasts estéreo) e BOUNDA a RAM
    (o `recs` guarda referências de arquivo, não os bytes FLAC de todo o subset).

    Filtros de inclusão (escritos ANTES de rodar, PRD §7.3):
      - accent != pt-br            → fora do escopo PT-BR
      - texto vazio pós-normalize  → sem alvo
      - is_hallucinated_text(texto)→ loop de alucinação do Whisper (F3)
      - char/s ∉ [MIN_CPS,MAX_CPS] → razão texto×duração implausível (F3)

    Retorna (recs, sups, stats) — stats é um dict com contadores e a distribuição por
    show (relatório de cobertura F7)."""
    wav_dir.mkdir(parents=True, exist_ok=True)
    recs, sups = [], []
    stats = dict(total=0, kept=0, empty=0, wrong_accent=0, hallucination=0, bad_ratio=0,
                 decode_error=0)
    show_counts: dict[str, int] = defaultdict(int)
    for shard in iter_parquet_shards(parquet_dir):
        pf = pq.ParquetFile(shard)
        for batch in pf.iter_batches(columns=["audio", "sentence", "accent", "path"]):
            d = batch.to_pydict()
            for audio, sentence, accent, path in zip(
                    d["audio"], d["sentence"], d["accent"], d["path"]):
                stats["total"] += 1
                if limit is not None and stats["kept"] >= limit:
                    stats["show_counts"] = dict(show_counts)
                    return recs, sups, stats
                if accent != ACCENT_KEEP:
                    stats["wrong_accent"] += 1
                    continue
                text = PI.normalize_ptbr(sentence or "")
                if not text:
                    stats["empty"] += 1
                    continue
                if is_hallucinated_text(text):
                    stats["hallucination"] += 1
                    continue
                # decode → mono → wav → from_file (bounda RAM; garante mono)
                try:
                    arr, sr = sf.read(io.BytesIO(audio["bytes"]), dtype="float32")
                except Exception:  # FLAC corrompido no shard — conta e segue (fail-soft por item)
                    stats["decode_error"] += 1
                    continue
                if arr.ndim > 1:  # downmix estéreo→mono (mesma convenção de prep_icefall)
                    arr = arr.mean(axis=1)
                dur = len(arr) / sr if sr else 0.0
                cps = len(text) / dur if dur > 0 else 0.0
                if cps < MIN_CPS or cps > MAX_CPS:
                    stats["bad_ratio"] += 1
                    continue
                cid = f"{CUT_ID_PREFIX}_{stats['kept']:08d}"
                wav = wav_dir / f"{cid}.wav"
                sf.write(str(wav), arr, sr)
                rec = Recording.from_file(str(wav), recording_id=cid)
                recs.append(rec)
                sups.append(SupervisionSegment(
                    id=f"{cid}-0", recording_id=cid, start=0.0, duration=rec.duration,
                    channel=0, language="Portuguese", text=text))
                show_counts[show_key(path)] += 1
                stats["kept"] += 1
    stats["show_counts"] = dict(show_counts)
    return recs, sups, stats


def _write_coverage_report(out: Path, show_counts: dict[str, int], kept: int):
    """Relatório de cobertura por show/episódio (F7) + sinal de domínio. Escreve
    `show_distribution.txt` (auditável) e imprime o topo + o % do maior show."""
    ordered = sorted(show_counts.items(), key=lambda kv: kv[1], reverse=True)
    lines = [f"{n}\t{k}" for k, n in ordered]
    (out / "show_distribution.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    top = ordered[:15]
    print(f"[tagarela] cobertura: {len(show_counts)} shows/episódios distintos em "
          f"{kept} utts mantidas", flush=True)
    for k, n in top:
        print(f"[tagarela]   {n:7d}  {k}", flush=True)
    if ordered and kept:
        dom_share = 100.0 * ordered[0][1] / kept
        flag = "  ← DOMÍNIO (>30% num só show)" if dom_share > 30.0 else ""
        print(f"[tagarela] maior show = {dom_share:.1f}% das utts{flag}", flush=True)


def prepare(parquet_dir: Path, out: Path, extractor, num_jobs: int, limit: int | None):
    wav_dir = out / "wav_train"
    recs, sups, stats = build_split(parquet_dir, wav_dir, limit)
    print(f"[tagarela] total={stats['total']} kept={stats['kept']} "
          f"empty_text={stats['empty']} wrong_accent={stats['wrong_accent']} "
          f"hallucination={stats['hallucination']} bad_ratio={stats['bad_ratio']} "
          f"decode_error={stats['decode_error']}", flush=True)
    if stats["kept"] == 0:
        raise RuntimeError(
            f"[tagarela] 0 utterances mantidas sob {parquet_dir} — shards vazios ou "
            f"todos filtrados (accent/texto/alucinação/ratio)?")
    _write_coverage_report(out, stats["show_counts"], stats["kept"])
    cuts = CutSet.from_manifests(
        recordings=RecordingSet.from_recordings(recs),
        supervisions=SupervisionSet.from_segments(sups))
    cuts = cuts.resample(TARGET_SR)  # podcasts costumam ser 44,1/48k → 16k = CORAA/MLS
    cuts = cuts.compute_and_store_features(
        extractor=extractor, storage_path=str(out / "feats_train"), num_jobs=num_jobs)
    cuts = CutSet.from_cuts(_clamp(c) for c in cuts)
    cuts.to_file(str(out / "tagarela_cuts_train.jsonl.gz"))
    hours = sum(c.duration for c in cuts) / 3600.0
    print(f"[tagarela] {len(cuts)} cuts, {hours:.2f}h [MEDIDO] "
          f"→ tagarela_cuts_train.jsonl.gz", flush=True)
    return [sp.text for sp in sups], hours


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/tagarela")
    ap.add_argument("--parquet-dir", required=True,
                    help="dir com os shards *.parquet baixados (subset estratificado)")
    ap.add_argument("--num-jobs", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="máx utts (smoke)")
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    parquet_dir = Path(args.parquet_dir)
    extractor = Fbank(FbankConfig(num_mel_bins=80))

    texts, _ = prepare(parquet_dir, out, extractor, args.num_jobs, args.limit)
    (out / "transcript_words.txt").write_text("\n".join(texts) + "\n", encoding="utf-8")
    print(f"[tagarela] pronto em {out} (formato datamodule commonvoice, split=train "
          f"ÚNICO — invariante estrutural §7.3)", flush=True)


if __name__ == "__main__":
    main()
