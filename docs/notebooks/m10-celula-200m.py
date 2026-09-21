# ============================================================================
# M10 -- UMA EPOCA A ~200M: a escala por parametros.  Cole e execute.
# Autossuficiente: nao depende de variavel deixada por outra celula.
# Pre-requisito: corpus, fbank e bpe.model ja no disco desta sessao.
# ============================================================================
import os, sys, re, time, signal, subprocess

CV, LANGID = '/content/data/tagarela', 'pt'
LANG       = '/content/data/lang_bpe_500'
EXP        = '/content/drive/MyDrive/jvscribe/m10_proto/exp-200m'
ALVO_M, EPOCAS = 200, 1

# --- o que precisa existir. Falhar aqui custa segundos; falhar depois do
#     treino custa a epoca inteira.
for f in (f'{CV}/cv-{LANGID}_cuts_train.jsonl.gz',
          f'{CV}/cv-{LANGID}_cuts_dev.jsonl.gz',
          f'{LANG}/bpe.model',
          '/content/icefall/egs/commonvoice/ASR/zipformer/train.py'):
    if not os.path.exists(f):
        raise FileNotFoundError(f'{f} nao existe -- a sessao reiniciou? '
                                'Rode as secoes 1 a 6 do notebook antes desta celula.')
os.makedirs(EXP, exist_ok=True)

from lhotse import CutSet
HORAS_TREINO = sum(c.duration for c in
                   CutSet.from_file(f'{CV}/cv-{LANGID}_cuts_train.jsonl.gz')) / 3600

UNIDADES_POR_HORA = {'L4': 4.8, 'A100': 13.0, 'T4': 2.0}   # [ESTIMATIVA] nao medido
GPU  = subprocess.run(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],
                      capture_output=True, text=True).stdout.strip()
un_h = next((v for k, v in UNIDADES_POR_HORA.items() if k in GPU), None)
print(f'GPU: {GPU} | unidades/h: {un_h} | corpus: {HORAS_TREINO:.1f} h\n')

# --- escolher as dimensoes MEDINDO, nao adivinhando -------------------------
# get_parser() ja chama add_model_arguments(); o datamodule so entra no main(),
# entao parse_args() aceita apenas flags de modelo. blank_id/vocab_size sao
# preenchidos no main a partir do bpe.model -- por isso entram a mao aqui.
sys.path.insert(0, '/content/icefall/egs/commonvoice/ASR/zipformer')
import train as T

CANDIDATOS = {
 'medium (o run de 66M)': dict(
    layers='2,2,3,4,3,2', ffw='512,768,1024,1536,1024,768',
    dim='192,256,384,512,384,256', unmask='192,192,256,256,256,192'),
 'large (icefall)': dict(
    layers='2,2,4,5,4,2', ffw='512,768,1536,2048,1536,768',
    dim='192,256,512,768,512,256', unmask='192,192,256,320,256,192'),
 'large + camadas': dict(
    layers='2,3,4,6,4,3', ffw='512,768,1536,2048,1536,768',
    dim='192,256,512,768,512,256', unmask='192,192,256,320,256,192'),
 'large + largura': dict(
    layers='2,2,4,5,4,2', ffw='768,1024,1536,2560,1536,1024',
    dim='256,384,512,896,512,384', unmask='192,192,256,384,256,192'),
 'xlarge': dict(
    layers='2,3,4,6,4,3', ffw='768,1024,2048,2560,2048,1024',
    dim='256,384,640,896,640,384', unmask='192,192,320,384,320,192'),
}
def _flags(c):
    return ['--num-encoder-layers', c['layers'], '--feedforward-dim', c['ffw'],
            '--encoder-dim', c['dim'], '--encoder-unmasked-dim', c['unmask'],
            '--causal', '1', '--use-transducer', '1', '--use-ctc', '1']
def _conta(c):
    p = T.get_params(); p.update(vars(T.get_parser().parse_args(_flags(c))))
    p.blank_id, p.vocab_size = 0, 500
    return sum(x.numel() for x in T.get_model(p).parameters()) / 1e6

medidos = {}
for nome, c in CANDIDATOS.items():
    medidos[nome] = _conta(c)
    print(f'  {medidos[nome]:7.1f}M  {nome}')
nome  = min(medidos, key=lambda k: abs(medidos[k] - ALVO_M))
CFG, P_M = CANDIDATOS[nome], medidos[nome]
print(f'\nescolhido: {nome} -- {P_M:.1f}M (alvo {ALVO_M}M)')

