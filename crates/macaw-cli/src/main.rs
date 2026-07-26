//! Walking skeleton de M0: captura dois streams (mic + loopback), aplica VAD por
//! stream, rotula o falante por roteamento, extrai log-mel e roda o forward pass
//! do encoder — provando o encanamento de ponta a ponta.
//!
//! Este é o **caller de produção** do wiring triad (`.claude/rules/cycle-implement.md`):
//! exercita `macaw-audio` (captura, VAD, roteamento, features) e `macaw-asr`
//! (encoder) juntos, com observabilidade (backlog, threads vivas).
//!
//! Dois modos:
//! - `macaw-cli fixture` — roda o pipeline sobre a fixture versionada (offline,
//!   determinístico, não precisa de servidor de áudio). É o que a validação de
//!   integração e o CI usam.
//! - `macaw-cli live` — captura mic + loopback do sistema em tempo real e imprime
//!   rótulo de falante + backlog enquanto roda. Precisa de servidor de áudio.

use macaw_cli::app;
use macaw_cli::transcribe::transcribe_wav;

use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::mpsc::Receiver;
use std::time::{Duration, Instant};

use macaw_asr::AsrEngine;
use macaw_audio::capture::{
    active_capture_threads, check_sink_health, evaluate_sink_health, list_sources, spawn_capture,
    CaptureConfig, Warning,
};
use macaw_audio::features::{FeatureCache, StreamState};
use macaw_audio::harness::{LatencyHistogram, RtfxMeter, ThermalRatio};
use macaw_audio::metrics::{BacklogCounter, DriftMeter};
use macaw_audio::vad::{route_speaker, EnergyZcrVad, SpeechDetector, SpeechState, VadConfig};
use macaw_audio::{MEL_BINS, SAMPLE_RATE, VAD_WINDOW};

fn model_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../models/m0-borrowed")
}

fn fixture_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/tone_440hz_16k.wav")
}

/// Diretório do export do modelo icefall de produção (`model.int8.onnx` + `tokens.txt`).
fn onnx_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../training/results/onnx")
}

/// Modo `transcribe <wav>`: caller de produção do runtime v0 (pilar a do wiring triad).
/// Roda `wav → macaw_audio::kaldi_fbank → AsrEngine::transcribe` e imprime o texto + a
/// métrica de runtime (pilar c: RTFx/tokens/duração — observabilidade em produção).
fn run_transcribe(wav: &str) -> Result<(), Box<dyn std::error::Error>> {
    let (text, m) = transcribe_wav(&onnx_dir(), std::path::Path::new(wav))?;
    println!("{text}");
    // Pilar (c) — métrica observável: sem isto, o decode é invisível quando quebra.
    eprintln!(
        "[macaw-cli transcribe] T={} audio={:.2}s decode={:.0}ms RTFx={:.1}× tokens={}",
        m.n_frames, m.audio_secs, m.decode_ms, m.rtfx, m.tokens
    );
    Ok(())
}

fn main() -> ExitCode {
    let mode = std::env::args().nth(1).unwrap_or_else(|| "fixture".to_string());
    let result = match mode.as_str() {
        "fixture" => run_fixture(),
        "bench" => run_bench(),
        "live" => run_live(),
        "transcribe" => match std::env::args().nth(2) {
            Some(wav) => run_transcribe(&wav),
            None => {
                eprintln!("uso: macaw-cli transcribe <arquivo.wav>");
                return ExitCode::from(2);
            }
        },
        "serve" => {
            let port = std::env::args()
                .nth(2)
                .and_then(|s| s.parse().ok())
                .unwrap_or(7070);
            app::run(port)
        }
        other => {
            eprintln!(
                "modo desconhecido: {other:?} (use 'fixture', 'bench', 'live', 'transcribe' ou 'serve')"
            );
            return ExitCode::from(2);
        }
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("erro: {e}");
            ExitCode::FAILURE
        }
    }
}

