//! App web local para testar o walking skeleton de forma amigável (modo `serve`).
//!
//! Sobe um servidor HTTP mínimo (só `std::net` — sem dependência nova, per a
//! parsimony ladder) que serve um dashboard e um endpoint de métricas. O
//! navegador faz polling e mostra ao vivo: quem está falando (roteamento de
//! falante), backlog, deriva, threads vivas e saúde do sink.
//!
//! O pipeline de áudio roda em background e atualiza um snapshot compartilhado; o
//! servidor só lê esse snapshot e o serializa — nunca bloqueia a captura.

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use macaw_asr::AsrEngine;
use macaw_audio::capture::{
    active_capture_threads, check_sink_health, check_source_health, evaluate_sink_health,
    evaluate_source_health, list_sources, spawn_capture, CaptureConfig, Warning,
};
use macaw_audio::features::{FeatureCache, StreamState};
use macaw_audio::harness::{LatencyHistogram, RtfxMeter};
use macaw_audio::metrics::{BacklogCounter, DriftMeter};
use macaw_audio::vad::{route_speaker, EnergyZcrVad, SpeechDetector, Speaker, SpeechState, VadConfig};
use macaw_audio::{MEL_BINS, SAMPLE_RATE, VAD_WINDOW};

/// Estado corrente do pipeline, lido pelo servidor e escrito pela thread de áudio.
#[derive(Clone)]
struct Snapshot {
    running: bool,
    threads_alive: usize,
    /// "Você" | "Cliente" | "Ambos" | "Ninguém".
    speaker: &'static str,
    mic_active: bool,
    loop_active: bool,
    backlog_p50: u64,
    backlog_p95: u64,
    backlog_p99: u64,
    drift_ms: f64,
    sink_muted: bool,
    sink_note: String,
    mic_muted: bool,
    mic_note: String,
}

impl Snapshot {
    fn initial() -> Self {
        Self {
            running: false,
            threads_alive: 0,
            speaker: "Ninguém",
            mic_active: false,
            loop_active: false,
            backlog_p50: 0,
            backlog_p95: 0,
            backlog_p99: 0,
            drift_ms: 0.0,
            sink_muted: false,
            sink_note: String::new(),
            mic_muted: false,
            mic_note: String::new(),
        }
    }

    /// Serializa à mão (sem serde — evita dependência nova).
    fn to_json(&self) -> String {
        format!(
            "{{\"running\":{},\"threads_alive\":{},\"speaker\":\"{}\",\"mic_active\":{},\
             \"loop_active\":{},\"backlog_p50\":{},\"backlog_p95\":{},\"backlog_p99\":{},\
             \"drift_ms\":{:.1},\"sink_muted\":{},\"sink_note\":\"{}\",\
             \"mic_muted\":{},\"mic_note\":\"{}\"}}",
            self.running,
            self.threads_alive,
            self.speaker,
            self.mic_active,
            self.loop_active,
            self.backlog_p50,
            self.backlog_p95,
            self.backlog_p99,
            self.drift_ms,
            self.sink_muted,
            self.sink_note.replace('"', "'"),
            self.mic_muted,
            self.mic_note.replace('"', "'"),
        )
    }
}

fn speaker_label(s: Speaker) -> &'static str {
    match s {
        Speaker::Agent => "Você",
        Speaker::Customer => "Cliente",
        Speaker::Both => "Ambos",
        Speaker::Neither => "Ninguém",
    }
}

fn model_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../models/m0-borrowed")
}

fn fixture_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/tone_440hz_16k.wav")
}

