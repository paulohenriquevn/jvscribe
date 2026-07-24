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
use macaw_audio::capture::{active_capture_threads, list_sources, spawn_capture, CaptureConfig};
use macaw_audio::features::{FeatureCache, StreamState};
use macaw_audio::metrics::BacklogCounter;
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
    let mut vad_mic = EnergyZcrVad::new(VadConfig::default());
    let mut vad_loop = EnergyZcrVad::new(VadConfig::default());
    let mut buf_mic: Vec<i16> = Vec::new();
    let mut buf_loop: Vec<i16> = Vec::new();

    let deadline = Instant::now() + Duration::from_secs(seconds);
    while Instant::now() < deadline {
        drain_into(&mic, &mut buf_mic, &backlog);
        if let Some(ref lp) = loopback {
            drain_into(lp, &mut buf_loop, &backlog);
        }

        let mic_state = classify_latest(&mut vad_mic, &mut buf_mic, &backlog);
        let loop_state = classify_latest(&mut vad_loop, &mut buf_loop, &backlog);
        let speaker = route_speaker(mic_state, loop_state);

        let (p50, p95, p99) = backlog.backlog_percentiles();
        println!("falante: {speaker:?} | backlog p50/p95/p99 = {p50}/{p95}/{p99}");

        std::thread::sleep(Duration::from_millis(500));
    }
    println!("encerrado. threads de captura vivas: {}", active_capture_threads());
    Ok(())
}

fn drain_into(rx: &Receiver<Vec<i16>>, buf: &mut Vec<i16>, backlog: &BacklogCounter) {
    while let Ok(chunk) = rx.try_recv() {
        backlog.record_produced(chunk.len() as u64);
        buf.extend_from_slice(&chunk);
    }
}

/// Classifica a janela mais recente e drena o buffer até menos de uma janela,
/// registrando cada amostra consumida no contador de backlog (RNF-03).
fn classify_latest(
    vad: &mut EnergyZcrVad,
    buf: &mut Vec<i16>,
    backlog: &BacklogCounter,
) -> SpeechState {
    let mut last = SpeechState::Silence;
    while buf.len() >= VAD_WINDOW {
        let window: Vec<i16> = buf.drain(..VAD_WINDOW).collect();
        backlog.record_consumed(window.len() as u64);
        if let Ok(state) = vad.process_window(&window) {
            last = state;
        }
    }
    last
}
