"""Patch determinístico: cabeça de fonema auxiliar no Zipformer-CTC (M4 fase 3 —
task #20, PRD §8.1: "supervisão fonética auxiliar em camada intermediária,
agnóstica ao decoder"). Regra 9 — NÃO reescreve o loop/loss/model do icefall; edita
in-place `zipformer/{zipformer.py,model.py,train.py}` com substrings exatas
(assert count==1, senão falha alto) e valida compilação — mesmo idioma de
`patch_ctc_decode.py` já usado neste projeto.

⚠️ NÃO usar o `jvscribe/smoke/train_ctc.py` como base (rebaixado a smoke-only:
bug de src_key_padding_mask ausente + cabeça ad-hoc — ver docstring do próprio
arquivo). Esta extensão parte da recipe REAL (train.py/model.py/zipformer.py).

Design (documentado para auditoria — não é fork ambíguo, é mecanismo já existente):

1. `Zipformer2.forward()` (zipformer.py) JÁ acumula o output de cada stack em uma
   lista `outputs` (linha ~345, usada por `_get_full_dim_output` para concatenar
   dimensões). Todo `outputs[i]` compartilha o MESMO T que `x_lens` (o
   `DownsampledZipformer2Encoder` faz downsample+upsample internamente por stack) —
   então nenhuma reconciliação de comprimento é necessária. O patch só GUARDA
   `outputs[aux_ctc_layer_idx]` como atributo (`self.aux_ctc_output`), sem mudar a
   assinatura de `forward()` (EncoderInterface intocado — decode/export/streaming
   continuam idênticos quando `aux_ctc_layer_idx=None`, o default).

2. Índice do stack intermediário: o menor `i` tal que a soma cumulativa de
   `num_encoder_layers[0..i]` cobre ≥50% do total de camadas do encoder —
   "camada intermediária" por profundidade real, não por índice de stack (o
   Zipformer é um U-Net com downsampling desigual; profundidade em CAMADAS é a
   métrica certa). Para `small` (num-encoder-layers 2,2,2,2,2,2 = 12 total):
   cumsum após stack 2 = 6 = exatamente 50% → aux_ctc_layer_idx=2 (dim 256).
   Grounded em Lee & Watanabe 2021 (Intermediate Loss Regularization for
   CTC-based ASR) — colocação em ~metade da profundidade é a prática padrão da
   literatura de "self-conditioned/intermediate CTC" citada no PRD §8.1.

3. `AsrModel` (model.py) ganha uma 2ª cabeça CTC (`phoneme_output`, linear +
   log-softmax) lendo `self.encoder.aux_ctc_output`. Existe só quando
   `phoneme_vocab_size>0` — produção (`phoneme_vocab_size=0`, default) não
   instancia a cabeça: zero custo, zero mudança de comportamento (PRD §8.1: "Na
   inferência é removida... custo em produção é exatamente zero").

4. `train.py::compute_loss` faz lookup de fonemas por TEXTO (mesmo idioma do
   smoke `train_ctc.py::collate`, agora sobre a recipe real) via
   `phoneme_targets.json` (gerado por `gen_phonemes.py`), soma
   `phoneme_loss_scale * phoneme_loss` ao loss total. Peso default 0.3 —
   [ESTIMATIVA] consistente com a faixa usada na literatura de intermediate-CTC
   (tipicamente 0.3-0.5 para uma única cabeça auxiliar); não há medição própria
   deste peso — é hyperparameter de partida, ajustável sem re-patch (flag CLI).

Uso (NA instância, em egs/commonvoice/ASR):
    python3 /workspace/prep_phoneme_head.py
Idempotente: se os patches já foram aplicados (padrão novo já presente), sai OK
sem duplicar. Faz backup .orig-phoneme-patch de cada arquivo tocado antes de escrever.
"""

from __future__ import annotations

import argparse

import py_compile
import sys
from pathlib import Path

ZIPFORMER_DIR = Path("/workspace/icefall/egs/commonvoice/ASR/zipformer")

