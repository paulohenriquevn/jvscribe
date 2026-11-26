"""Escolha de CPUs e de contagem de threads a partir da topologia real.

Motivo `[MEDIDO]` 2026-07-31, i7 híbrido (2 P-cores a 5,0 GHz + 8 E-cores a 3,7 GHz):

| configuração        | mediana | IPC  | instruções |
|---------------------|---------|------|------------|
| P-cores, intra=2    | 70,2 ms | 1,87 |     30,9 G |
| todos, intra=6      | 94,0 ms | 1,22 |     90,9 G |

Fixar nos P-cores é **25% mais rápido usando 3× menos threads**. O cache miss é idêntico nos
dois (~26%), então não é memória: 6 threads executam **3× mais instruções para o mesmo
trabalho** — spin-wait em barreira. Numa CPU híbrida cada barreira espera o E-core, que é 26%
mais lento em clock e mais estreito.

Sobra de CPU também é requisito: RNF-05 exige medir com softphone ativo. Ocupar 2 dos 12
lógicos em vez de 6 é o que torna isso viável.
"""
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

# alias: `cpu` colide com a variável de laço de `_sysfs`, e o rename cego
# `cpu_topology`→`cpu` criou o sombreamento. O módulo entra com nome próprio.
import cpu as cpu_mod  # noqa: E402
from cpu import Topologia, detectar  # noqa: E402


def _sysfs(tmp_path: Path, freqs: dict[int, int]) -> Path:
    """Monta um /sys/devices/system/cpu falso com as frequências dadas (kHz)."""
    for cpu, khz in freqs.items():
        d = tmp_path / f"cpu{cpu}" / "cpufreq"
        d.mkdir(parents=True)
        (d / "cpuinfo_max_freq").write_text(f"{khz}\n")
    return tmp_path


# --- CPU híbrida: o caso que motivou tudo --------------------------------

def test_cpu_hibrida_escolhe_apenas_os_nucleos_rapidos(tmp_path):
    """2 P-cores com HT (4 lógicos a 5,0 GHz) + 8 E-cores a 3,7 GHz."""
    base = _sysfs(tmp_path, {**{c: 5_000_000 for c in range(4)},
                             **{c: 3_700_000 for c in range(4, 12)}})
    t = detectar(base)
    assert t.hibrida
    assert t.cpus_rapidas == [0, 1, 2, 3]
    assert t.total == 12


def test_em_cpu_hibrida_as_threads_ficam_abaixo_dos_logicos_rapidos(tmp_path):
    """Medido: intra=2 bateu intra=4 nos mesmos 4 lógicos — hyperthread não soma em matmul.

    Dois lógicos do mesmo núcleo físico disputam as mesmas unidades de execução SIMD; o
    segundo thread adiciona sincronização sem adicionar vazão.
    """
    base = _sysfs(tmp_path, {**{c: 5_000_000 for c in range(4)},
                             **{c: 3_700_000 for c in range(4, 12)}})
    t = detectar(base)
    assert t.threads_recomendadas == 2, (
        f"esperava 2 (metade dos 4 lógicos rápidos), veio {t.threads_recomendadas}"
    )


# --- CPU homogênea: não pode virar caso especial da híbrida --------------

def test_cpu_homogenea_nao_e_marcada_como_hibrida(tmp_path):
    base = _sysfs(tmp_path, {c: 3_600_000 for c in range(8)})
    t = detectar(base)
    assert not t.hibrida
    assert t.cpus_rapidas == list(range(8))


def test_cpu_homogenea_recomenda_metade_dos_logicos(tmp_path):
    """Sem núcleo lento para esperar, o limite passa a ser contenção de banda e HT."""
    base = _sysfs(tmp_path, {c: 3_600_000 for c in range(8)})
    assert detectar(base).threads_recomendadas == 4


def test_diferenca_pequena_de_clock_nao_conta_como_hibrida(tmp_path):
    """Negativo: boost por núcleo faz frequências diferirem em poucos %. Isso NÃO é híbrida.

    Sem esta tolerância, uma CPU homogênea com boost seria fatiada e ficaríamos com 1 thread.
    """
    base = _sysfs(tmp_path, {0: 4_000_000, 1: 4_100_000, 2: 3_950_000, 3: 4_000_000})
    t = detectar(base)
    assert not t.hibrida
    assert len(t.cpus_rapidas) == 4


# --- degradação: sysfs ausente ou ilegível -------------------------------

def test_sem_sysfs_degrada_para_contagem_de_cpus_sem_quebrar(tmp_path):
    """Negativo: container, macOS ou kernel sem cpufreq. Não pode levantar."""
    t = detectar(tmp_path / "nao-existe")
    assert t.total >= 1
    assert t.threads_recomendadas >= 1
    assert not t.hibrida