# --- memoria e LR saem do TAMANHO, nunca escolhidos soltos ------------------
# UM ponto medido: 9.090 MB com 66,4M a max-duration 300.
#   fixo       = P x 4 bytes x 4 (peso, grad, 2 estados do ScaledAdam)
#   ativacoes ~ largura x T, e largura ~ sqrt(P)
# [ESTIMATIVA] de um ponto so. Se der OOM: corte MAX_DUR pela metade e rode de
# novo -- BASE_LR desce junto, porque o que importa e a RAZAO. Foi o desacople
# dos dois que mandou a primeira tentativa para NaN.
_fixo    = lambda p: p * 1e6 * 16 / 1e6
ATIV_300 = 9090 - _fixo(66.4)
ORCAMENTO_MB = 20000                      # 23.034 na L4, ~3 GB de folga
MAX_DUR = int(300 * (ORCAMENTO_MB - _fixo(P_M)) / ATIV_300 / (P_M/66.4)**0.5 / 10) * 10
RAZAO   = 2.1e-5                          # a razao lr/batch do RESULTS.md do recipe
BASE_LR = round(RAZAO * MAX_DUR, 5)
print(f'fixo ~{_fixo(P_M)/1000:.1f} GB | MAX_DUR {MAX_DUR} s [ESTIMATIVA] | BASE_LR {BASE_LR}')

cmd = (
    'cd /content/icefall/egs/commonvoice/ASR && python3 zipformer/train.py'
    f' --world-size 1 --num-epochs {EPOCAS} --start-epoch 1'
    f' --exp-dir {EXP} --bpe-model {LANG}/bpe.model'
    f' --cv-manifest-dir {CV} --language {LANGID} --enable-musan 0'
    f' --max-duration {MAX_DUR} --use-fp16 0 --num-workers 2'
    f" --num-encoder-layers {CFG['layers']} --feedforward-dim {CFG['ffw']}"
    f" --encoder-dim {CFG['dim']} --encoder-unmasked-dim {CFG['unmask']}"
    f' --causal 1 --use-transducer 1 --use-ctc 1 --base-lr {BASE_LR}')
print('\n' + cmd + '\n')

# --- rodar, vigiar, medir ---------------------------------------------------
# O exit code manda: um custo impresso sobre um run que morreu nao mede nada.
# O vigia existe porque a primeira tentativa subiu a loss por 3.300 batches
# antes de virar NaN -- 75 min gastos depois que o problema ja estava no log.
LOG = '/content/train-200m.log'
print(f'log -> {LOG}\n')
RE_TOT = re.compile(r'tot_loss\[loss=([\d.]+)')
melhor, ruins, MAX_RUINS, FATOR = float('inf'), 0, 4, 1.25
divergiu = False

t0 = time.time()
with open(LOG, 'w') as fh:
    proc = subprocess.Popen(['bash','-lc',cmd], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            start_new_session=True)
    for linha in proc.stdout:
        fh.write(linha); fh.flush()
        if any(k in linha for k in ('Epoch','Error','error','Traceback','CUDA',
                                    'Saving','validation','Maximum memory',
                                    'model parameters')):
            print(linha, end='')
        m = RE_TOT.search(linha)
        if m:
            v = float(m.group(1))
            if v != v or v > melhor * FATOR:
                ruins += 1
                if ruins >= MAX_RUINS:
                    divergiu = True
                    print(f'\n!! DIVERGIU: tot_loss {v:.3f} contra minimo {melhor:.3f}. Matando.')
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM); break
            else:
                ruins = 0; melhor = min(melhor, v)
    proc.wait()
el = time.time() - t0

# Custo por epoca mede THROUGHPUT, nao convergencia: forward e backward custam o
# mesmo numa epoca que aprende e numa que nao. O numero vale se UMA epoca fechou.
ckpts = sorted(f for f in os.listdir(EXP) if f.startswith('epoch-') and f.endswith('.pt'))
for f in ckpts:
    print(f'  {f}  {os.path.getsize(os.path.join(EXP,f))/1e6:.0f} MB')
if not ckpts:
    print('\n'.join(open(LOG).read().splitlines()[-40:]))
    raise RuntimeError(f'nenhuma epoca fechou em {el/60:.1f} min -- sem custo a medir.')

h_ep = el/3600/len(ckpts)
print(f'\n=== CUSTO MEDIDO A {P_M:.0f}M ===   ({HORAS_TREINO:.0f} h de corpus)')
print(f'{h_ep:.2f} h por epoca   (66,4M mediu 0,85 h -> escala {h_ep/0.85:.2f}x '
      f'para {P_M/66.4:.2f}x de parametros)')
if un_h:
    print(f'{h_ep*un_h:.1f} unidades = ${h_ep*un_h/10:.2f} por epoca')
    for c in (1500, 5000):
        for ne in (20, 40):
            h = h_ep*c/HORAS_TREINO*ne
            print(f'  {c} h x {ne} ep: {h:5.0f} h GPU | Colab ${h*un_h/10:4.0f} '
                  f'| A100 vast.ai ${h/2.5*0.80:4.0f} | {h/24:.0f} dias')
if divergiu or proc.returncode != 0:
    print(f'\nO CUSTO ACIMA VALE. O MODELO NAO: exit {proc.returncode}, divergiu={divergiu}.')
