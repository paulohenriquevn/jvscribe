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


def test_dump_binario_de_eval_continua_ignorado():
    """O golden `.f32` vivia em `crates/`, removido com o runtime Rust em 2026-07-30.

    A regra `*.f32` permanece porque protege os dumps de eval (`fleurs_one.f32`, 214 KB) de
    entrarem no histórico. Se um golden voltar a ser versionado, adicione a negação DEPOIS da
    regra geral — a ordem é o que determina quem vence em `.gitignore`.
    """
    assert _is_ignored("data/eval/fleurs/fleurs_one.f32"), (
        "dump binário de eval não pode ser versionável"
    )


# --- regressão inversa: o que DEVE continuar ignorado ---------------------------


def test_pesos_de_modelo_continuam_ignorados():
    """Invariante do dono: modelo nunca entra no histórico do git."""
    for p in ("models/m0-borrowed/encoder-model.onnx", "models.zip", "data/corpus.wav"):
        assert _is_ignored(p), f"{p} DEVERIA continuar ignorado"


# Havia aqui um `_obsoleto_test_dump_de_eval_f32` — desabilitado por prefixo no nome, de modo
# que o pytest não o coletava. Um teste que não roda não protege nada e ainda parece cobertura
# (`testing.md § 6`). Sua metade viva está em `test_dump_binario_de_eval_continua_ignorado`
# acima; a outra metade assertava um caminho da árvore Rust (`crates/`), removida em
# 2026-07-30, e teria falhado se alguém a reativasse.