def test_arquivo_de_frequencia_ilegivel_e_ignorado_sem_derrubar(tmp_path):
    base = _sysfs(tmp_path, {0: 5_000_000, 1: 5_000_000})
    ruim = base / "cpu2" / "cpufreq"
    ruim.mkdir(parents=True)
    (ruim / "cpuinfo_max_freq").write_text("não é número\n")
    t = detectar(base)
    assert t.cpus_rapidas == [0, 1]


def test_nunca_recomenda_zero_threads(tmp_path):
    """Negativo: uma única CPU não pode virar `intra_op_num_threads=0`."""
    base = _sysfs(tmp_path, {0: 2_000_000})
    assert detectar(base).threads_recomendadas >= 1


# --- a string de afinidade -----------------------------------------------

def test_lista_de_afinidade_em_formato_de_taskset(tmp_path):
    base = _sysfs(tmp_path, {**{c: 5_000_000 for c in range(4)},
                             **{c: 3_700_000 for c in range(4, 12)}})
    assert detectar(base).afinidade_taskset() == "0-3"


def test_afinidade_de_cpus_nao_contiguas(tmp_path):
    """Alguns kernels enumeram P e E intercalados."""
    base = _sysfs(tmp_path, {0: 5_000_000, 1: 3_700_000, 2: 5_000_000, 3: 3_700_000})
    assert detectar(base).afinidade_taskset() == "0,2"


def test_topologia_e_serializavel_para_o_relatorio(tmp_path):
    """A condição de medição tem de caber no relatório — senão o número fica sem contexto."""
    base = _sysfs(tmp_path, {**{c: 5_000_000 for c in range(4)},
                             **{c: 3_700_000 for c in range(4, 12)}})
    d = detectar(base).como_dict()
    for chave in ("total", "hibrida", "cpus_rapidas", "threads_recomendadas", "mhz_max"):
        assert chave in d, f"falta {chave} no dict de condição"


def test_dataclass_aceita_construcao_direta_para_override_manual():
    """O operador tem de poder forçar uma topologia sem mexer no sysfs."""
    t = Topologia(total=4, cpus_rapidas=[0, 1], hibrida=True, mhz_max=5000)
    assert t.threads_recomendadas == 1 and t.afinidade_taskset() == "0-1"


# --- por que NÃO fixamos afinidade -----------------------------------------

def test_o_modulo_nao_expoe_nada_que_mude_a_afinidade_do_processo():
    """Fixar o processo nos P-cores foi tentado, MEDIDO e revertido.

    Isolado, `taskset -c 0-3` + `intra=2` dava 70,2 ms contra 94,0 ms — 25% melhor. No
    sistema real com dois canais deu o OPOSTO: RTFx caiu de 4,60× para 2,33×.

    Causa: `sched_setaffinity` **é herdado pelos processos filhos**. Os `parec` da captura
    passavam a disputar os mesmos 2 P-cores físicos com a inferência, matando a captura de
    fome. Verificado: filho de um processo fixado em [0,1,2,3] nasce em [0,1,2,3].

    E no soak determinístico (sem subprocessos) a afinidade era **neutra**: 6,49× fixado
    contra 6,88× livre. Ganho zero, modo de falha real → o módulo é observacional.

    O ganho verdadeiro estava na CONTAGEM de threads, não na afinidade: intra=2 dá RTFx 6,88×
    contra 4,95× de intra=6 e 3,94× de intra=12.
    """
    proibidos = [n for n in dir(cpu_mod)
                 if any(x in n.lower() for x in ("afinidade", "affinity", "pin", "setaffinity"))
                 and callable(getattr(cpu_mod, n, None))]
    assert not proibidos, (
        f"{proibidos} mutam afinidade de processo — medido como prejudicial (vaza para os "
        "subprocessos de captura). O módulo deve só OBSERVAR a topologia."
    )


def test_a_recomendacao_deixa_cpu_livre_para_os_outros_componentes():
    """O runtime não é só a inferência: há captura, features e um segundo canal.

    Uma recomendação que ocupe tudo estrangula o resto — e o RNF-05 ainda exige softphone
    rodando junto.
    """
    t = Topologia(total=12, cpus_rapidas=[0, 1, 2, 3], hibrida=True, mhz_max=5000)
    assert t.threads_recomendadas <= t.total // 4, (
        f"{t.threads_recomendadas} de {t.total} lógicos não deixa folga para captura, "
        "segundo canal e carga concorrente"
    )
