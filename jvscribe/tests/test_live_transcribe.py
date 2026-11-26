"""Núcleo da app de transcrição ao vivo em dois canais.

Testa o que é lógica de negócio — rotulagem de falante, montagem de turnos e o veredito
contra os RNF de real-time — sem tocar em áudio, modelo ou hardware. A captura tem os seus
próprios testes em `test_dual_capture.py`.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "common"))
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

from live_transcribe import MetricasRNF, Transcricao, rotular  # noqa: E402


# --- rotulagem de falante -------------------------------------------------
# No caso 1:1 a diarização não precisa existir: o mic É o atendente por construção e o
# loopback É o cliente. Errar este mapeamento troca quem disse o quê.

def test_mic_e_o_atendente_e_loopback_e_o_cliente():
    assert rotular("mic") == "ATENDENTE"
    assert rotular("loopback") == "CLIENTE"


def test_rotulo_desconhecido_falha_alto_em_vez_de_inventar_falante():
    """Negativo: um label não previsto não pode virar 'ATENDENTE' por default."""
    with pytest.raises(ValueError, match="desconhecido"):
        rotular("microfone")


# --- montagem de turnos ---------------------------------------------------

def test_palavras_do_mesmo_falante_em_sequencia_viram_um_turno_so():
    t = Transcricao()
    t.adicionar("mic", ["bom", "dia"], 1.0)
    t.adicionar("mic", ["senhor"], 1.6)
    assert [(x.falante, x.texto) for x in t.turnos] == [("ATENDENTE", "bom dia senhor")]


def test_troca_de_falante_abre_turno_novo():
    t = Transcricao()
    t.adicionar("mic", ["bom", "dia"], 1.0)
    t.adicionar("loopback", ["oi"], 2.0)
    t.adicionar("mic", ["pois", "não"], 3.0)
    assert [(x.falante, x.texto) for x in t.turnos] == [
        ("ATENDENTE", "bom dia"), ("CLIENTE", "oi"), ("ATENDENTE", "pois não"),
    ]


def test_lista_vazia_de_palavras_nao_cria_turno():
    """Uma rodada de decode sem palavra confirmada é o caso COMUM — não pode poluir a saída."""
    t = Transcricao()
    t.adicionar("mic", [], 1.0)
    assert t.turnos == []


# --- métricas de RNF ------------------------------------------------------

def test_rtfx_e_audio_processado_dividido_por_tempo_de_parede():
    m = MetricasRNF()
    m.registrar(audio_s=1.0, wall_s=0.1, latencia_s=0.05, backlog=0)
    m.registrar(audio_s=1.0, wall_s=0.1, latencia_s=0.05, backlog=0)
    assert m.resumo()["rtfx"] == pytest.approx(10.0)


def test_p99_enxerga_a_cauda_que_a_media_esconde():
    """p99 tem de refletir a CAUDA — reportar média esconde o que quebra o produto
    (asr-evidence-discipline.md § 3, falácia #3).

    A cauda são 2 de 100 amostras: por definição de percentil, 1 outlier em 100 NÃO entra
    no p99 (99% das amostras ficariam abaixo dele) — e o teste não deve exigir isso.
    """
    m = MetricasRNF()
    for i in range(100):                      # 98 amostras de 10 ms e duas de 5 s
        m.registrar(audio_s=0.5, wall_s=0.01,
                    latencia_s=(5.0 if i >= 98 else 0.010), backlog=0)
    r = m.resumo()
    media_ms = 1000 * (98 * 0.010 + 2 * 5.0) / 100
    assert r["p50_ms"] == pytest.approx(10.0, abs=0.5)
    assert r["p99_ms"] > 1000, "o p99 tem de enxergar a cauda de 5 s"
    assert r["p99_ms"] > media_ms, "a média dilui a cauda; é por isso que o RNF-02 é p99"


def test_um_unico_outlier_em_100_nao_entra_no_p99():
    """Guarda a semântica: p99 é 'valor abaixo do qual ficam 99% das amostras'.

    Sem este teste, alguém 'consertaria' o percentil para pegar o máximo — e o RNF-02
    passaria a reprovar por um pico isolado, que é exatamente o que o percentil existe
    para tolerar.
    """
    m = MetricasRNF()
    for i in range(100):
        m.registrar(audio_s=0.5, wall_s=0.01,
                    latencia_s=(5.0 if i == 99 else 0.010), backlog=0)
    assert m.resumo()["p99_ms"] == pytest.approx(10.0, abs=0.5)


def test_resumo_sem_amostras_nao_divide_por_zero():
    """Negativo: chamar o resumo antes de qualquer decode não pode explodir."""
    r = MetricasRNF().resumo()
    assert r["amostras"] == 0 and r["rtfx"] is None and r["p99_ms"] is None


# --- veredito contra os limiares de RNF -------------------------------

def test_veredito_aprova_quando_os_tres_criterios_sao_atendidos():
    m = MetricasRNF()
    for _ in range(50):
        m.registrar(audio_s=1.0, wall_s=0.2, latencia_s=0.100, backlog=0)   # RTFx 5x, 100ms
    v = m.veredito()
    assert v["RNF-01"].aprovado and v["RNF-02"].aprovado and v["RNF-03"].aprovado


def test_veredito_reprova_rtfx_abaixo_de_3x():
    m = MetricasRNF()
    for _ in range(50):
        m.registrar(audio_s=1.0, wall_s=0.5, latencia_s=0.100, backlog=0)   # RTFx 2x
    assert not m.veredito()["RNF-01"].aprovado


def test_veredito_reprova_p99_acima_de_500ms():
    m = MetricasRNF()
    for i in range(100):
        m.registrar(audio_s=1.0, wall_s=0.1,
                    latencia_s=(0.900 if i > 90 else 0.100), backlog=0)
    assert not m.veredito()["RNF-02"].aprovado


def test_veredito_reprova_backlog_presente_em_mais_de_0_1_por_cento():
    m = MetricasRNF()
    for i in range(1000):
        m.registrar(audio_s=1.0, wall_s=0.1, latencia_s=0.05, backlog=(3 if i < 5 else 0))
    v = m.veredito()
    assert not v["RNF-03"].aprovado
    assert "0,5%" in v["RNF-03"].medido or "0.5" in v["RNF-03"].medido


def test_veredito_declara_o_medido_e_o_alvo_para_cada_criterio():
    """Um veredito sem o número medido ao lado do alvo é opinião, não evidência."""
    m = MetricasRNF()
    m.registrar(audio_s=1.0, wall_s=0.2, latencia_s=0.1, backlog=0)
    for chave, res in m.veredito().items():
        assert res.medido and res.alvo, f"{chave} sem medido/alvo"


# --- backpressure ---------------------------------------------------------
# Achado do soak de 2026-07-31: ao ficar para trás, o laço nunca recuperava — o atraso
# medido subiu de 392 ms para 18.798 ms e ficou lá. Num sistema de tempo real, áudio antigo
# vale menos que áudio novo: quando não dá para processar tudo, descarta-se o velho.

def test_sem_atraso_nada_e_descartado():
    from live_transcribe import aplicar_backpressure

    audio = list(range(16000))
    mantido, descartado = aplicar_backpressure(audio, atraso_s=0.0, teto_s=2.0)
    assert descartado == 0 and mantido == audio


def test_atraso_acima_do_teto_descarta_o_audio_MAIS_ANTIGO():
    """Mantém a cauda: numa ligação, o que o cliente acabou de dizer importa mais."""
    from live_transcribe import aplicar_backpressure

    audio = list(range(48000))          # 3 s
    mantido, descartado = aplicar_backpressure(audio, atraso_s=5.0, teto_s=2.0)
    assert descartado > 0
    assert mantido == audio[descartado:], "o descarte tem de ser do INÍCIO, não do fim"
    assert len(mantido) <= 2.0 * 16000


def test_backpressure_nunca_esvazia_tudo():
    """Negativo: descartar o lote inteiro mataria o áudio novo junto com o velho."""
    from live_transcribe import aplicar_backpressure

    mantido, _ = aplicar_backpressure(list(range(8000)), atraso_s=999.0, teto_s=2.0)
    assert len(mantido) > 0
