//! Testes de integração de `capture.rs` — T1.1 (captura dual) e T2.3
//! (detecção de sink mudo).
//!
//! Rodam contra o servidor PulseAudio real do ambiente: não há mock. A
//! premissa do M0 é justamente que a captura funciona no notebook de
//! referência (`knowledge-base/discoveries/m0-capture-probe-evidence.md`).
//!
//! Testes que dependem de servidor de áudio (ou de ferramentas externas como
//! `pactl`/`paplay`/`sox` para simular um sink) degradam graciosamente — via
//! `eprintln!` + retorno antecipado — quando o ambiente não tem o que é
//! necessário, em vez de falhar por um motivo alheio ao código sob teste.

use std::process::{Child, Command};
use std::sync::mpsc::Receiver;
use std::sync::{Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};

use macaw_audio::capture::{
    active_capture_threads, check_sink_health, evaluate_health, list_sources, spawn_capture,
    CaptureConfig, CaptureError, SinkHealth, Warning,
};

/// Serializa os testes que tocam o servidor de áudio real.
///
/// Necessário porque (a) eles disputam o mesmo servidor PulseAudio e (b)
/// `thread_count()` lê `/proc/self/status`, que é **global do processo** — sob a
/// execução paralela padrão do cargo, threads de captura de um teste poluiriam a
/// contagem de outro. `[MEDIDO]`: sem esta serialização,
/// `test_capture_thread_terminates_cleanly_on_drop` falhava de forma intermitente;
/// com ela, passa de forma determinística.
static AUDIO_TEST_LOCK: Mutex<()> = Mutex::new(());

/// Adquire o lock de serialização, tolerando um lock envenenado por um teste que
/// já falhou (não queremos mascarar a falha original com um panic de poison).
fn serialize() -> MutexGuard<'static, ()> {
    AUDIO_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner())
}

// ---------------------------------------------------------------------
// Helpers de ambiente
// ---------------------------------------------------------------------

