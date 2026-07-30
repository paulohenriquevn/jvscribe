"""Adapter lhotse do canal telefônico do M3 para augmentação ON-THE-FLY (M5 —
Task 2.1, blueprint `m5-scale-model-wer-blueprint.md` Q3/Q6/EC-2, plano ADR D2).

`telephone_channel.apply_telephone_channel(samples, sr) -> (samples_8k, 8000)` é
função numpy pura, criada para o builder OFFLINE de teste (`make_telephone_test.py`,
M4) — NÃO é um callable `CutSet -> CutSet` que a lista `cut_transforms` do
datamodule icefall espera (blueprint Q3/EC-2, achado registrado no plano). Este
módulo é o adapter fino que a torna aplicável on-the-fly, SEM reimplementar o DSP
(Regra 9 — "não reinvente a roda"): toda a física do canal (banda 300-3400 Hz +
G.711 A-law) permanece 100% em `apply_telephone_channel`; o único código novo aqui
é o glue de shape/sample-rate exigido pelo contrato `AudioTransform` do lhotse.

## Mecanismo lhotse usado (achado por leitura de código, não invenção)

`AudioTransform` (`lhotse/augmentation/transform.py`) é uma dataclass registrada
(`AudioTransform.KNOWN_TRANSFORMS`) com `__call__(self, samples, sampling_rate) ->
np.ndarray`, aplicada LAZILY:

  - por `Recording.load_audio()` quando anexada a `Recording.transforms` — o
    MESMO ponto de extensão que `Narrowband`/`Volume`/`Speed`
    (`lhotse/augmentation/torchaudio.py`) usam. `Recording.narrowband()` é o
    precedente mais próximo do nosso caso: roda a codec a 8 kHz e resample de
    volta (`restore_orig_sr=True`) para não alterar `num_samples`/`duration`
    do resto do pipeline;
  - por `MixedCut.load_audio()` quando anexada a `MixedCut.transforms` — campo
    PRÓPRIO do `MixedCut` (distinto de `Recording.transforms`), documentado
    como "aplicado ao track APÓS a mixagem" (`lhotse/cut/mixed.py` docstring).

Isso resolve o problema físico da ADR D2 (`Reverb → CutMix(ruído) →
telephone_channel`, telephone por ÚLTIMO): como o telephone entra DEPOIS de
`CutMix(MUSAN)` na lista `cut_transforms`, o cut que chega até nós pode já ser
um `MixedCut` (quando o CutMix disparou, `p=0.5`) — `TelephoneChannelTransform`
trata os dois casos (`MonoCut`/`MultiCut` via `Recording.transforms`, `MixedCut`
via `MixedCut.transforms`), reusando em ambos o MESMO `TelephoneChannel`.

Como `Narrowband`, resample-se de volta à sample-rate de entrada depois da
degradação 8 kHz — preserva `num_samples`/`duration` sem tocar os metadados do
`Recording`/`Cut` (invariante Q6: duração preservada, replicado no teste de
contrato).

## Decisão ON-THE-FLY vs OFFLINE (honesta, avaliada por pedido explícito da task)

Considerado e REJEITADO pré-bakear o canal telefônico offline (aplicá-lo 1x em
disco antes do treino — afinal, ao contrário de ruído/RIR, o DSP em si É
determinístico dado um input fixo):

  1. **A ordem física D2 quebra a premissa.** O canal é o ÚLTIMO estágio
     (sala → ruído ambiente → codec) — entra DEPOIS de Reverb e CutMix, que
     SÃO randomizados por época (RIR sorteado, clipe de ruído sorteado, SNR
     sorteado, `p<1` de aplicar ou não). O INPUT do estágio telefônico muda a
     cada época; não dá pra pré-computar "o resultado do canal" independente
     dessa randomização anterior sem violar a ordem (aplicar telefone ANTES
     de reverb/ruído seria fisicamente errado — banda-limitaria o ruído/
     reverb, alternativa já rejeitada na ADR D2) ou sem achatar TODA a cadeia
     randomizada num único artefato em disco (mata a diversidade por época).
  2. **Regra inviolável do domínio deste agente.** "A augmentação nunca é
     materializada em disco: mata a diversidade por época. On-the-fly ou não
     entra" (mandato do `audio-dsp-engineer`, espelha `ROADMAP.md` M3). Pré-
     bakear violaria isso mesmo que só para o estágio telefônico isolado.
  3. Onde offline FAZ sentido — e é exatamente o que M3/M4/M5 já fazem — é
     para os TEST SETS (`training/make_telephone_test.py`,
     `training/make_coraa_test.py` da Task 3.1): lá não há augmentação por
     época a preservar; o objetivo é um artefato de avaliação FIXO e
     reprodutível (mesmos IDs, mesmas refs, pareável no bootstrap). A
     distinção é TREINO (on-the-fly, este módulo) vs TEST (offline, builders
     dedicados) — nunca o inverso.

## Onde este módulo mora na instância

Import FLAT (`from telephone_channel import apply_telephone_channel`), mesma
convenção de `training/make_telephone_test.py`: o runbook de treino copia
`telephone_channel.py` + este arquivo para o MESMO diretório do
`asr_datamodule.py` patcheado (`egs/commonvoice/ASR/zipformer/`) — sem isso o
`from telephone_channel_transform import TelephoneChannelTransform` que
`prep_augment_datamodule.py` injeta não resolve.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import gcd
from typing import Union

import numpy as np
from lhotse import CutSet
from lhotse.augmentation import AudioTransform
from lhotse.cut.mixed import MixedCut
from lhotse.utils import fastcopy
from scipy.signal import resample_poly

from telephone_channel import apply_band, apply_telephone_channel  # noqa: F401
import codec_pool


def _resample_to(samples: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Glue de sample-rate (NÃO é o DSP do canal — isso é 100% de
    `apply_telephone_channel`). Mesmo padrão gcd+resample_poly já usado em
    `telephone_channel.py` (passo 1, resample 16k->8k) e em
    `make_telephone_test.py::_resample` (o glue de volta a 16 kHz do
    experimento de M4); mantido local e pequeno aqui em vez de extraído como
    um 3º import compartilhado — ~4 linhas, sem lógica de domínio/DSP, baixo
    risco de divergência (`parsimony-ladder.md` rung 5 + tensão DRY-vs-KISS de
    `CLAUDE.md`: "se eliminar duplicação cria uma abstração que ninguém
    entende, prefira a duplicação"; o conhecimento de domínio — banda+A-law —
    não está duplicado, só um one-liner de reamostragem)."""
    if sr_from == sr_to:
        return samples
    g = gcd(int(sr_from), int(sr_to))
    return resample_poly(samples, sr_to // g, sr_from // g).astype(np.float32)


@dataclass
class TelephoneChannel(AudioTransform):
    """`AudioTransform` lazy: banda 300-3400 Hz + um codec do pool (ADR D3/D4).

    `codec` é o único campo (default `g711a` = a cadeia clássica retrocompatível =
    `apply_band` + G.711 A-law). Round-trip de serialização: `{"codec": "..."}`. O codec
    é escolhido por-cut pelo `TelephoneChannelTransform` (RNG seedado), não aqui."""

    codec: str = "g711a"

    def __call__(self, samples: np.ndarray, sampling_rate: int) -> np.ndarray:
        mono = samples.ndim == 1
        channels = samples[np.newaxis, :] if mono else samples
        orig_len = channels.shape[-1]

        degraded = []
        for channel in channels:
            band_8k, sr_8k = apply_band(channel.astype(np.float32), int(sampling_rate))
            samples_8k = codec_pool.apply_codec(band_8k, sr_8k, self.codec)
            restored = _resample_to(samples_8k, sr_8k, int(sampling_rate))
            # resample 16k->8k->16k pode variar +-1 amostra por arredondamento
            # do polyphase filter; forcamos o comprimento exato de volta (a
            # MESMA tecnica de `Recording.narrowband(restore_orig_sr=True)`,
            # `lhotse/augmentation/torchaudio.py:375-376`).
            degraded.append(np.resize(restored, (orig_len,)))

        out = np.stack(degraded, axis=0).astype(np.float32)
        return out[0] if mono else out

    def reverse_timestamps(self, offset, duration, sampling_rate):
        # o canal degrada a forma de onda, nao desloca nem corta o eixo do
        # tempo -- mesma decisao de `Narrowband.reverse_timestamps`
        # (torchaudio.py:380-391): retorna offset/duration inalterados.
        return offset, duration


class TelephoneChannelTransform:
    """Transform `CutSet -> CutSet` para a lista `cut_transforms` do
    datamodule (ADR D2 -- ultimo estagio da cadeia fisica). Molde de
    `ReverbWithImpulseResponse`/`PerturbVolume`
    (`lhotse/dataset/cut_transforms/`): mesmo contrato `p` + RNG seedado, mesmo
    default determinístico `seed=42` de `CutMix` (`mix.py`).

    Trata os DOIS formatos de cut que podem chegar aqui (D2 coloca telephone
    DEPOIS de CutMix na lista `cut_transforms`): `MonoCut`/`MultiCut` (tem
    `.recording`) e `MixedCut` (já mixado pelo CutMix -- tem seu PRÓPRIO campo
    `.transforms`, aplicado pós-mix, ver docstring do módulo). Um cut sem
    nenhum dos dois (ex.: só features pré-computadas, sem `Recording`) é erro
    fail-fast -- é exatamente a restrição EC-P1/D2 (`--on-the-fly-feats`
    obrigatório para a augmentação de canal fazer sentido).
    """

    def __init__(
        self,
        p: float = 0.5,
        seed: Union[int, random.Random] = 42,
        preserve_id: bool = False,
        codecs: dict[str, float] | None = None,
    ) -> None:
        self.p = p
        self.random = seed if isinstance(seed, random.Random) else random.Random(seed)
        self.preserve_id = preserve_id
        # pool de codecs (ADR D3): default = todos os realistas; {"g711a":1.0} recupera o legado
        self.codecs = dict(codecs) if codecs else dict(codec_pool.POOL_DEFAULT)

    def _sample_codec(self) -> str:
        names = list(self.codecs)
        weights = [self.codecs[c] for c in names]
        return self.random.choices(names, weights=weights, k=1)[0]

    def __call__(self, cuts: CutSet) -> CutSet:
        return CutSet.from_cuts(self._maybe_apply(cut) for cut in cuts)

    def _maybe_apply(self, cut):
        if self.random.random() > self.p:
            return cut
        codec = self._sample_codec()
        if isinstance(cut, MixedCut):
            return self._apply_to_mixed(cut, codec)
        if getattr(cut, "has_recording", False):
            return self._apply_to_recording_backed(cut, codec)
        raise TypeError(
            f"TelephoneChannelTransform: cut {cut.id!r} (tipo "
            f"{type(cut).__name__}) nao tem Recording nem e MixedCut -- nao "
            "ha audio para degradar (features pre-computadas sem "
            "--on-the-fly-feats? ver EC-P1/ADR D2)."
        )

    def _apply_to_recording_backed(self, cut, codec: str = "g711a"):
        existing = list(cut.recording.transforms) if cut.recording.transforms else []
        new_recording = fastcopy(
            cut.recording, transforms=existing + [TelephoneChannel(codec=codec)]
        )
        return fastcopy(
            cut,
            id=cut.id if self.preserve_id else f"{cut.id}_tel",
            recording=new_recording,
        )

    def _apply_to_mixed(self, cut: MixedCut, codec: str = "g711a") -> MixedCut:
        existing = list(cut.transforms) if cut.transforms else []
        return fastcopy(
            cut,
            id=cut.id if self.preserve_id else f"{cut.id}_tel",
            transforms=existing + [TelephoneChannel(codec=codec)],
        )
