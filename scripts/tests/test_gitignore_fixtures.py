"""T2.1 (M9) — as fixtures determinísticas não podem ser ignoradas pelo git.

Bug latente medido em 2026-07-30: `.gitignore:15` ignora `*.wav`; `:17` reabre a exceção
`!tests/fixtures/*.wav`; e `:57`/`:58` repetem `*.wav`/`*.f32` **depois** — e em `.gitignore`
o último padrão que casa vence. A exceção estava morta.

As fixtures atuais sobrevivem apenas porque já estão no index (git não aplica regra de ignore
a arquivo rastreado). Qualquer fixture NOVA — ou uma regeneração seguida de `git add` —
desapareceria em silêncio, e o CI perderia as fixtures determinísticas de que 5 arquivos de
teste dependem.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _is_ignored(relpath: str) -> bool:
    """True se o git ignoraria este caminho (usa --no-index: não precisa existir)."""
    r = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", relpath],
        cwd=REPO,
        capture_output=True,
    )
    return r.returncode == 0


def test_fixture_wav_nova_nao_e_ignorada():
    assert not _is_ignored("tests/fixtures/__probe_nova.wav"), (
        "uma fixture .wav nova em tests/fixtures/ está sendo ignorada — "
        "a exceção do .gitignore foi anulada por um padrão posterior"
    )


def test_golden_f32_novo_nao_e_ignorado():
    assert not _is_ignored("crates/macaw-audio/tests/fixtures/__probe_novo.f32"), (
        "o golden .f32 do kaldi_fbank está sendo ignorado — o teste de conformidade "
        "cross-language contra o lhotse perderia sua fixture"
    )


# --- regressão inversa: o que DEVE continuar ignorado ---------------------------


def test_pesos_de_modelo_continuam_ignorados():
    """Invariante do dono: modelo nunca entra no histórico do git."""
    for p in ("models/m0-borrowed/encoder-model.onnx", "models.zip", "data/corpus.wav"):
        assert _is_ignored(p), f"{p} DEVERIA continuar ignorado"


def test_dump_de_eval_f32_continua_ignorado():
    """Regressão pega durante a própria T2.1.

    A primeira tentativa de corrigir o shadowing removeu a regra `*.f32` inteira — o que
    tornaria `training/results/onnx/fleurs_one.f32` (214 K de dump de eval) rastreável num
    `git add`. A correção certa é regra geral SEGUIDA da exceção, não ausência de regra.
    """
    assert _is_ignored("training/results/onnx/fleurs_one.f32"), (
        "dump binário de eval não pode ser versionável"
    )
    assert not _is_ignored("crates/macaw-audio/tests/fixtures/kaldi_fbank80_golden.f32"), (
        "o golden do kaldi_fbank É versionado — é a âncora do teste cross-language"
    )