/// Modo offline determinístico: pipeline completo sobre a fixture.
fn run_fixture() -> Result<(), Box<dyn std::error::Error>> {
    println!("macaw-cli fixture — walking skeleton (M0)");

    let reader = hound::WavReader::open(fixture_path())?;
    let samples: Vec<i16> = reader.into_samples::<i16>().collect::<Result<_, _>>()?;
    println!(
        "fixture: {} amostras ({:.2}s a {} Hz)",
        samples.len(),
        samples.len() as f32 / SAMPLE_RATE as f32,
        SAMPLE_RATE
    );

    // VAD (estatística informativa deste modo) por janela.
    let mut vad = EnergyZcrVad::new(VadConfig::default());
    let mut speech_windows = 0usize;
    let mut n_windows = 0usize;
    for window in samples.chunks_exact(VAD_WINDOW) {
        if vad.process_window(window)? == SpeechState::Speech {
            speech_windows += 1;
        }
        n_windows += 1;
    }
    println!("VAD: {speech_windows}/{n_windows} janelas com fala");

    // Features log-mel no layout do encoder — mesma reordenação que o modo bench
    // (helper compartilhado, sem duplicar a lógica).
    let (flat, n_frames) = mel_features_from_samples(&samples)?;

    // Forward pass do encoder, se o modelo emprestado estiver presente.
    let encoder = model_dir().join("encoder-model.onnx");
    if encoder.exists() && model_dir().join("encoder-model.onnx.data").exists() {
        let mut engine = AsrEngine::load(&encoder)?;
        let t = Instant::now();
        let shape = engine.encode(&flat, MEL_BINS, n_frames)?;
        let dt = t.elapsed();
        let audio_secs = n_frames as f64 * VAD_WINDOW as f64 / SAMPLE_RATE as f64;
        // `[MEDIDO — encanamento apenas]`: RTF do encoder de 600M nesta CPU. NÃO é
        // número de produto (modelo emprestado, offline) — é a evidência que
        // motiva o modelo próprio de M5/M6.
        println!(
            "encoder 600M: saída {shape:?} em {:.0}ms para {audio_secs:.2}s de áudio \
             (RTF {:.2} — [MEDIDO — encanamento apenas])",
            dt.as_millis(),
            dt.as_secs_f64() / audio_secs
        );
    } else {
        println!("encoder ausente — rode scripts/setup_model.sh para o forward pass");
    }

    println!("pipeline completo: captura → VAD → features → encoder ✓");
    Ok(())
}

/// Extrai as features log-mel de `samples` no layout do encoder `[mel * n_frames]`.
///
/// Ponto único da reordenação `[frame][mel] → [mel*n_frames]` — usado por
/// `run_fixture` (modo fixture) e por `extract_fixture_features` (modo bench),
/// para não duplicar a lógica (DRY, review F3).
fn mel_features_from_samples(samples: &[i16]) -> Result<(Vec<f32>, usize), Box<dyn std::error::Error>> {
    let cache = FeatureCache::new();
    let mut state = StreamState::new(&cache);
    let mut frames: Vec<f32> = Vec::new();
    let mut n_frames = 0usize;
    for window in samples.chunks_exact(VAD_WINDOW) {
        let mel = state.extract(&cache, window)?;
        frames.extend_from_slice(mel);
        n_frames += 1;
    }
    let mut flat = vec![0.0f32; MEL_BINS * n_frames];
    for t in 0..n_frames {
        for m in 0..MEL_BINS {
            flat[m * n_frames + t] = frames[t * MEL_BINS + m];
        }
    }
    Ok((flat, n_frames))
}

/// Lê a fixture e extrai as features (caminho do modo bench).
fn extract_fixture_features() -> Result<(Vec<f32>, usize), Box<dyn std::error::Error>> {
    let reader = hound::WavReader::open(fixture_path())?;
    let samples: Vec<i16> = reader.into_samples::<i16>().collect::<Result<_, _>>()?;
    mel_features_from_samples(&samples)
}

