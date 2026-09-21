# =====================================================================================
# CORPUS DO BAKE-OFF — ~1.500 h do TAGARELA, baixado e preparado em CICLOS
#
# Cole em UMA célula do Colab e execute. Não depende de nenhuma variável do notebook.
# Pré-requisitos: as células 1-4 do m10-prototipo-colab.ipynb (ambiente + dependências
# + clone do repo em /content/jvscribe).
#
# Por que em ciclos: baixar os 157 shards de uma vez deixa 107,7 GB de parquet parados
# em disco até o fim da extração, e o parquet vira o item dominante do pico. Ciclando
# download → preparação → remoção, o parquet vivo é o de UM grupo:
#
#     | modo                         | pico em 1.500 h | teto do disco* |
#     |------------------------------|-----------------|----------------|
#     | baixar tudo, depois preparar |      166,0 GB   |        800 h   |
#     | em ciclos (este script)      |       66,5 GB   |      2.523 h   |
#     *contra os 117,5 GB livres medidos numa sessão do Colab Pro
#
# A Fase 3 quer 5.000 h = 151 GB só de feature. Nem em ciclos isso cabe numa sessão —
# e é por disco, não por compute, que ela precisa do volume da vast.ai.
#
# ⚠️ As features são extraídas e o áudio do lote é apagado. Isso FECHA a augmentação
#    telefônica on-the-fly, que relê o wav a cada época. É a troca que torna 1.500 h
#    viáveis num disco de sessão.
#
# Retomada: se a sessão morrer, rode de novo. Ciclo com manifesto pronto é pulado.
# =====================================================================================
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

# ── o que você escolhe ───────────────────────────────────────────────────────────────
HORAS_ALVO       = 1500   # meta do bake-off (plano M10, T4)
SHARDS_POR_CICLO = 12     # parquet vivo = este número de shards
SHARDS_POR_LOTE  = 4      # wav vivo = este número, dentro do ciclo
NUM_JOBS         = 8      # paralelismo do fbank
RAIZ             = Path('/content/data/tagarela_1500h')
REPO             = Path('/content/jvscribe')

# ── constantes MEDIDAS neste projeto (não estimadas) ─────────────────────────────────
H_POR_SHARD  = 296.8 / 31   # [MEDIDO] 31 shards → 296,8 h mantidas após os filtros
GB_POR_SHARD = 1210 / 1764  # [FONTE-REPO] card do TAGARELA: ~1,21 TB em 1.764 shards
MB_WAV_H     = 115          # [MEDIDO] wav 16 kHz mono
MB_FEAT_H    = 31           # [MEDIDO] lilcom_chunky (numpy seria 115)

N_SHARDS  = max(1, round(HORAS_ALVO / H_POR_SHARD))
gb_parq   = SHARDS_POR_CICLO * GB_POR_SHARD
gb_wav    = SHARDS_POR_LOTE * H_POR_SHARD * MB_WAV_H / 1024
gb_feats  = HORAS_ALVO * MB_FEAT_H / 1024
gb_pico   = gb_parq + gb_wav + gb_feats

livre_gb = shutil.disk_usage('/content').free / 1024**3
MARGEM   = 15  # GB de folga para log, manifesto e o que o Colab usa por conta própria

print(f'alvo            {HORAS_ALVO:>7.0f} h  →  {N_SHARDS} shards '
      f'({H_POR_SHARD:.2f} h/shard [MEDIDO])')
print(f'parquet vivo    {gb_parq:>7.1f} GB   ({SHARDS_POR_CICLO} shards por ciclo)')
print(f'wav vivo        {gb_wav:>7.1f} GB   ({SHARDS_POR_LOTE} shards por lote)')
print(f'features        {gb_feats:>7.1f} GB   (acumula até o fim; em numpy seriam '
      f'{HORAS_ALVO * MB_WAV_H / 1024:.0f} GB)')
print(f'PICO            {gb_pico:>7.1f} GB   contra {livre_gb:.1f} GB livres')