# A REVISÃO do icefall contra a qual estes patches foram escritos — `[MEDIDO]` 2026-07-31,
# bissecção sobre o histórico do upstream.
#
# Os três patchers (`prep_phoneme_head`, `prep_finetune`, `prep_augment_datamodule`) aplicam
# `PATCH_OK` neste commit e o resultado compila. Contra o `HEAD` do icefall, `model.py` falha:
# `693d84a` (2024-10-21, "Add Consistency-Regularized CTC" #1766) inseriu `forward_ctc` com
# `return ctc_loss, cr_loss` ENTRE a âncora e `def forward_transducer`, e o padrão deixou de
# casar. `f84270c` é o pai desse commit — o último em que a âncora bate.
#
# Isto não estava registrado em lugar nenhum do repositório. Sem o pino, a falha só aparece
# na hora de preparar o treino — numa GPU alugada, com a instância já rodando.
#
# `egs/commonvoice/ASR/zipformer/model.py` é SYMLINK para o de `librispeech`; a bissecção tem
# de ser feita no alvo, senão o histórico parece ter um commit só.
ICEFALL_REV_TESTADO = "f84270c"
ICEFALL_REV_QUEBROU = "693d84a"


def apply_patch(path: Path, repls: list[tuple[str, str]], already_applied_marker: str) -> None:
    src = path.read_text()

    if already_applied_marker in src:
        print(f"[phoneme-head] {path.name}: patch já aplicado (marcador presente) — pulando")
        return

    backup = path.with_suffix(path.suffix + ".orig-phoneme-patch")
    if not backup.exists():
        backup.write_text(src)

    for old, new in repls:
        count = src.count(old)
        if count != 1:
            sys.exit(
                f"FALHA: padrão não bate 1x em {path} (bateu {count}x):\n"
                f"{old[:200]!r}\n\n"
                f"Causa provável: o icefall mudou. Estes patches foram escritos contra "
                f"`{ICEFALL_REV_TESTADO}` e param de casar a partir de "
                f"`{ICEFALL_REV_QUEBROU}` (Consistency-Regularized CTC, #1766).\n"
                f"  git -C <icefall> worktree add --detach ../icefall-{ICEFALL_REV_TESTADO} "
                f"{ICEFALL_REV_TESTADO}\n"
                f"e aponte --zipformer-dir/--train-py/--datamodule-py para lá. Reescrever a "
                f"âncora para o icefall novo exige revalidar o treino — não é troca de string."
            )
        src = src.replace(old, new)

    path.write_text(src)
    py_compile.compile(str(path), doraise=True)
    print(f"[phoneme-head] {path.name}: patch aplicado e compila OK")


def patch_zipformer_py(zipformer_dir: Path = ZIPFORMER_DIR) -> None:
    path = zipformer_dir / "zipformer.py"
    marker = "aux_ctc_layer_idx"
    repls = [
        (
            "        chunk_size: Tuple[int] = [-1],\n"
            "        left_context_frames: Tuple[int] = [-1],\n"
            "    ) -> None:\n"
            "        super(Zipformer2, self).__init__()",
            "        chunk_size: Tuple[int] = [-1],\n"
            "        left_context_frames: Tuple[int] = [-1],\n"
            "        aux_ctc_layer_idx: Optional[int] = None,\n"
            "    ) -> None:\n"
            "        super(Zipformer2, self).__init__()",
        ),
        (
            "        self.causal = causal\n"
            "        self.chunk_size = chunk_size\n"
            "        self.left_context_frames = left_context_frames\n",
            "        self.causal = causal\n"
            "        self.chunk_size = chunk_size\n"
            "        self.left_context_frames = left_context_frames\n"
            "        # M4 fase 3 -- cabeça de fonema auxiliar (intermediate CTC,\n"
            "        # Lee & Watanabe 2021). None = comportamento original idêntico.\n"
            "        self.aux_ctc_layer_idx = aux_ctc_layer_idx\n"
            "        self.aux_ctc_output = None\n"
            "        self.aux_ctc_output_lens = None\n",
        ),
        (
            "            outputs.append(x)\n"
            "\n"
            "        # if the last output has the largest dimension, x will be unchanged,",
            "            outputs.append(x)\n"
            "\n"
            "        if self.aux_ctc_layer_idx is not None:\n"
            "            # captura o output do stack intermediario ANTES do downsample\n"
            "            # final; todo outputs[i] compartilha o mesmo T de x_lens (o\n"
            "            # DownsampledZipformer2Encoder upsample interno garante isso).\n"
            "            self.aux_ctc_output = outputs[self.aux_ctc_layer_idx]\n"
            "            self.aux_ctc_output_lens = x_lens\n"
            "\n"
            "        # if the last output has the largest dimension, x will be unchanged,",
        ),
    ]
    apply_patch(path, repls, marker)


