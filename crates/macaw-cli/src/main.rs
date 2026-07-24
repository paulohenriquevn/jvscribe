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

use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::mpsc::Receiver;
use std::time::{Duration, Instant};

use macaw_asr::AsrEngine;
use macaw_audio::capture::{
    active_capture_threads, check_sink_health, evaluate_health, list_sources, spawn_capture,
    CaptureConfig, Warning,
};
use macaw_audio::features::{FeatureCache, StreamState};
use macaw_audio::metrics::{BacklogCounter, DriftMeter};
use macaw_audio::vad::{route_speaker, EnergyZcrVad, SpeechDetector, SpeechState, VadConfig};
use macaw_audio::{MEL_BINS, SAMPLE_RATE, VAD_WINDOW};

fn model_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../models/m0-borrowed")
}

fn fixture_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/tone_440hz_16k.wav")
}

fn main() -> ExitCode {
    let mode = std::env::args().nth(1).unwrap_or_else(|| "fixture".to_string());
    let result = match mode.as_str() {
        "fixture" => run_fixture(),
        "live" => run_live(),
        other => {
            eprintln!("modo desconhecido: {other:?} (use 'fixture' ou 'live')");
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

    // VAD + features por janela.
    let mut vad = EnergyZcrVad::new(VadConfig::default());
    let cache = FeatureCache::new();
    let mut state = StreamState::new(&cache);
    let mut frames: Vec<f32> = Vec::new();
    let mut n_frames = 0usize;
    let mut speech_windows = 0usize;

    for window in samples.chunks_exact(VAD_WINDOW) {
        if vad.process_window(window)? == SpeechState::Speech {
            speech_windows += 1;
        }
        let mel = state.extract(&cache, window)?;
        frames.extend_from_slice(mel);
        n_frames += 1;
    }
    println!("VAD: {speech_windows}/{n_frames} janelas com fala");

    // Reordena de [frame][mel] (acumulado) para [mel * n_frames] (layout do encoder).
    let mut flat = vec![0.0f32; MEL_BINS * n_frames];
    for t in 0..n_frames {
        for m in 0..MEL_BINS {
            flat[m * n_frames + t] = frames[t * MEL_BINS + m];
        }
    }

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
                if let Some(Warning::SinkMuted) = evaluate_health(&health) {
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