/// Modo `bench` — harness de medição de M1 (T1.3). Roda o encoder emprestado em
/// laço, descarta warmup e reporta RTFx sustentado, latência p50/p95/p99 e a
/// razão térmica (RTFx da 2ª metade ÷ 1ª metade do soak — proxy de min30/min1).
///
/// Uso: `macaw-cli bench [iterações]` (default 30). Para a medição sob os RNFs
/// completos (P-cores + carga concorrente), use `scripts/bench.sh`, que prende o
/// processo aos P-cores com `taskset` (RNF-05/06).
///
/// Este é o **caller de produção** do harness (wiring triad): exercita
/// `RtfxMeter`/`LatencyHistogram`/`ThermalRatio` de `macaw-audio` sobre o
/// `AsrEngine` real de `macaw-asr`.
fn run_bench() -> Result<(), Box<dyn std::error::Error>> {
    println!("macaw-cli bench — harness de medição (M1)");
    let total_iters: usize = std::env::args()
        .nth(2)
        .and_then(|s| s.parse().ok())
        .unwrap_or(30);
    let warmup_iters = (total_iters / 5).max(1); // 20% de warmup, mínimo 1.

    let encoder = model_dir().join("encoder-model.onnx");
    if !(encoder.exists() && model_dir().join("encoder-model.onnx.data").exists()) {
        println!("encoder ausente — rode scripts/setup_model.sh para o bench");
        return Ok(());
    }

    let (flat, n_frames) = extract_fixture_features()?;
    let audio_secs = n_frames as f64 * VAD_WINDOW as f64 / SAMPLE_RATE as f64;
    let mut engine = AsrEngine::load(&encoder)?;

    println!(
        "medindo {total_iters} iterações ({warmup_iters} de warmup) sobre {audio_secs:.2}s de áudio…"
    );

    // Coleta o tempo de parede por iteração (cronometragem real com Instant).
    let mut iter_times = Vec::with_capacity(total_iters);
    let mut latency = LatencyHistogram::new();
    for _ in 0..total_iters {
        let t = Instant::now();
        let _ = engine.encode(&flat, MEL_BINS, n_frames)?;
        let dt = t.elapsed();
        iter_times.push(dt);
        latency.record(dt);
    }

    // RTFx sustentado (descarta warmup) — terminologia RTFx = áudio/parede.
    let meter = RtfxMeter::new(warmup_iters);
    let rtfx = meter.rtfx(audio_secs, &iter_times)?;

    // Razão térmica: RTFx da 2ª metade ÷ 1ª metade das iterações medidas (proxy
    // curto de min30/min1; o soak de 10 min real é `scripts/bench.sh`).
    let measured = &iter_times[warmup_iters..];
    let half = measured.len() / 2;
    let thermal = if half > 0 {
        let first = meter_rtfx_window(audio_secs, &measured[..half]);
        let second = meter_rtfx_window(audio_secs, &measured[half..]);
        match ThermalRatio::ratio(first, second) {
            Ok(r) => format!("{r:.2}"),
            Err(_) => "[DESCONHECIDO]".to_string(),
        }
    } else {
        "[DESCONHECIDO — iterações insuficientes]".to_string()
    };

    let (p50, p95, p99) = latency
        .percentiles()
        .map(|(a, b, c)| {
            (
                a as f64 / 1000.0,
                b as f64 / 1000.0,
                c as f64 / 1000.0,
            )
        })
        .unwrap_or((0.0, 0.0, 0.0));

    // Números rotulados [MEDIDO — encanamento apenas]: são do encoder emprestado
    // de 600M, NÃO números de produto (o modelo próprio vem em M5/M6).
    println!("--- relatório do harness [MEDIDO — encanamento apenas] ---");
    println!("RTFx sustentado (áudio/parede): {rtfx:.2}× (alvo RNF-07 ≥ 6×)");
    println!("latência p50/p95/p99: {p50:.1}/{p95:.1}/{p99:.1} ms (alvo RNF-02 p99 ≤ 500 ms)");
    println!("razão térmica (2ª½ ÷ 1ª½): {thermal} (alvo RNF-04 ≥ 0,80 no soak de 10 min)");
    println!(
        "backlog: harness offline não gera backlog (RNF-03 medido no modo live com captura real)"
    );
    Ok(())
}

/// RTFx de uma janela de tempos (sem warmup) — helper local do bench para a
/// razão térmica. Usa `RtfxMeter` com warmup 0 sobre a janela já sem warmup.
fn meter_rtfx_window(audio_secs: f64, times: &[std::time::Duration]) -> f64 {
    RtfxMeter::new(0).rtfx(audio_secs, times).unwrap_or(0.0)
}

