# =====================================================================================
# CORPUS DO BAKE-OFF — ~1.500 h do TAGARELA, preparado em lotes
#
# Cole em UMA célula do Colab e execute. Não depende de nenhuma variável do notebook.
# Pré-requisitos: as células 1-4 do m10-prototipo-colab.ipynb (ambiente + dependências
# + clone do repo em /content/icefall e /content/jvscribe).
#
# O que faz, nesta ordem:
#   1. projeta o pico de disco e RECUSA começar se não couber;
#   2. baixa N shards estratificados do TAGARELA;
#   3. prepara em lotes: decode → wav → fbank → apaga o wav do lote;
#   4. relata horas mantidas, horas perdidas por filtro, e o custo em disco.
#
# O TETO do Colab é ~1.700 h: por hora preparada o disco paga 73 MB de parquet + 31 MB
# de feature = 104 MB, contra ~206 GB livres menos o wav do lote. A Fase 3 quer 5.000 h,
# e é por isso — não por compute — que ela precisa do volume da vast.ai.
#
# ⚠️ Apagar o áudio FECHA a augmentação telefônica on-the-fly, que relê o wav a cada
#    época. É a troca que torna 1.500 h viáveis num disco de sessão. Quem quiser a
#    augmentação precisa do volume persistente da vast.ai, não do Colab.
# =====================================================================================
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── o que você escolhe ───────────────────────────────────────────────────────────────
HORAS_ALVO   = 1500      # meta do bake-off (plano M10, T4)
SHARDS_LOTE  = 12        # shards por lote de preparação — controla o pico de wav
NUM_JOBS     = 8         # paralelismo do fbank
RAIZ         = Path('/content/data/tagarela_1500h')
REPO         = Path('/content/jvscribe')

# ── constantes MEDIDAS neste projeto (não estimadas) ─────────────────────────────────
H_POR_SHARD  = 296.8 / 31   # [MEDIDO] 31 shards → 296,8 h mantidas após os filtros
GB_POR_SHARD = 1210 / 1764  # [FONTE-REPO] card do TAGARELA: ~1,21 TB em 1.764 shards
MB_WAV_H     = 115          # [MEDIDO] wav 16 kHz mono
MB_FEAT_H    = 31           # [MEDIDO] lilcom_chunky (numpy seria 115)

N_SHARDS = max(1, round(HORAS_ALVO / H_POR_SHARD))
h_lote   = SHARDS_LOTE * H_POR_SHARD

gb_parquet = N_SHARDS * GB_POR_SHARD
gb_wav     = h_lote * MB_WAV_H / 1024          # só UM lote por vez
gb_feats   = HORAS_ALVO * MB_FEAT_H / 1024
gb_pico    = gb_parquet + gb_wav + gb_feats

livre_gb = shutil.disk_usage('/content').free / 1024**3
print(f'alvo          {HORAS_ALVO:>7.0f} h  →  {N_SHARDS} shards '
      f'({H_POR_SHARD:.2f} h/shard [MEDIDO])')
print(f'parquet       {gb_parquet:>7.1f} GB   (baixados de uma vez)')
print(f'wav do lote   {gb_wav:>7.1f} GB   ({SHARDS_LOTE} shards = {h_lote:.0f} h por lote)')
print(f'features      {gb_feats:>7.1f} GB   (lilcom; em numpy seriam '
      f'{HORAS_ALVO * 115 / 1024:.0f} GB)')
print(f'PICO          {gb_pico:>7.1f} GB   contra {livre_gb:.1f} GB livres')

MARGEM = 20  # GB de folga para o checkpoint, o log e o que o Colab usa por conta própria
if gb_pico + MARGEM > livre_gb:
    gb_por_hora = GB_POR_SHARD / H_POR_SHARD + MB_FEAT_H / 1024
    sugerido = max(0, int((livre_gb - MARGEM - gb_wav) / gb_por_hora))
    raise SystemExit(
        f'\nNÃO CABE: pico projetado {gb_pico:.0f} GB + {MARGEM} GB de margem > '
        f'{livre_gb:.0f} GB livres.\n'
        f'Baixe menos: HORAS_ALVO = {max(100, sugerido // 100 * 100)} cabe neste disco.\n'
        f'Encher o disco no meio do fbank perde o lote em curso E o download inteiro.')

# ── 1. download ──────────────────────────────────────────────────────────────────────
raw = RAIZ / 'raw'
raw.mkdir(parents=True, exist_ok=True)
ja = len(list(raw.glob('*.parquet')))
print(f'\n[1/2] baixando {N_SHARDS} shards ({ja} já em disco — o downloader retoma)…')
t0 = time.time()
subprocess.run([sys.executable, str(REPO / 'jvscribe/finetune/download_tagarela_subset.py'),
                '--out', str(raw), '--num-shards', str(N_SHARDS)], check=True)
print(f'[1/2] download em {(time.time() - t0) / 60:.1f} min')

# ── 2. preparação em lotes ───────────────────────────────────────────────────────────
print(f'\n[2/2] preparando em lotes de {SHARDS_LOTE} shards…')
t0 = time.time()
env = dict(os.environ, OMP_NUM_THREADS='1')  # o fbank já paraleliza por job; OMP aninhado
                                             # derruba a taxa (lição do M4)
subprocess.run([sys.executable, str(REPO / 'jvscribe/finetune/prep_tagarela.py'),
                '--parquet-dir', str(raw), '--out', str(RAIZ),
                '--num-jobs', str(NUM_JOBS),
                '--shards-per-batch', str(SHARDS_LOTE),
                '--drop-audio-after-features'],
               check=True, cwd=str(REPO / 'jvscribe/finetune'), env=env)
prep_min = (time.time() - t0) / 60

# ── relatório ────────────────────────────────────────────────────────────────────────
from lhotse import CutSet  # noqa: E402

cuts  = CutSet.from_file(str(RAIZ / 'tagarela_cuts_train.jsonl.gz'))
horas = sum(c.duration for c in cuts) / 3600
feats_gb = sum(f.stat().st_size for f in (RAIZ / 'feats_train').rglob('*')
               if f.is_file()) / 1024**3
print(f'\n{"=" * 70}\n'
      f'{len(cuts)} cuts · {horas:.1f} h mantidas ({horas / HORAS_ALVO * 100:.0f}% do alvo)\n'
      f'features {feats_gb:.1f} GB = {feats_gb * 1024 / horas:.0f} MB/h [MEDIDO]\n'
      f'preparação em {prep_min:.0f} min = {horas / (prep_min / 60):.0f}× tempo real\n'
      f'{"=" * 70}')
print(f'\nApague os parquets para liberar {gb_parquet:.0f} GB quando conferir o manifesto:'
      f'\n  !rm -rf {raw}')
print('\nO manifesto traz o pseudo-rótulo ORIGINAL do TAGARELA (Whisper genérico), que a\n'
      'T3 mediu com 22,7% de discordância contra o Nemotron. Serve para medir custo e\n'
      'mecânica. NÃO serve para o bake-off: o ADR-003 exige re-rotular com professor\n'
      'adaptado antes de treinar.')