if gb_pico + MARGEM > livre_gb:
    cabe = int((livre_gb - MARGEM - gb_parq - gb_wav) / (MB_FEAT_H / 1024))
    raise SystemExit(
        f'\nNÃO CABE: pico {gb_pico:.0f} GB + {MARGEM} GB de margem > {livre_gb:.0f} GB '
        f'livres.\nHORAS_ALVO = {max(100, cabe // 100 * 100)} cabe neste disco.\n'
        f'Encher o disco no meio do fbank perde o ciclo em curso.')

# ── sincroniza o clone ───────────────────────────────────────────────────────────────
# Sem isto, um clone feito antes do commit falha com `exit status 2` — que é o
# "can't open file" do Python, e não diz nada sobre estar desatualizado.
FINETUNE = REPO / 'jvscribe/finetune'
SCRIPT   = FINETUNE / 'prepare_corpus_streaming.py'

if not (REPO / '.git').is_dir():
    raise SystemExit(f'{REPO} não é um clone git — rode a célula 3 do notebook antes.')
subprocess.run(['git', '-C', str(REPO), 'pull', '--ff-only', 'origin', 'workspace'],
               check=True)
if not SCRIPT.exists():
    raise SystemExit(
        f'{SCRIPT} não existe mesmo depois do pull.\n'
        f'O clone aponta para outro remoto ou outra branch. Confira:\n'
        f'  !git -C {REPO} remote -v && git -C {REPO} branch --show-current')
_head = subprocess.run(['git', '-C', str(REPO), 'rev-parse', '--short', 'HEAD'],
                       capture_output=True, text=True).stdout.strip()
print(f'repo em {_head}')

# ── baixa e prepara ──────────────────────────────────────────────────────────────────
print(f'\nbaixando e preparando em {-(-N_SHARDS // SHARDS_POR_CICLO)} ciclos…')
t0 = time.time()
# Ecoa ao vivo E grava: são ~5 h de execução, e sem eco você fica no escuro; sem log,
# a causa de uma falha no ciclo 9 já saiu do scrollback do Colab quando ela aparece.
LOG = Path('/content/corpus.log')
proc = subprocess.Popen(
    [sys.executable, 'prepare_corpus_streaming.py',
     '--out', str(RAIZ), '--horas-alvo', str(HORAS_ALVO),
     '--shards-por-ciclo', str(SHARDS_POR_CICLO),
     '--shards-por-lote', str(SHARDS_POR_LOTE),
     '--num-jobs', str(NUM_JOBS)],
    cwd=str(FINETUNE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True, bufsize=1)
ultimas = deque(maxlen=40)
with LOG.open('w') as fh:
    for linha in proc.stdout:
        fh.write(linha)
        ultimas.append(linha)
        if linha.startswith('[stream]') or 'Error' in linha or 'error' in linha:
            print(linha, end='', flush=True)
if proc.wait() != 0:
    print('\n--- últimas 40 linhas ---')
    print(''.join(ultimas))
    raise SystemExit(f'preparação FALHOU (exit {proc.returncode}) — log completo em {LOG}')
minutos = (time.time() - t0) / 60

# ── relatório ────────────────────────────────────────────────────────────────────────
from lhotse import CutSet  # noqa: E402

cuts     = CutSet.from_file(str(RAIZ / 'tagarela_cuts_train.jsonl.gz'))
horas    = sum(c.duration for c in cuts) / 3600
feats_gb = sum(f.stat().st_size for f in RAIZ.rglob('feats_train*/**/*')
               if f.is_file()) / 1024**3
print(f'\n{"=" * 70}\n'
      f'{len(cuts)} cuts · {horas:.1f} h mantidas ({horas / HORAS_ALVO * 100:.0f}% do alvo)\n'
      f'features {feats_gb:.1f} GB = {feats_gb * 1024 / horas:.0f} MB/h [MEDIDO]\n'
      f'{minutos:.0f} min = {horas / (minutos / 60):.0f}× tempo real\n'
      f'disco livre agora: {shutil.disk_usage("/content").free / 1024**3:.1f} GB\n'
      f'{"=" * 70}')
print('\nO manifesto traz o pseudo-rótulo ORIGINAL do TAGARELA (Whisper genérico), que a\n'
      'T3 mediu com 22,7% de discordância contra o Nemotron. Serve para medir custo e\n'
      'mecânica. NÃO serve para o bake-off: o ADR-003 exige re-rotular com professor\n'
      'adaptado antes de treinar.')
