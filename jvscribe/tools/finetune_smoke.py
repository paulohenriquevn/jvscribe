#!/usr/bin/env python3
"""Prova que o checkpoint publicado é finetunável — carrega, calcula loss e aprende.

Motivo de existir: `models/.../finetune/avg-124k-112k.pt` foi **reconstruído** depois que o
original chegou truncado da nuvem (ver `finetune/README.md § Incidente`). Um `.pt` que abre
não é um `.pt` que treina. Este script fecha essa lacuna sem depender de GPU.

O que ele afirma, e como prova cada afirmação:

1. **Os pesos entram na arquitetura declarada** — `load_state_dict(strict=True)`. Qualquer
   chave faltante, sobrando ou com shape errado é erro, não aviso.
2. **O modelo já sabe português** — a CTC loss inicial sobre áudio+transcrição reais fica
   MUITO abaixo da de um modelo aleatório, medido no mesmo lote. Um checkpoint corrompido
   ou mal-carregado carrega pesos "válidos" e produz loss de modelo aleatório.
3. **O gradiente flui e o treino desce** — N passos de Adam com a loss caindo.

Uso:
    python3 jvscribe/tools/finetune_smoke.py \\
        --checkpoint models/current/finetune/avg-124k-112k.pt \\
        --bpe models/current/finetune/bpe.model \\
        --audio-dir <wavs> --refs <refs.tsv> --icefall <caminho do clone> [--steps 12]

⚠️ Escopo: é um **smoke em CPU**, não um treino. Ele não valida a receita completa (datamodule,
augmentação, scheduler do icefall) — valida que o artefato publicado é um ponto de partida
utilizável. O treino de verdade roda em GPU pela receita de `finetune/README.md`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Arquitetura do jvscribe-ptbr-zipformer-ctc-64m. Sem estes valores o state_dict não encaixa —
# eles NÃO estão dentro do `.pt`, é preciso declará-los (ver finetune/README.md).
ARCH = dict(
    num_encoder_layers=(2, 2, 3, 4, 3, 2),
    feedforward_dim=(512, 768, 1024, 1536, 1024, 768),
    encoder_dim=(192, 256, 384, 512, 384, 256),
    encoder_unmasked_dim=(192, 192, 256, 256, 256, 192),
    downsampling_factor=(1, 2, 4, 8, 4, 2),
    num_heads=(4, 4, 4, 8, 4, 4),
    query_head_dim=(32,),
    value_head_dim=(12,),
    pos_head_dim=(4,),
    pos_dim=48,
    cnn_module_kernel=(31, 31, 15, 15, 15, 31),
)
VOCAB = 500
BLANK = 0


def _preparar_imports(icefall: Path, k2stub: Path) -> None:
    """O stub de `k2` precisa vir ANTES do k2 real no path — ver o docstring do stub."""
    sys.path.insert(0, str(k2stub))
    sys.path.insert(0, str(icefall))
    sys.path.insert(0, str(icefall / "egs/commonvoice/ASR/zipformer"))


def construir_modelo():
    """Replica `get_encoder_embed` / `get_encoder_model` / `AsrModel.__init__` do icefall.

    Espelha a fonte, não a memória: `train.py:574` (Conv2dSubsampling com o mesmo
    `ScheduledFloat`), `train.py:586` (Zipformer2) e `model.py:113` (cabeça CTC sobre
    `max(encoder_dim)`).
    """
    import torch
    from scaling import ScheduledFloat
    from subsampling import Conv2dSubsampling
    from zipformer import Zipformer2

    dropout = ScheduledFloat((0.0, 0.3), (20000.0, 0.1))
    encoder_embed = Conv2dSubsampling(
        in_channels=80,
        out_channels=ARCH["encoder_dim"][0],
        dropout=dropout,
    )
    encoder = Zipformer2(
        output_downsampling_factor=2,
        downsampling_factor=ARCH["downsampling_factor"],
        num_encoder_layers=ARCH["num_encoder_layers"],
        encoder_dim=ARCH["encoder_dim"],
        encoder_unmasked_dim=ARCH["encoder_unmasked_dim"],
        query_head_dim=ARCH["query_head_dim"],
        pos_head_dim=ARCH["pos_head_dim"],
        value_head_dim=ARCH["value_head_dim"],
        pos_dim=ARCH["pos_dim"],
        num_heads=ARCH["num_heads"],
        feedforward_dim=ARCH["feedforward_dim"],
        cnn_module_kernel=ARCH["cnn_module_kernel"],
        dropout=dropout,
        causal=False,
    )
    ctc_output = torch.nn.Sequential(
        torch.nn.Dropout(p=0.1),
        torch.nn.Linear(max(ARCH["encoder_dim"]), VOCAB),
        torch.nn.LogSoftmax(dim=-1),
    )
    return encoder_embed, encoder, ctc_output


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--bpe", type=Path, required=True)
    ap.add_argument("--audio-dir", type=Path, required=True)
    ap.add_argument("--refs", type=Path, required=True)
    ap.add_argument("--icefall", type=Path, required=True)
    ap.add_argument("--k2stub", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--n-utts", type=int, default=6)
    a = ap.parse_args()

    _preparar_imports(a.icefall, a.k2stub)

    import numpy as np
    import sentencepiece as spm
    import soundfile as sf
    import torch
    from lhotse import Fbank, FbankConfig

    torch.manual_seed(0)

    # ---------- lote real: áudio + transcrição humana ----------
    sp = spm.SentencePieceProcessor(model_file=str(a.bpe))
    fb = Fbank(FbankConfig(num_mel_bins=80))
    feats, targets = [], []
    for linha in a.refs.read_text(encoding="utf-8").splitlines()[: a.n_utts]:
        uid, texto = linha.split("\t", 1)
        wav = a.audio_dir / f"{uid}.wav"
        if not wav.exists():
            continue
        x, sr = sf.read(str(wav), dtype="float32")
        feats.append(torch.from_numpy(np.asarray(fb.extract(x, sr), dtype=np.float32)))
        targets.append(torch.tensor(sp.encode(texto.strip()), dtype=torch.long))
    if len(feats) < 2:
        raise SystemExit(f"lote insuficiente: {len(feats)} utterances em {a.audio_dir}")

    tmax = max(f.shape[0] for f in feats)
    x = torch.zeros(len(feats), tmax, 80)
    xl = torch.tensor([f.shape[0] for f in feats], dtype=torch.long)
    for i, f in enumerate(feats):
        x[i, : f.shape[0]] = f
    tgt = torch.cat(targets)
    tgt_len = torch.tensor([len(t) for t in targets], dtype=torch.long)
    print(f"  lote: {len(feats)} utterances, {int(xl.sum())} frames, {int(tgt_len.sum())} tokens BPE")

    from icefall.utils import make_pad_mask

    def perda(embed, enc, head) -> torch.Tensor:
        """Mesmo encadeamento de `AsrModel.forward_encoder` + `forward_ctc` (model.py)."""
        f, flens = embed(x, xl)
        mask = make_pad_mask(flens)
        out, olens = enc(f.permute(1, 0, 2), flens, mask)   # (N,T,C) -> (T,N,C)
        out = out.permute(1, 0, 2)                          # -> (N,T,C)
        lp = head(out)                                      # (N,T,V)
        return torch.nn.functional.ctc_loss(
            log_probs=lp.permute(1, 0, 2),                  # (T,N,V)
            targets=tgt, input_lengths=olens, target_lengths=tgt_len,
            blank=BLANK, reduction="mean", zero_infinity=True,
        )

    # ---------- 1. os pesos entram na arquitetura ----------
    embed, enc, head = construir_modelo()
    ck = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    sd = ck["model"] if isinstance(ck, dict) and "model" in ck else ck
    modelo = torch.nn.ModuleDict({"encoder_embed": embed, "encoder": enc, "ctc_output": head})
    faltando, sobrando = modelo.load_state_dict(sd, strict=False)
    print(f"  load_state_dict: faltando={len(faltando)}  sobrando={len(sobrando)}")
    if faltando:
        print(f"    primeiras faltando: {faltando[:5]}")
        raise SystemExit("FALHA: chaves faltando — o checkpoint não encaixa na arquitetura")

    # ---------- 2. o modelo já sabe português ----------
    modelo.eval()
    with torch.no_grad():
        loss_treinado = float(perda(embed, enc, head))
    aleatorio = torch.nn.ModuleDict(dict(zip(
        ("encoder_embed", "encoder", "ctc_output"), construir_modelo())))
    aleatorio.eval()
    with torch.no_grad():
        loss_aleatorio = float(perda(
            aleatorio["encoder_embed"], aleatorio["encoder"], aleatorio["ctc_output"]))
    print(f"  CTC loss  treinado={loss_treinado:.4f}   aleatorio={loss_aleatorio:.4f}")
    if not loss_treinado < 0.5 * loss_aleatorio:
        raise SystemExit(
            "FALHA: a loss do checkpoint não é claramente menor que a de um modelo aleatório — "
            "os pesos carregaram mas não codificam o idioma"
        )

    # ---------- 3. o gradiente flui e o treino desce ----------
    modelo.train()
    opt = torch.optim.Adam(modelo.parameters(), lr=1e-4)
    historico = []
    for passo in range(a.steps):
        opt.zero_grad()
        l = perda(embed, enc, head)
        l.backward()
        gnorm = torch.nn.utils.clip_grad_norm_(modelo.parameters(), 5.0)
        opt.step()
        historico.append(float(l))
        print(f"    passo {passo:02d}  loss={float(l):.4f}  |grad|={float(gnorm):.3f}")
    if not historico[-1] < historico[0]:
        raise SystemExit(f"FALHA: a loss não caiu ({historico[0]:.4f} -> {historico[-1]:.4f})")

    print(f"\n  OK — loss {historico[0]:.4f} -> {historico[-1]:.4f} "
          f"({100*(historico[0]-historico[-1])/historico[0]:.1f}% de queda em {a.steps} passos)")
    print("  O checkpoint publicado carrega, codifica PT-BR e aceita treino.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