fn tool_available(name: &str) -> bool {
    Command::new("which")
        .arg(name)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Encontra uma source real (não `.monitor`) no servidor local — evita fixar
/// os testes a um nome de hardware específico deste notebook.
fn any_real_source_name() -> Option<String> {
    list_sources()
        .ok()?
        .into_iter()
        .find(|s| !s.is_monitor)
        .map(|s| s.name)
}

fn load_null_sink(sink_name: &str) -> String {
    let output = Command::new("pactl")
        .args([
            "load-module",
            "module-null-sink",
            &format!("sink_name={sink_name}"),
            "rate=16000",
            "channels=1",
            "format=s16le",
        ])
        .output()
        .expect("pactl load-module deve executar (pré-checado por tool_available)");
    assert!(
        output.status.success(),
        "falha ao carregar null-sink de teste: {output:?}"
    );
    String::from_utf8_lossy(&output.stdout).trim().to_string()
}

fn set_sink_mute(sink_name: &str, mute: bool) {
    let flag = if mute { "1" } else { "0" };
    let status = Command::new("pactl")
        .args(["set-sink-mute", sink_name, flag])
        .status()
        .expect("pactl set-sink-mute deve executar");
    assert!(status.success(), "falha ao mutar sink de teste");
}

fn unload_module(module_id: &str) {
    let _ = Command::new("pactl")
        .args(["unload-module", module_id])
        .status();
}

/// Sink nulo + reprodução contínua de um tom, com limpeza automática via
/// `Drop` (mesmo em caso de `assert!` falhar no meio do teste).
struct NullSinkGuard {
    module_id: String,
    sink_name: String,
    player: Child,
}

impl NullSinkGuard {
    fn start(sink_name: &str, tone_path: &std::path::Path) -> Self {
        let module_id = load_null_sink(sink_name);
        let player = Command::new("paplay")
            .args([
                "--device",
                sink_name,
                tone_path
                    .to_str()
                    .expect("caminho temporário deve ser utf-8"),
            ])
            .spawn()
            .expect("paplay deve executar (pré-checado por tool_available)");
        Self {
            module_id,
            sink_name: sink_name.to_string(),
            player,
        }
    }

    fn monitor_name(&self) -> String {
        format!("{}.monitor", self.sink_name)
    }
}

impl Drop for NullSinkGuard {
    fn drop(&mut self) {
        let _ = self.player.kill();
        let _ = self.player.wait();
        unload_module(&self.module_id);
    }
}

fn generate_tone(path: &std::path::Path, duration_secs: u32) {
    let status = Command::new("sox")
        .args([
            "-n",
            "-r",
            "16000",
            "-c",
            "1",
            "-b",
            "16",
            path.to_str().expect("caminho temporário deve ser utf-8"),
            "synth",
            &duration_secs.to_string(),
            "sine",
            "440",
            "vol",
            "0.5",
        ])
        .status()
        .expect("sox deve executar (já é dependência de scripts/make_fixtures.sh)");
    assert!(status.success(), "sox falhou ao gerar tom de teste");
}

fn drain_total(rx: &Receiver<Vec<i16>>) -> usize {
    let mut total = 0;
    while let Ok(chunk) = rx.try_recv() {
        total += chunk.len();
    }
    total
}


// ---------------------------------------------------------------------
// T1.1 — comportamento sequencial
// ---------------------------------------------------------------------

#[test]
fn test_capture_fails_with_typed_error_when_source_does_not_exist() {
    let cfg = CaptureConfig {
        source: "fonte-que-nao-existe-xyz".to_string(),
        sample_rate: 16_000,
        channels: 1,
    };

    let result = spawn_capture(cfg);

    match result {
        Err(CaptureError::SourceNotFound { source }) => {
            assert_eq!(source, "fonte-que-nao-existe-xyz");
            let message = CaptureError::SourceNotFound { source }.to_string();
            assert!(
                message.contains("fonte-que-nao-existe-xyz"),
                "mensagem deveria citar o nome da source, obteve: {message}"
            );
        }
        other => panic!("esperava Err(CaptureError::SourceNotFound), obteve {other:?}"),
    }
}

#[test]
fn test_list_sources_identifies_monitor_sources() {
    let sources = match list_sources() {
        Ok(sources) => sources,
        Err(err) => {
            eprintln!("SKIP: servidor de áudio indisponível neste ambiente ({err}) — list_sources não pode ser exercitado");
            return;
        }
    };

    assert!(
        !sources.is_empty(),
        "esperava ao menos uma source no servidor de áudio local"
    );

    for source in &sources {
        if source.name.ends_with(".monitor") {
            assert!(
                source.is_monitor,
                "source \"{}\" termina em .monitor mas is_monitor é false",
                source.name
            );
        }
    }
}

// ---------------------------------------------------------------------
// T1.1 — concorrência
// ---------------------------------------------------------------------

/// `[MEDIDO]` 2026-07-24, PulseAudio 15.99.1 local, ambiente sandboxed sem
/// hardware de áudio físico dedicado: com um null-sink de formato casado
/// (16 kHz mono s16le, sem resample), a primeira rajada de amostras do
/// monitor demora ~0.9-2s para chegar após a conexão, e o próprio caminho de
/// mic mostrou lacunas de bloqueio de até ~1.5s em `Simple::read()`. Medir
/// numa janela curta de 2s (como descrito literalmente no plano) captura
/// majoritariamente esse transiente de arranque — a diferença de contagem
/// chegou a 20% nesse regime. Uma janela de 8s após 2.5s de aquecimento
/// reduziu a diferença medida para ~2%. A tolerância de 10% do plano
/// (Acceptance Criteria de T1.1) é preservada — o que muda é apenas quanto
/// tempo se espera estabilizar antes de medir, uma adaptação exigida pela
/// evidência (`.claude/rules/asr-evidence-discipline.md` § 3, falácia 4:
/// benchmark curto mente).
/// Prova o DoD de T1.1: os dois streams capturam simultaneamente **e** avançam à
/// mesma taxa em regime.
///
/// Metodologia (corrigida — ver `knowledge-base/discoveries/m0-drift-evidence.md`):
/// a diferença de contagem **total desde o spawn** conflacionaria o offset de
/// partida do monitor (medido em ~1,44 s, constante) com a paridade de taxa. O
/// experimento provou que a diferença absoluta **não cresce** com o tempo — logo o
/// drift em regime é ≈ 0. Este teste mede a propriedade física relevante: após um
/// warmup que absorve o offset de partida, quantas amostras cada stream entrega
/// **durante uma janela de parede fixa**.
#[test]
fn test_two_captures_run_simultaneously_without_interference() {
    let _lock = serialize();

    if !(tool_available("pactl") && tool_available("paplay") && tool_available("sox")) {
        eprintln!("SKIP: pactl/paplay/sox indisponíveis — captura dupla concorrente não pode ser exercitada neste ambiente");
        return;
    }

    let mic_source = match any_real_source_name() {
        Some(name) => name,
        None => {
            eprintln!("SKIP: nenhuma source de mic encontrada no servidor de áudio local");
            return;
        }
    };

    let tmp_dir = std::env::temp_dir();
    let tone_path = tmp_dir.join(format!("macaw_test_tone_{}.wav", std::process::id()));
    generate_tone(&tone_path, 16);

    let sink_name = format!("macaw_test_dualcap_sink_{}", std::process::id());
    let guard = NullSinkGuard::start(&sink_name, &tone_path);

    thread::sleep(Duration::from_millis(2500));

    let rx_mic = spawn_capture(CaptureConfig {
        source: mic_source,
        sample_rate: 16_000,
        channels: 1,
    })
    .expect("captura do mic deve iniciar");

    let rx_mon = spawn_capture(CaptureConfig {
        source: guard.monitor_name(),
        sample_rate: 16_000,
        channels: 1,
    })
    .expect("captura do monitor (null-sink de teste) deve iniciar");

    // Warmup: deixa ambos fluírem e descarta o acumulado, absorvendo o offset de
    // partida do monitor (~1,44 s medido). Depois disso, os dois estão em regime.
    thread::sleep(Duration::from_secs(3));
    let _ = drain_total(&rx_mic);
    let _ = drain_total(&rx_mon);

    // Janela de medição de parede fixa: conta amostras entregues DURANTE a janela.
    let window = Duration::from_secs(6);
    thread::sleep(window);
    let mic_window = drain_total(&rx_mic);
    let mon_window = drain_total(&rx_mon);

    drop(guard);
    let _ = std::fs::remove_file(&tone_path);

    // DoD: ambos entregam amostras simultaneamente.
    assert!(mic_window > 0, "captura de mic não entregou amostras na janela");
    assert!(mon_window > 0, "captura de monitor não entregou amostras na janela");

    // Paridade de taxa em regime: a evidência mostra drift ≈ 0. Uma tolerância de
    // 5% cobre jitter de agendamento da janela de parede sem esconder drift real
    // (que apareceria como diferença crescente, não como um offset fixo).
    let diff_pct = (mic_window as f64 - mon_window as f64).abs()
        / mic_window.max(mon_window) as f64
        * 100.0;
    assert!(
        diff_pct < 5.0,
        "taxa em regime diverge: mic {mic_window} vs monitor {mon_window} na janela de 6s = {diff_pct:.1}% (esperado < 5%)"
    );
}

/// Prova o DoD de T1.1: a thread de captura encerra limpo (< 500 ms) quando o
/// `Receiver` é dropado — sem vazar.
///
/// Usa `active_capture_threads()`, o contador de liveness próprio do módulo, e não
/// `/proc/self/status`. O contador é determinístico e independente de carga; o
/// `/proc` conta as threads internas do libpulse e é ruidoso sob a execução
/// paralela da suíte completa — `[MEDIDO]`: o proxy de `/proc` falhava sob carga,
/// o contador próprio não.
#[test]
fn test_capture_thread_terminates_cleanly_on_drop() {
    let _lock = serialize();

    let mic_source = match any_real_source_name() {
        Some(name) => name,
        None => {
            eprintln!("SKIP: nenhuma source de mic encontrada no servidor de áudio local");
            return;
        }
    };

    let baseline = active_capture_threads();

    let rx = match spawn_capture(CaptureConfig {
        source: mic_source,
        sample_rate: 16_000,
        channels: 1,
    }) {
        Ok(rx) => rx,
        Err(err) => {
            eprintln!("SKIP: captura não pôde iniciar neste ambiente ({err})");
            return;
        }
    };

    // A thread pode levar alguns ms para agendar e incrementar o contador.
    let up_deadline = Instant::now() + Duration::from_millis(500);
    while active_capture_threads() <= baseline && Instant::now() < up_deadline {
        thread::sleep(Duration::from_millis(5));
    }
    assert_eq!(
        active_capture_threads(),
        baseline + 1,
        "esperava exatamente uma thread de captura viva após spawn_capture"
    );

    drop(rx);

    // O encerramento só acontece na PRÓXIMA leitura após o canal fechar. Com o
    // `fragsize` fixado (~32ms), isso é bem inferior aos 500ms do DoD.
    let deadline = Instant::now() + Duration::from_millis(500);
    let mut terminated = false;
    while Instant::now() < deadline {
        if active_capture_threads() == baseline {
            terminated = true;
            break;
        }
        thread::sleep(Duration::from_millis(10));
    }

    assert!(
        terminated,
        "thread de captura não encerrou em < 500ms após drop do Receiver (contador ainda em {})",
        active_capture_threads()
    );
}

// ---------------------------------------------------------------------
// T2.3 — detecção de sink mudo
// ---------------------------------------------------------------------

#[test]
fn test_sink_health_reports_muted_state() {
    if !tool_available("pactl") {
        eprintln!("SKIP: pactl indisponível — check_sink_health não pode ser exercitado");
        return;
    }

    let sink_name = format!("macaw_test_health_sink_{}", std::process::id());
    let module_id = load_null_sink(&sink_name);
    set_sink_mute(&sink_name, true);

    let health = check_sink_health(&sink_name);

    unload_module(&module_id);

    let health = health.expect("check_sink_health deve funcionar contra o sink de teste");
    assert!(
        health.muted,
        "sink com mute ativo deveria reportar muted == true"
    );
}

#[test]
fn test_warning_emitted_when_sink_is_silent() {
    let health = SinkHealth {
        muted: true,
        volume_pct: 0,
    };

    assert_eq!(evaluate_health(&health), Some(Warning::SinkMuted));
}