/// Modo ao vivo: captura mic + loopback e imprime rótulo de falante + backlog.
fn run_live() -> Result<(), Box<dyn std::error::Error>> {
    println!("macaw-cli live — captura dual");
    let seconds: u64 = std::env::args()
        .nth(2)
        .and_then(|s| s.parse().ok())
        .unwrap_or(10);

    let mic = spawn_capture(CaptureConfig {
        source: "@DEFAULT_SOURCE@".to_string(),
        sample_rate: SAMPLE_RATE,
        channels: 1,
    })?;
    // Loopback: a primeira source `.monitor` disponível (o `@DEFAULT_SINK@.monitor`
    // literal não é resolvido pelo servidor como `@DEFAULT_SOURCE@` é — `[MEDIDO]`
    // no smoke test do CLI). Opcional: se não houver monitor, só o mic roda.
    let monitor_name = list_sources()
        .ok()
        .and_then(|s| s.into_iter().find(|d| d.is_monitor).map(|d| d.name));

    // T2.3 — saúde do sink ANTES de capturar o loopback: se o sink estiver mudo, o
    // monitor captura silêncio legítimo e o cliente deixa de ser transcrito SEM
    // erro. Isso tem que ser visível (`error-handling.md` § 1). Deriva o nome do
    // sink do monitor (`<sink>.monitor` → `<sink>`).
    if let Some(ref mon) = monitor_name {
        let sink = mon.strip_suffix(".monitor").unwrap_or(mon);
        match check_sink_health(sink) {
            Ok(health) => {
                if let Some(Warning::SinkMuted) = evaluate_sink_health(&health) {
                    eprintln!(
                        "AVISO SinkMuted: sink '{sink}' está mudo/volume 0 (muted={}, vol={}%) \
                         — o loopback NÃO vai capturar o áudio do cliente",
                        health.muted, health.volume_pct
                    );
                }
            }
            Err(e) => eprintln!("aviso: não foi possível checar a saúde do sink '{sink}': {e}"),
        }
    }

    let loopback = monitor_name.and_then(|name| {
        spawn_capture(CaptureConfig {
            source: name,
            sample_rate: SAMPLE_RATE,
            channels: 1,
        })
        .ok()
    });

    println!("threads de captura vivas: {}", active_capture_threads());

    let backlog = BacklogCounter::new();
    let drift = DriftMeter::new(SAMPLE_RATE);
    let mut vad_mic = EnergyZcrVad::new(VadConfig::default());
    let mut vad_loop = EnergyZcrVad::new(VadConfig::default());
    let mut buf_mic: Vec<i16> = Vec::new();
    let mut buf_loop: Vec<i16> = Vec::new();
    // Total de amostras já entregues por cada stream — alimenta o DriftMeter (T5.2).
    let mut mic_total = 0u64;
    let mut loop_total = 0u64;

    let deadline = Instant::now() + Duration::from_secs(seconds);
    while Instant::now() < deadline {
        mic_total += drain_into(&mic, &mut buf_mic, &backlog);
        if let Some(ref lp) = loopback {
            loop_total += drain_into(lp, &mut buf_loop, &backlog);
        }

        let mic_state = classify_latest(&mut vad_mic, &mut buf_mic, &backlog);
        let loop_state = classify_latest(&mut vad_loop, &mut buf_loop, &backlog);
        let speaker = route_speaker(mic_state, loop_state);

        // T5.2 — deriva entre os dois streams via a API testada (não reimplementada).
        let drift_ms = drift.record(mic_total, loop_total);

        let (p50, p95, p99) = backlog.backlog_percentiles();
        println!(
            "falante: {speaker:?} | backlog p50/p95/p99 = {p50}/{p95}/{p99} | drift = {drift_ms:.1}ms"
        );

        std::thread::sleep(Duration::from_millis(500));
    }
    println!("encerrado. threads de captura vivas: {}", active_capture_threads());
    Ok(())
}

/// Drena o canal para o buffer e retorna quantas amostras foram entregues (para o
/// DriftMeter). Cada amostra é contabilizada como produzida no backlog.
fn drain_into(rx: &Receiver<Vec<i16>>, buf: &mut Vec<i16>, backlog: &BacklogCounter) -> u64 {
    let mut delivered = 0u64;
    while let Ok(chunk) = rx.try_recv() {
        backlog.record_produced(chunk.len() as u64);
        delivered += chunk.len() as u64;
        buf.extend_from_slice(&chunk);
    }
    delivered
}

/// Classifica as janelas completas do buffer e as remove, registrando o consumo no
/// contador de backlog (RNF-03).
///
/// Recebe `&mut dyn SpeechDetector` — não o `EnergyZcrVad` concreto — para que a
/// troca por Silero em M1 seja só uma segunda implementação do traço, sem tocar
/// nesta assinatura (OCP, `vad.rs` doc do traço). Realiza no composition root a
/// abstração que o traço promete.
///
/// Sem alocação por janela: classifica um slice de `buf` e só então remove o
/// prefixo consumido de uma vez (`drain(..consumed)`), em vez de `collect`ar cada
/// janela num `Vec` novo.
fn classify_latest(
    vad: &mut dyn SpeechDetector,
    buf: &mut Vec<i16>,
    backlog: &BacklogCounter,
) -> SpeechState {
    let mut last = SpeechState::Silence;
    let mut consumed = 0usize;
    while consumed + VAD_WINDOW <= buf.len() {
        let window = &buf[consumed..consumed + VAD_WINDOW];
        if let Ok(state) = vad.process_window(window) {
            last = state;
        }
        consumed += VAD_WINDOW;
    }
    if consumed > 0 {
        backlog.record_consumed(consumed as u64);
        buf.drain(..consumed);
    }
    last
}
