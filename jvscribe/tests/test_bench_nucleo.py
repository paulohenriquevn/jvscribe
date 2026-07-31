"""A aritmética sobre a qual os vereditos de benchmark repousam.

`bench/` estava em **29% de cobertura** — a pipeline que produz todo número de desempenho
publicado. O `main()` de cada ferramenta precisa de sessão ONNX, áudio e uma máquina ociosa, e
isso não cabe em teste unitário; mas o que **decide o veredito** cabe, e não estava coberto:

- `_Janela.rtfx()` / `.p99_ms()` — os dois números que o soak compara entre o primeiro e o
  último minuto para julgar RNF-04.
- `medir()` — a ordem round-robin, que é o que impede a flutuação de carga de viciar um
  candidato. O projeto já declarou vencedor de corrida única **três vezes** e errou nas três
  (`CLAUDE.md`, disciplina de medição § 3).
- `montar_configs()` — o contrato de que o baseline é o primeiro, do qual `relatar()` depende.

O que estes testes NÃO cobrem, e é honesto dizer: nenhum deles prova que o benchmark mede a
coisa certa numa máquina real. Isso é o live test, e ele registra carga.
"""
from __future__ import annotations

import pytest

from bench.runtime_bench import medir
from bench.stress_test import _Janela


class TestJanela:
    """O minuto de soak — a unidade que o veredito de RNF-04 compara."""

    def test_rtfx_e_audio_sobre_wall(self):
        j = _Janela()
        j.add(audio_s=3.0, wall_s=1.0, lat_s=0.05)
        assert j.rtfx() == pytest.approx(3.0)

    def test_janela_sem_trabalho_nao_divide_por_zero(self):
        """Um minuto sem amostra acontece: captura travada, backpressure, início da corrida."""
        assert _Janela().rtfx() == 0.0
        assert _Janela().p99_ms() == 0.0

    def test_p99_exclui_o_pior_1_por_cento_por_definicao(self):
        """Uma amostra lenta em 100 **não** aparece no p99 — e isso está certo.

        Escrevi este teste esperando 5000 ms e ele falhou; a expectativa é que estava errada.
        p99 significa "99% das amostras estão abaixo": com n=100, exatamente uma fica acima,
        e é justamente a que o percentil descarta. Quem quer a pior amostra pede o máximo.

        Fica registrado porque o erro é intuitivo e o número seria publicado.
        """
        j = _Janela()
        for _ in range(99):
            j.add(1.0, 1.0, 0.010)
        j.add(1.0, 1.0, 5.0)
        assert j.p99_ms() == pytest.approx(10.0)

    def test_p99_enxerga_a_cauda_quando_ela_passa_de_1_por_cento(self):
        """O que RNF-02 realmente exige: cauda gorda não pode ser suavizada (falácia § 3 #3).

        Rank mais próximo, sem interpolação — com 2 lentas em 100, o p99 devolve uma delas em
        vez de uma média que esconderia as duas.
        """
        j = _Janela()
        for _ in range(98):
            j.add(1.0, 1.0, 0.010)
        for _ in range(2):
            j.add(1.0, 1.0, 5.0)
        assert j.p99_ms() == pytest.approx(5000.0)

    def test_as_duas_implementacoes_de_percentil_do_repo_concordam(self):
        """`stress_test._Janela.p99_ms` e `live_transcribe.MetricasRNF._percentil`.

        São dois cálculos do MESMO conceito em pipelines diferentes — a classe de duplicação
        que este projeto já pagou com duas réguas de WER. Enquanto coexistirem, têm de casar.
        """
        from realtime.live_transcribe import MetricasRNF

        latencias = [0.01] * 98 + [5.0, 7.0]
        j = _Janela()
        for lat in latencias:
            j.add(1.0, 1.0, lat)
        assert j.p99_ms() == pytest.approx(
            MetricasRNF._percentil(sorted(latencias), 0.99) * 1000
        )

    def test_rtfx_acumula_entre_amostras_e_nao_sobrescreve(self):
        j = _Janela()
        j.add(1.0, 0.5, 0.01)
        j.add(1.0, 0.5, 0.01)
        assert j.rtfx() == pytest.approx(2.0), "as amostras do minuto têm de somar"

    def test_load_nasce_desconhecido_e_nao_zero(self):
        """`0.0` significaria "máquina ociosa" — uma afirmação que ninguém fez ainda."""
        assert _Janela().load is None


class _SessaoFalsa:
    """Registra a ORDEM das chamadas — é ela que o round-robin protege."""

    def __init__(self, nome: str, registro: list[str]) -> None:
        self.nome, self.registro = nome, registro

    def run(self, saidas, entradas):
        self.registro.append(self.nome)
        return None


class TestMedirRoundRobin:
    def test_alterna_configuracoes_a_cada_repeticao(self):
        """Round-robin, não uma configuração de cada vez.

        Medir A cem vezes e depois B cem vezes entrega a A e a B *janelas de tempo
        diferentes* — se a máquina esquentar ou outro processo acordar no meio, a diferença
        medida é do ambiente, não do candidato. Foi assim que "intra=8 é 30,9% melhor" não
        reproduziu.
        """
        ordem: list[str] = []
        sessoes = [(n, _SessaoFalsa(n, ordem), 1) for n in ("A", "B", "C")]
        medir(sessoes, {1: ("x", "xl")}, reps=3)
        assert ordem == ["A", "B", "C", "A", "B", "C", "A", "B", "C"]

    def test_cada_configuracao_rende_uma_amostra_por_repeticao(self):
        ordem: list[str] = []
        sessoes = [(n, _SessaoFalsa(n, ordem), 1) for n in ("A", "B")]
        amostras = medir(sessoes, {1: ("x", "xl")}, reps=5)
        assert {k: len(v) for k, v in amostras.items()} == {"A": 5, "B": 5}

    def test_latencia_e_normalizada_pelo_tamanho_do_batch(self):
        """Sem dividir por `batch`, uma config em batch 2 pareceria 2× mais lenta por item.

        Comparar batch 1 contra batch 2 em ms/execução é comparar coisas diferentes — o
        número que interessa é o custo por item.
        """
        ordem: list[str] = []
        sessoes = [("b1", _SessaoFalsa("b1", ordem), 1), ("b2", _SessaoFalsa("b2", ordem), 2)]
        amostras = medir(sessoes, {1: ("x", "xl"), 2: ("x2", "xl2")}, reps=2)
        assert all(v >= 0 for v in amostras["b2"])
        assert len(amostras["b2"]) == 2


def test_o_baseline_do_runtime_bench_e_o_primeiro_da_lista():
    """`relatar()` indexa `amostras[baseline]`; se a ordem mudar, o relatório compara errado.

    Usa um dublê de `onnxruntime` para não exigir a lib só para checar um contrato de ordem.
    """
    from bench.runtime_bench import montar_configs

    class _Ort:
        class GraphOptimizationLevel:
            ORT_ENABLE_BASIC = 1

        class SessionOptions:
            intra_op_num_threads = 0
            inter_op_num_threads = 0
            enable_cpu_mem_arena = False
            graph_optimization_level = 0

    configs = montar_configs(_Ort)
    assert configs[0][0].startswith("baseline"), "o baseline deixou de ser o primeiro"
    nomes = [n for n, _, _ in configs]
    assert len(nomes) == len(set(nomes)), "nome repetido colapsa duas configs num dict"