/// Ponto de entrada do modo `serve`.
pub fn run(port: u16) -> Result<(), Box<dyn std::error::Error>> {
    let state = Arc::new(Mutex::new(Snapshot::initial()));
    let running = Arc::new(AtomicBool::new(true));
    // Garante que só UM `/fixture` roda por vez — cada um carrega o encoder de
    // 2,3 GB, e várias cargas concorrentes estourariam a memória.
    let fixture_busy = Arc::new(AtomicBool::new(false));
    // Encoder carregado sob demanda e cacheado: a primeira chamada de `/fixture`
    // paga os ~2 s de load; as seguintes reusam a sessão (~130 ms).
    let engine: Arc<Mutex<Option<AsrEngine>>> = Arc::new(Mutex::new(None));

    // Thread do pipeline de áudio: captura + VAD + roteamento + métricas.
    let pipe_state = Arc::clone(&state);
    let pipe_running = Arc::clone(&running);
    std::thread::spawn(move || pipeline_loop(&pipe_state, &pipe_running));

    let listener = TcpListener::bind(("127.0.0.1", port))?;
    println!("┌───────────────────────────────────────────────┐");
    println!("│  Macaw Voice — app de teste                    │");
    println!("│  Abra no navegador:  http://127.0.0.1:{port}      │");
    println!("│  Ctrl+C para encerrar                          │");
    println!("└───────────────────────────────────────────────┘");

    for stream in listener.incoming() {
        match stream {
            Ok(s) => {
                // Uma thread POR conexão: `/fixture` carrega o encoder (~2-3s) e
                // NÃO pode bloquear os polls de `/metrics`, senão a UI congela — foi
                // exatamente esse o bug do servidor single-threaded. Threads leves,
                // conexões curtas.
                let st = Arc::clone(&state);
                let fb = Arc::clone(&fixture_busy);
                let eng = Arc::clone(&engine);
                std::thread::spawn(move || {
                    if let Err(e) = handle(s, &st, &fb, &eng) {
                        eprintln!("aviso: conexão falhou: {e}");
                    }
                });
            }
            Err(e) => eprintln!("aviso: accept falhou: {e}"),
        }
    }
    running.store(false, Ordering::SeqCst);
    Ok(())
}

/// Laço do pipeline — atualiza o snapshot a cada ~300ms.
fn pipeline_loop(state: &Arc<Mutex<Snapshot>>, running: &Arc<AtomicBool>) {
    let mic = spawn_capture(CaptureConfig {
        source: "@DEFAULT_SOURCE@".to_string(),
        sample_rate: SAMPLE_RATE,
        channels: 1,
    })
    .ok();

    let monitor_name = list_sources()
        .ok()
        .and_then(|s| s.into_iter().find(|d| d.is_monitor).map(|d| d.name));

    // Saúde do sink cujo monitor capturamos (lado do cliente / loopback).
    let (sink_muted, sink_note) = match &monitor_name {
        Some(mon) => {
            let sink = mon.strip_suffix(".monitor").unwrap_or(mon);
            match check_sink_health(sink) {
                Ok(h) => {
                    let muted = matches!(evaluate_sink_health(&h), Some(Warning::SinkMuted));
                    let note = if muted {
                        format!("Sink '{sink}' mudo/volume 0 — o cliente não será captado")
                    } else {
                        format!("Sink '{sink}' ok (vol {}%)", h.volume_pct)
                    };
                    (muted, note)
                }
                Err(_) => (false, "não foi possível checar a saúde do sink".to_string()),
            }
        }
        None => (false, "nenhum monitor de sistema encontrado".to_string()),
    };

    // Saúde da source padrão (lado do atendente / microfone). Um mic mudo ou com
    // volume baixo demais capta silêncio e a voz do atendente não é transcrita,
    // sem erro visível — a falha que o próprio usuário viveu no teste.
    let (mic_muted, mic_note) = match check_source_health("@DEFAULT_SOURCE@") {
        Ok(h) => {
            let low = matches!(evaluate_source_health(&h), Some(Warning::SourceMuted));
            let note = if low {
                format!(
                    "Microfone mudo/volume baixo ({}%) — sua voz não será captada",
                    h.volume_pct
                )
            } else {
                format!("Microfone ok (vol {}%)", h.volume_pct)
            };
            (low, note)
        }
        Err(_) => (false, "não foi possível checar a saúde do microfone".to_string()),
    };

    let loopback = monitor_name.and_then(|name| {
        spawn_capture(CaptureConfig {
            source: name,
            sample_rate: SAMPLE_RATE,
            channels: 1,
        })
        .ok()
    });

    {
        let mut snap = state.lock().unwrap_or_else(|e| e.into_inner());
        snap.running = true;
        snap.sink_muted = sink_muted;
        snap.sink_note = sink_note;
        snap.mic_muted = mic_muted;
        snap.mic_note = mic_note;
    }

    let backlog = BacklogCounter::new();
    let drift = DriftMeter::new(SAMPLE_RATE);
    let mut vad_mic = EnergyZcrVad::new(VadConfig::default());
    let mut vad_loop = EnergyZcrVad::new(VadConfig::default());
    let mut buf_mic: Vec<i16> = Vec::new();
    let mut buf_loop: Vec<i16> = Vec::new();
    let mut mic_total = 0u64;
    let mut loop_total = 0u64;

    while running.load(Ordering::SeqCst) {
        let mic_state = mic
            .as_ref()
            .map(|rx| {
                mic_total += drain(rx, &mut buf_mic, &backlog);
                classify(&mut vad_mic, &mut buf_mic, &backlog)
            })
            .unwrap_or(SpeechState::Silence);
        let loop_state = loopback
            .as_ref()
            .map(|rx| {
                loop_total += drain(rx, &mut buf_loop, &backlog);
                classify(&mut vad_loop, &mut buf_loop, &backlog)
            })
            .unwrap_or(SpeechState::Silence);

        let speaker = route_speaker(mic_state, loop_state);
        let drift_ms = drift.record(mic_total, loop_total);
        let (p50, p95, p99) = backlog.backlog_percentiles();

        {
            let mut snap = state.lock().unwrap_or_else(|e| e.into_inner());
            snap.threads_alive = active_capture_threads();
            snap.speaker = speaker_label(speaker);
            snap.mic_active = mic_state == SpeechState::Speech;
            snap.loop_active = loop_state == SpeechState::Speech;
            snap.backlog_p50 = p50;
            snap.backlog_p95 = p95;
            snap.backlog_p99 = p99;
            snap.drift_ms = drift_ms;
        }

        std::thread::sleep(Duration::from_millis(300));
    }
}