def patch_model_py(zipformer_dir: Path = ZIPFORMER_DIR) -> None:
    path = zipformer_dir / "model.py"
    marker = "forward_phoneme_ctc"
    repls = [
        (
            "        use_transducer: bool = True,\n"
            "        use_ctc: bool = False,\n"
            "        use_attention_decoder: bool = False,\n"
            "    ):",
            "        use_transducer: bool = True,\n"
            "        use_ctc: bool = False,\n"
            "        use_attention_decoder: bool = False,\n"
            "        phoneme_vocab_size: int = 0,\n"
            "        phoneme_aux_dim: int = 0,\n"
            "    ):",
        ),
        (
            "        self.use_attention_decoder = use_attention_decoder\n"
            "        if use_attention_decoder:\n"
            "            self.attention_decoder = attention_decoder\n"
            "        else:\n"
            "            assert attention_decoder is None\n",
            "        self.use_attention_decoder = use_attention_decoder\n"
            "        if use_attention_decoder:\n"
            "            self.attention_decoder = attention_decoder\n"
            "        else:\n"
            "            assert attention_decoder is None\n"
            "\n"
            "        # M4 fase 3 -- cabeca de fonema auxiliar (PRD Sec.8.1). So existe\n"
            "        # durante o treino; producao usa phoneme_vocab_size=0 (default) =\n"
            "        # zero custo, zero mudanca de comportamento.\n"
            "        self.use_phoneme_ctc = phoneme_vocab_size > 0\n"
            "        if self.use_phoneme_ctc:\n"
            "            assert phoneme_aux_dim > 0, phoneme_aux_dim\n"
            "            self.phoneme_output = nn.Sequential(\n"
            "                nn.Dropout(p=0.1),\n"
            "                nn.Linear(phoneme_aux_dim, phoneme_vocab_size),\n"
            "                nn.LogSoftmax(dim=-1),\n"
            "            )\n",
        ),
        (
            "        return ctc_loss\n"
            "\n"
            "    def forward_transducer(\n",
            "        return ctc_loss\n"
            "\n"
            "    def forward_phoneme_ctc(\n"
            "        self,\n"
            "        targets: torch.Tensor,\n"
            "        target_lengths: torch.Tensor,\n"
            "    ) -> torch.Tensor:\n"
            "        \"\"\"CTC loss da cabeca de fonema auxiliar (M4 fase 3). Le o output\n"
            "        do stack intermediario que Zipformer2.forward() guardou em\n"
            "        self.encoder.aux_ctc_output (T, N, C) -- ja no formato que\n"
            "        F.ctc_loss espera, sem permute. So chamar quando self.use_phoneme_ctc.\"\"\"\n"
            "        aux = self.encoder.aux_ctc_output\n"
            "        aux_lens = self.encoder.aux_ctc_output_lens\n"
            "        assert aux is not None, (\n"
            "            \"aux_ctc_output vazio -- encoder.aux_ctc_layer_idx eh None?\"\n"
            "        )\n"
            "        phoneme_log_probs = self.phoneme_output(aux)  # (T, N, num_phones)\n"
            "        phoneme_loss = torch.nn.functional.ctc_loss(\n"
            "            log_probs=phoneme_log_probs,\n"
            "            targets=targets.cpu(),\n"
            "            input_lengths=aux_lens.cpu(),\n"
            "            target_lengths=target_lengths.cpu(),\n"
            "            reduction=\"sum\",\n"
            "        )\n"
            "        return phoneme_loss\n"
            "\n"
            "    def forward_transducer(\n",
        ),
        (
            "        prune_range: int = 5,\n"
            "        am_scale: float = 0.0,\n"
            "        lm_scale: float = 0.0,\n"
            "    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:\n"
            "        \"\"\"\n"
            "        Args:\n"
            "          x:\n"
            "            A 3-D tensor of shape (N, T, C).",
            "        prune_range: int = 5,\n"
            "        am_scale: float = 0.0,\n"
            "        lm_scale: float = 0.0,\n"
            "        phoneme_targets: Optional[torch.Tensor] = None,\n"
            "        phoneme_target_lengths: Optional[torch.Tensor] = None,\n"
            "    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:\n"
            "        \"\"\"\n"
            "        Args:\n"
            "          x:\n"
            "            A 3-D tensor of shape (N, T, C).",
        ),
        (
            "        else:\n"
            "            attention_decoder_loss = torch.empty(0)\n"
            "\n"
            "        return simple_loss, pruned_loss, ctc_loss, attention_decoder_loss",
            "        else:\n"
            "            attention_decoder_loss = torch.empty(0)\n"
            "\n"
            "        if self.use_phoneme_ctc:\n"
            "            assert phoneme_targets is not None and phoneme_target_lengths is not None\n"
            "            phoneme_loss = self.forward_phoneme_ctc(\n"
            "                targets=phoneme_targets,\n"
            "                target_lengths=phoneme_target_lengths,\n"
            "            )\n"
            "        else:\n"
            "            phoneme_loss = torch.empty(0)\n"
            "\n"
            "        return simple_loss, pruned_loss, ctc_loss, attention_decoder_loss, phoneme_loss",
        ),
    ]
    apply_patch(path, repls, marker)


def patch_train_py(zipformer_dir: Path = ZIPFORMER_DIR) -> None:
    path = zipformer_dir / "train.py"
    marker = "use_phoneme_ctc"
    repls = [
        (
            "import logging\nimport warnings\n",
            "import json\nimport logging\nimport warnings\n",
        ),
        (
            "    parser.add_argument(\n"
            "        \"--use-ctc\",\n"
            "        type=str2bool,\n"
            "        default=False,\n"
            "        help=\"If True, use CTC head.\",\n"
            "    )\n",
            "    parser.add_argument(\n"
            "        \"--use-ctc\",\n"
            "        type=str2bool,\n"
            "        default=False,\n"
            "        help=\"If True, use CTC head.\",\n"
            "    )\n"
            "\n"
            "    parser.add_argument(\n"
            "        \"--use-phoneme-ctc\",\n"
            "        type=str2bool,\n"
            "        default=False,\n"
            "        help=\"M4 fase 3 (PRD Sec.8.1): se True, adiciona cabeca CTC\"\n"
            "        \" de fonema auxiliar em camada intermediaria (custo zero em\"\n"
            "        \" producao -- so existe durante o treino).\",\n"
            "    )\n"
            "\n"
            "    parser.add_argument(\n"
            "        \"--phoneme-loss-scale\",\n"
            "        type=float,\n"
            "        default=0.3,\n"
            "        help=\"Peso da loss CTC de fonema no loss total. [ESTIMATIVA]\"\n"
            "        \" -- literatura de intermediate-CTC usa tipicamente 0.3-0.5.\",\n"
            "    )\n"
            "\n"
            "    parser.add_argument(\n"
            "        \"--phoneme-targets-json\",\n"
            "        type=str,\n"
            "        default=\"data/pt/phoneme_targets.json\",\n"
            "        help=\"Saida de gen_phonemes.py: {map: {texto: [ids fonema]},\"\n"
            "        \" num_phones: int}.\",\n"
            "    )\n",
        ),
        (
            "def get_encoder_model(params: AttributeDict) -> nn.Module:\n"
            "    encoder = Zipformer2(\n"
            "        output_downsampling_factor=2,\n",
            "def _aux_ctc_layer_idx(num_encoder_layers) -> int:\n"
            "    \"\"\"Menor indice de stack cuja soma cumulativa de camadas cobre >=50%\n"
            "    do total -- 'camada intermediaria' por profundidade real (M4 fase 3,\n"
            "    Lee & Watanabe 2021). Ver docstring de prep_phoneme_head.py.\"\"\"\n"
            "    total = sum(num_encoder_layers)\n"
            "    cum = 0\n"
            "    for i, n in enumerate(num_encoder_layers):\n"
            "        cum += n\n"
            "        if cum * 2 >= total:\n"
            "            return i\n"
            "    return len(num_encoder_layers) - 1\n"
            "\n"
            "\n"
            "def get_encoder_model(params: AttributeDict) -> nn.Module:\n"
            "    aux_idx = (\n"
            "        _aux_ctc_layer_idx(_to_int_tuple(params.num_encoder_layers))\n"
            "        if params.get(\"use_phoneme_ctc\", False)\n"
            "        else None\n"
            "    )\n"
            "    encoder = Zipformer2(\n"
            "        output_downsampling_factor=2,\n"
            "        aux_ctc_layer_idx=aux_idx,\n",
        ),
        (
            "    model = AsrModel(\n"
            "        encoder_embed=encoder_embed,\n"
            "        encoder=encoder,\n"
            "        decoder=decoder,\n"
            "        joiner=joiner,\n"
            "        encoder_dim=max(_to_int_tuple(params.encoder_dim)),\n"
            "        decoder_dim=params.decoder_dim,\n"
            "        vocab_size=params.vocab_size,\n"
            "        use_transducer=params.use_transducer,\n"
            "        use_ctc=params.use_ctc,\n"
            "    )\n"
            "    return model\n",
            "    phoneme_vocab_size = 0\n"
            "    phoneme_aux_dim = 0\n"
            "    if params.get(\"use_phoneme_ctc\", False):\n"
            "        ph_data = json.loads(Path(params.phoneme_targets_json).read_text())\n"
            "        phoneme_vocab_size = ph_data[\"num_phones\"]\n"
            "        aux_idx = _aux_ctc_layer_idx(_to_int_tuple(params.num_encoder_layers))\n"
            "        phoneme_aux_dim = _to_int_tuple(params.encoder_dim)[aux_idx]\n"
            "        params.num_phones = phoneme_vocab_size\n"
            "        params.aux_ctc_layer_idx = aux_idx\n"
            "        logging.info(\n"
            "            f\"[phoneme-head] vocab={phoneme_vocab_size} \"\n"
            "            f\"aux_ctc_layer_idx={aux_idx} aux_dim={phoneme_aux_dim} \"\n"
            "            f\"loss_scale={params.phoneme_loss_scale}\"\n"
            "        )\n"
            "\n"
            "    model = AsrModel(\n"
            "        encoder_embed=encoder_embed,\n"
            "        encoder=encoder,\n"
            "        decoder=decoder,\n"
            "        joiner=joiner,\n"
            "        encoder_dim=max(_to_int_tuple(params.encoder_dim)),\n"
            "        decoder_dim=params.decoder_dim,\n"
            "        vocab_size=params.vocab_size,\n"
            "        use_transducer=params.use_transducer,\n"
            "        use_ctc=params.use_ctc,\n"
            "        phoneme_vocab_size=phoneme_vocab_size,\n"
            "        phoneme_aux_dim=phoneme_aux_dim,\n"
            "    )\n"
            "    return model\n",
        ),
        (
            "    texts = batch[\"supervisions\"][\"text\"]\n"
            "    y = sp.encode(texts, out_type=int)\n"
            "    y = k2.RaggedTensor(y)\n"
            "\n"
            "    with torch.set_grad_enabled(is_training):\n"
            "        losses = model(\n"
            "            x=feature,\n"
            "            x_lens=feature_lens,\n"
            "            y=y,\n"
            "            prune_range=params.prune_range,\n"
            "            am_scale=params.am_scale,\n"
            "            lm_scale=params.lm_scale,\n"
            "        )\n"
            "        simple_loss, pruned_loss, ctc_loss = losses[:3]\n"
            "\n"
            "        loss = 0.0\n",
            "    texts = batch[\"supervisions\"][\"text\"]\n"
            "    y = sp.encode(texts, out_type=int)\n"
            "    y = k2.RaggedTensor(y)\n"
            "\n"
            "    phoneme_targets = phoneme_target_lengths = None\n"
            "    if params.get(\"use_phoneme_ctc\", False):\n"
            "        ph_map = _get_phoneme_map(params.phoneme_targets_json)\n"
            "        ph_seqs = [ph_map.get(t, [1]) for t in texts]  # 1 = <unk> fonema\n"
            "        phoneme_targets = torch.tensor(\n"
            "            [i for seq in ph_seqs for i in seq], dtype=torch.long\n"
            "        ).to(device)\n"
            "        phoneme_target_lengths = torch.tensor(\n"
            "            [len(seq) for seq in ph_seqs], dtype=torch.long\n"
            "        )\n"
            "\n"
            "    with torch.set_grad_enabled(is_training):\n"
            "        losses = model(\n"
            "            x=feature,\n"
            "            x_lens=feature_lens,\n"
            "            y=y,\n"
            "            prune_range=params.prune_range,\n"
            "            am_scale=params.am_scale,\n"
            "            lm_scale=params.lm_scale,\n"
            "            phoneme_targets=phoneme_targets,\n"
            "            phoneme_target_lengths=phoneme_target_lengths,\n"
            "        )\n"
            "        simple_loss, pruned_loss, ctc_loss = losses[:3]\n"
            "\n"
            "        loss = 0.0\n",
        ),
        (
            "        if params.use_ctc:\n"
            "            loss += params.ctc_loss_scale * ctc_loss\n"
            "\n"
            "    assert loss.requires_grad == is_training\n",
            "        if params.use_ctc:\n"
            "            loss += params.ctc_loss_scale * ctc_loss\n"
            "\n"
            "        if params.get(\"use_phoneme_ctc\", False):\n"
            "            phoneme_loss = losses[4]\n"
            "            loss += params.phoneme_loss_scale * phoneme_loss\n"
            "\n"
            "    assert loss.requires_grad == is_training\n",
        ),
        (
            "    if params.use_ctc:\n"
            "        info[\"ctc_loss\"] = ctc_loss.detach().cpu().item()\n"
            "\n"
            "    return loss, info\n",
            "    if params.use_ctc:\n"
            "        info[\"ctc_loss\"] = ctc_loss.detach().cpu().item()\n"
            "    if params.get(\"use_phoneme_ctc\", False):\n"
            "        info[\"phoneme_loss\"] = phoneme_loss.detach().cpu().item()\n"
            "\n"
            "    return loss, info\n",
        ),
    ]
    apply_patch(path, repls, marker)

    # helper _get_phoneme_map -- cache global simples, carregado 1x (nao muda por
    # epoca). Injetado como bloco separado antes de compute_loss para nao poluir o
    # dict de repls acima com um trecho multi-linha isolado.
    src = path.read_text()
    cache_marker = "_PHONEME_MAP_CACHE"
    if cache_marker not in src:
        anchor = "def compute_loss(\n"
        count = src.count(anchor)
        if count != 1:
            sys.exit(f"FALHA: âncora de compute_loss não bate 1x em {path} (bateu {count}x)")
        helper = (
            "_PHONEME_MAP_CACHE: Dict[str, dict] = {}\n"
            "\n"
            "\n"
            "def _get_phoneme_map(path: str) -> dict:\n"
            "    \"\"\"Carrega phoneme_targets.json 1x e cacheia (M4 fase 3).\"\"\"\n"
            "    if path not in _PHONEME_MAP_CACHE:\n"
            "        data = json.loads(Path(path).read_text())\n"
            "        _PHONEME_MAP_CACHE[path] = data[\"map\"]\n"
            "    return _PHONEME_MAP_CACHE[path]\n"
            "\n"
            "\n"
        )
        src = src.replace(anchor, helper + anchor, 1)
        path.write_text(src)
        py_compile.compile(str(path), doraise=True)
        print(f"[phoneme-head] {path.name}: helper _get_phoneme_map injetado, compila OK")


def main() -> None:
    # Os dois irmãos que patcham a MESMA árvore (`prep_finetune`, `prep_augment_datamodule`)
    # aceitam o caminho por flag; este o tinha cravado, e só rodava numa máquina onde
    # `/workspace/icefall` existisse. Um clone em qualquer outro lugar era inalcançável.
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zipformer-dir", type=Path, default=ZIPFORMER_DIR,
                    help="diretório egs/commonvoice/ASR/zipformer do icefall")
    d = ap.parse_args().zipformer_dir
    if not d.exists():
        sys.exit(f"FALHA: {d} não existe — passe --zipformer-dir apontando para o clone "
                 f"do icefall (egs/commonvoice/ASR/zipformer).")
    patch_zipformer_py(d)
    patch_model_py(d)
    patch_train_py(d)
    print("PATCH_OK: cabeça de fonema auxiliar aplicada em zipformer.py + model.py + train.py")


if __name__ == "__main__":
    main()