fn drain(
    rx: &std::sync::mpsc::Receiver<Vec<i16>>,
    buf: &mut Vec<i16>,
    backlog: &BacklogCounter,
) -> u64 {
    let mut delivered = 0u64;
    while let Ok(chunk) = rx.try_recv() {
        backlog.record_produced(chunk.len() as u64);
        delivered += chunk.len() as u64;
        buf.extend_from_slice(&chunk);
    }
    delivered
}

fn classify(
    vad: &mut dyn SpeechDetector,
    buf: &mut Vec<i16>,
    backlog: &BacklogCounter,
) -> SpeechState {
    let mut last = SpeechState::Silence;
    let mut consumed = 0usize;
    while consumed + VAD_WINDOW <= buf.len() {
        if let Ok(state) = vad.process_window(&buf[consumed..consumed + VAD_WINDOW]) {
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

/// Trata uma requisição HTTP — roteia por caminho.
fn handle(
    mut stream: TcpStream,
    state: &Arc<Mutex<Snapshot>>,
    fixture_busy: &Arc<AtomicBool>,
    engine: &Arc<Mutex<Option<AsrEngine>>>,
) -> std::io::Result<()> {
    let mut buf = [0u8; 1024];
    let n = stream.read(&mut buf)?;
    let req = String::from_utf8_lossy(&buf[..n]);
    let path = req.split_whitespace().nth(1).unwrap_or("/");

    match path {
        "/" => respond(&mut stream, "200 OK", "text/html; charset=utf-8", DASHBOARD_HTML),
        "/metrics" => {
            let json = state.lock().unwrap_or_else(|e| e.into_inner()).to_json();
            respond(&mut stream, "200 OK", "application/json", &json)
        }
        "/fixture" => {
            // Single-flight: só um forward pass por vez (cada um usa o encoder de
            // 2,3 GB); dois em paralelo estourariam a memória e a UI.
            if fixture_busy.swap(true, Ordering::SeqCst) {
                let busy = "{\"ok\":false,\"msg\":\"Um teste já está rodando — aguarde.\"}";
                return respond(&mut stream, "200 OK", "application/json", busy);
            }
            let body = run_fixture_test(engine);
            fixture_busy.store(false, Ordering::SeqCst);
            respond(&mut stream, "200 OK", "application/json", &body)
        }
        "/m1" => {
            // Números já medidos de M1, lidos dos relatórios em disco (evidência real).
            respond(&mut stream, "200 OK", "application/json", &m1_measurements_json())
        }
        "/bench" => {
            // Benchmark rápido ao vivo (10 iterações, sem carga) — reusa o
            // single-flight do encoder de 2,3 GB.
            if fixture_busy.swap(true, Ordering::SeqCst) {
                let busy = "{\"ok\":false,\"msg\":\"Um teste já está rodando — aguarde.\"}";
                return respond(&mut stream, "200 OK", "application/json", busy);
            }
            let body = run_bench_test(engine);
            fixture_busy.store(false, Ordering::SeqCst);
            respond(&mut stream, "200 OK", "application/json", &body)
        }
        _ => respond(&mut stream, "404 Not Found", "text/plain", "não encontrado"),
    }
}

fn respond(
    stream: &mut TcpStream,
    status: &str,
    content_type: &str,
    body: &str,
) -> std::io::Result<()> {
    let response = format!(
        "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\n\
         Content-Length: {}\r\nAccess-Control-Allow-Origin: *\r\n\
         Connection: close\r\n\r\n{body}",
        body.len()
    );
    stream.write_all(response.as_bytes())
}

/// Roda o teste do encoder sobre a fixture e devolve o resultado como JSON.
///
/// O engine é cacheado no `Arc<Mutex<Option<_>>>` — a primeira chamada carrega, as
/// seguintes reusam.
fn run_fixture_test(engine_cache: &Arc<Mutex<Option<AsrEngine>>>) -> String {
    let (flat, n) = match fixture_flat_features() {
        Ok(v) => v,
        Err(e) => return e,
    };
    let mut guard = match load_engine(engine_cache) {
        Ok(g) => g,
        Err(e) => return e,
    };
    let engine = guard.as_mut().expect("engine acabou de ser carregado");
    let t = Instant::now();
    match engine.encode(&flat, MEL_BINS, n) {
        Ok(shape) => {
            let ms = t.elapsed().as_millis();
            let secs = n as f64 * VAD_WINDOW as f64 / SAMPLE_RATE as f64;
            format!(
                "{{\"ok\":true,\"msg\":\"Encoder 600M rodou sobre {secs:.1}s de áudio: \
                 saída [{}, {}, {}] em {ms} ms\"}}",
                shape.first().copied().unwrap_or(0),
                shape.get(1).copied().unwrap_or(0),
                shape.get(2).copied().unwrap_or(0),
            )
        }
        Err(e) => format!("{{\"ok\":false,\"msg\":\"forward pass: {e}\"}}"),
    }
}

/// Lê a fixture e extrai as features log-mel no layout do encoder. Ponto único
/// da extração para `/fixture` e `/bench` (DRY). Erro já vem como JSON pronto.
fn fixture_flat_features() -> Result<(Vec<f32>, usize), String> {
    let encoder = model_dir().join("encoder-model.onnx");
    if !encoder.exists() || !model_dir().join("encoder-model.onnx.data").exists() {
        return Err("{\"ok\":false,\"msg\":\"Modelo emprestado ausente. Rode scripts/setup_model.sh\"}"
            .to_string());
    }
    let reader = hound::WavReader::open(fixture_path())
        .map_err(|e| format!("{{\"ok\":false,\"msg\":\"fixture: {e}\"}}"))?;
    let samples: Vec<i16> = reader
        .into_samples()
        .collect::<Result<_, _>>()
        .map_err(|e| format!("{{\"ok\":false,\"msg\":\"leitura: {e}\"}}"))?;
    let cache = FeatureCache::new();
    let mut st = StreamState::new(&cache);
    let mut frames = Vec::new();
    let mut n = 0usize;
    for w in samples.chunks_exact(VAD_WINDOW) {
        let mel = st
            .extract(&cache, w)
            .map_err(|e| format!("{{\"ok\":false,\"msg\":\"features: {e}\"}}"))?;
        frames.extend_from_slice(mel);
        n += 1;
    }
    let mut flat = vec![0.0f32; MEL_BINS * n];
    for t in 0..n {
        for m in 0..MEL_BINS {
            flat[m * n + t] = frames[t * MEL_BINS + m];
        }
    }
    Ok((flat, n))
}

/// Carrega o encoder no cache (primeira vez) e devolve o guard travado.
fn load_engine(
    engine_cache: &Arc<Mutex<Option<AsrEngine>>>,
) -> Result<std::sync::MutexGuard<'_, Option<AsrEngine>>, String> {
    let encoder = model_dir().join("encoder-model.onnx");
    let mut guard = engine_cache.lock().unwrap_or_else(|e| e.into_inner());
    if guard.is_none() {
        match AsrEngine::load(&encoder) {
            Ok(e) => *guard = Some(e),
            Err(e) => return Err(format!("{{\"ok\":false,\"msg\":\"encoder: {e}\"}}")),
        }
    }
    Ok(guard)
}

/// Benchmark rápido ao vivo — 10 iterações (2 de warmup) do encoder sobre a
/// fixture, reportando RTFx e latência p50/p95/p99 via o harness de M1. É o mesmo
/// mecanismo de `scripts/bench.sh`, numa janela curta e sem carga (seguro para a
/// UI). O soak completo RNF-04/05 continua sendo o `bench.sh 3000 --load`.
fn run_bench_test(engine_cache: &Arc<Mutex<Option<AsrEngine>>>) -> String {
    let (flat, n) = match fixture_flat_features() {
        Ok(v) => v,
        Err(e) => return e,
    };
    let audio_secs = n as f64 * VAD_WINDOW as f64 / SAMPLE_RATE as f64;
    let mut guard = match load_engine(engine_cache) {
        Ok(g) => g,
        Err(e) => return e,
    };
    let engine = guard.as_mut().expect("engine carregado");

    let total_iters = 10usize;
    let warmup = 2usize;
    let mut times = Vec::with_capacity(total_iters);
    let mut latency = LatencyHistogram::new();
    for _ in 0..total_iters {
        let t = Instant::now();
        if let Err(e) = engine.encode(&flat, MEL_BINS, n) {
            return format!("{{\"ok\":false,\"msg\":\"forward pass: {e}\"}}");
        }
        let dt = t.elapsed();
        times.push(dt);
        latency.record(dt);
    }
    let rtfx = match RtfxMeter::new(warmup).rtfx(audio_secs, &times) {
        Ok(r) => r,
        Err(e) => return format!("{{\"ok\":false,\"msg\":\"harness: {e}\"}}"),
    };
    let (p50, p95, p99) = latency
        .percentiles()
        .map(|(a, b, c)| (a as f64 / 1000.0, b as f64 / 1000.0, c as f64 / 1000.0))
        .unwrap_or((0.0, 0.0, 0.0));
    format!(
        "{{\"ok\":true,\"rtfx\":{rtfx:.1},\"p50\":{p50:.0},\"p95\":{p95:.0},\"p99\":{p99:.0},\
         \"msg\":\"RTFx {rtfx:.1}× · p99 {p99:.0} ms (janela curta, {total_iters} iterações, sem carga)\"}}"
    )
}

/// Lê os relatórios de medição de M1 do disco e os devolve como JSON (evidência
/// real, não hardcoded). Se um arquivo faltar, devolve string vazia para ele.
fn m1_measurements_json() -> String {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../knowledge-base/measurements");
    let read = |name: &str| std::fs::read_to_string(root.join(name)).unwrap_or_default();
    let baseline = json_escape(&read("m1-baseline-report.md"));
    let harness = json_escape(&read("m1-harness-measurement.md"));
    format!("{{\"baseline\":\"{baseline}\",\"harness\":\"{harness}\"}}")
}

/// Escapa uma string para inserção segura num literal JSON.
fn json_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 16);
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => {}
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

/// Dashboard — HTML/CSS/JS embutido, self-contained (sem CDN, sem assets externos).
const DASHBOARD_HTML: &str = include_str!("dashboard.html");
