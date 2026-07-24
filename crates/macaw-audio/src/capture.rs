//! Captura dual via PulseAudio — uma thread bloqueante por stream (ADR D2 do
//! plano `knowledge-base/plans/m0-walking-skeleton-plan.md`).
//!
//! A API `Simple` de `libpulse-simple-binding` permite especificar a source
//! **por stream**, o que nem `cpal` nem `PULSE_SOURCE` permitem no mesmo
//! processo — `[MEDIDO]` em
//! `knowledge-base/discoveries/m0-capture-probe-evidence.md` experimento 6.
//!
//! Este módulo é o único ponto do crate que fala com o servidor de áudio
//! (adapter de infraestrutura, per `.claude/rules/architecture.md` § 1) — o
//! resto de `macaw-audio` é domínio DSP puro.

use std::cell::RefCell;
use std::rc::Rc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc::{self, Receiver};
use std::thread;

use libpulse_binding as pulse;
use libpulse_simple_binding::Simple;
use pulse::callbacks::ListResult;
use pulse::context::{Context, FlagSet as ContextFlagSet, State as ContextState};
use pulse::error::PAErr;
use pulse::mainloop::standard::{IterateResult, Mainloop};
use pulse::sample::{Format, Spec};
use pulse::stream::Direction;
use pulse::volume::Volume;

/// Nome de aplicação reportado ao servidor PulseAudio em toda conexão.
const APP_NAME: &str = "macaw-voice";

/// Número de threads de captura vivas neste processo.
///
/// Incrementado quando uma thread de captura inicia e decrementado quando ela
/// encerra (por `Receiver` dropado ou stream derrubado pelo servidor). É
/// observabilidade de produção — permite detectar vazamento de thread quando
/// capturas são recriadas — e o sinal determinístico com que os testes provam o
/// encerramento limpo, sem depender de `/proc/self/status`, que é global do
/// processo e ruidoso sob carga.
static ACTIVE_CAPTURE_THREADS: AtomicUsize = AtomicUsize::new(0);

/// Quantas threads de captura estão vivas agora.
#[must_use]
pub fn active_capture_threads() -> usize {
    ACTIVE_CAPTURE_THREADS.load(Ordering::Acquire)
}

/// Ordinal de `PA_ERR_NOENTITY` em `pa_error_code_t`.
///
/// `[MEDIDO]` — comando: binário de sonda com `Simple::new(..., Some("fonte-que-
/// nao-existe-xyz"), ...)`, PulseAudio 15.99.1 local, 2026-07-24. O erro
/// devolvido por `pa_simple_new` é o **ordinal positivo** do enum
/// `pa_error_code_t` (`PAErr(5)`), não o valor negativo usado pelas operações
/// assíncronas de `Context` (essas seguem a convenção documentada em
/// `pulse::error::Code`/`TryFrom<PAErr>`, que aqui NÃO se aplica). Repetido 3×
/// consecutivas com o mesmo resultado.
const PA_ERR_NO_ENTITY: i32 = 5;

/// Configuração de uma captura de um único stream de áudio.
#[derive(Debug, Clone)]
pub struct CaptureConfig {
    /// Nome da source PulseAudio (ex.: `alsa_input...` ou `....monitor`).
    pub source: String,
    /// Taxa de amostragem, em Hz.
    pub sample_rate: u32,
    /// Número de canais.
    pub channels: u8,
}

/// Erros tipados de captura.
///
/// Nunca panic na fronteira FFI (`.claude/rules/error-handling.md` § 2; risco
/// R4 do plano) — todo modo de falha do servidor de áudio vira uma variante
/// explícita.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CaptureError {
    /// A source informada não existe no servidor de áudio.
    SourceNotFound {
        /// Nome da source que foi solicitada.
        source: String,
    },
    /// A conexão com o servidor de áudio falhou (servidor indisponível,
    /// recusado, encerrado antes de ficar pronto, etc).
    ConnectionFailed {
        /// Rótulo do que estava sendo feito quando a conexão falhou.
        context: String,
        /// Motivo relatado pelo servidor de áudio.
        reason: String,
    },
    /// A leitura de amostras falhou depois de a conexão já estar estabelecida.
    ReadFailed {
        /// Source de onde a leitura falhou.
        source: String,
        /// Motivo relatado pelo servidor de áudio.
        reason: String,
    },
}

impl std::fmt::Display for CaptureError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::SourceNotFound { source } => {
                write!(f, "source de áudio não encontrada: \"{source}\"")
            }
            Self::ConnectionFailed { context, reason } => {
                write!(
                    f,
                    "conexão com o servidor de áudio falhou ({context}): {reason}"
                )
            }
            Self::ReadFailed { source, reason } => {
                write!(f, "leitura de amostras falhou para \"{source}\": {reason}")
            }
        }
    }
}

impl std::error::Error for CaptureError {}

/// Converte o erro de `Simple::new` num `CaptureError` tipado.
fn map_simple_new_error(source: &str, err: PAErr) -> CaptureError {
    let reason = err
        .to_string()
        .unwrap_or_else(|| format!("código PulseAudio {}", err.0));
    if err.0 == PA_ERR_NO_ENTITY {
        CaptureError::SourceNotFound {
            source: source.to_string(),
        }
    } else {
        CaptureError::ConnectionFailed {
            context: source.to_string(),
            reason,
        }
    }
}

/// Inicia a captura de um stream em thread dedicada.
///
/// A conexão com o servidor de áudio é estabelecida **antes** de a thread ser
/// disparada — assim `SourceNotFound`/`ConnectionFailed` retornam de forma
/// síncrona para o chamador, e a thread só existe quando a captura já está
/// garantidamente ativa.
///
/// O buffer usado para ler da FFI (`byte_buf`) é alocado **uma única vez**,
/// antes do laço, e reutilizado em toda iteração — nunca cresce nem realoca
/// (T1.1 DoD). Cada chunk lido é convertido para um novo `Vec<i16>` para ser
/// enviado por `mpsc`: essa é a única alocação por chunk, inerente à
/// transferência de posse pelo canal (mesmo desenho produtor/consumidor citado
/// como prior art em `sherpa-onnx/.../streaming_zipformer_microphone.rs`), não
/// uma realocação do buffer de leitura.
pub fn spawn_capture(cfg: CaptureConfig) -> Result<Receiver<Vec<i16>>, CaptureError> {
    let spec = Spec {
        format: Format::S16NE,
        channels: cfg.channels,
        rate: cfg.sample_rate,
    };
    if !spec.is_valid() {
        return Err(CaptureError::ConnectionFailed {
            context: cfg.source.clone(),
            reason: format!(
                "sample spec inválida (channels={}, rate={})",
                cfg.channels, cfg.sample_rate
            ),
        });
    }

    let chunk_frames = crate::VAD_WINDOW;
    let chunk_bytes = chunk_frames * cfg.channels.max(1) as usize * 2;

    // `[MEDIDO]` 2026-07-24: sem `BufferAttr` explícito, `Simple::new` usa o
    // default do servidor para `fragsize`, que a própria doc de
    // `libpulse-binding` avisa que "will default to something like 2s" — e
    // foi exatamente isso que a sonda mediu neste ambiente: leituras
    // bloqueando até ~1,5-2s antes da primeira rajada de dados. Fixar
    // `fragsize` no tamanho do chunk que já usamos (`chunk_bytes`, alinhado a
    // `VAD_WINDOW`) derrubou o pior caso medido para ~45ms — necessário para
    // que a thread de captura note o fechamento do canal (Receiver dropado)
    // em tempo hábil (T1.1 DoD: "encerra em < 500ms").
    let attr = pulse::def::BufferAttr {
        maxlength: u32::MAX,
        tlength: u32::MAX,
        prebuf: u32::MAX,
        minreq: u32::MAX,
        fragsize: chunk_bytes as u32,
    };

    let simple = Simple::new(
        None,
        APP_NAME,
        Direction::Record,
        Some(&cfg.source),
        "macaw-capture",
        &spec,
        None,
        Some(&attr),
    )
    .map_err(|err| map_simple_new_error(&cfg.source, err))?;

    let (tx, rx) = mpsc::channel::<Vec<i16>>();

    // Guarda RAII: incrementa o contador de threads vivas ao ser criada e
    // decrementa ao ser dropada — inclusive se a thread encerrar por qualquer
    // caminho (erro de leitura, canal fechado, unwind). Move para dentro da
    // thread para que o decremento aconteça exatamente quando a thread morre.
    struct LiveGuard;
    impl LiveGuard {
        fn new() -> Self {
            ACTIVE_CAPTURE_THREADS.fetch_add(1, Ordering::AcqRel);
            LiveGuard
        }
    }
    impl Drop for LiveGuard {
        fn drop(&mut self) {
            ACTIVE_CAPTURE_THREADS.fetch_sub(1, Ordering::AcqRel);
        }
    }

    thread::spawn(move || {
        let _live = LiveGuard::new();
        // Alocado uma vez, fora do laço — reutilizado em toda iteração.
        let mut byte_buf = vec![0u8; chunk_bytes];

        loop {
            if simple.read(&mut byte_buf).is_err() {
                // Servidor encerrou/derrubou o stream: encerra a thread limpo.
                // O canal fechado (Sender dropado) é o sinal para o consumidor
                // — nunca um panic (error-handling.md § 2).
                break;
            }

            let samples: Vec<i16> = byte_buf
                .chunks_exact(2)
                .map(|b| i16::from_ne_bytes([b[0], b[1]]))
                .collect();

            if tx.send(samples).is_err() {
                // Receiver dropado pelo consumidor: encerra a thread limpo.
                break;
            }
        }
    });

    Ok(rx)
}

/// Descreve uma source de áudio disponível no servidor.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceDescriptor {
    /// Nome da source.
    pub name: String,
    /// `true` quando o nome termina em `.monitor` — source que espelha a
    /// saída de um sink (loopback), conforme convenção do PulseAudio.
    pub is_monitor: bool,
}

/// Enumera as sources de áudio disponíveis no servidor local.
pub fn list_sources() -> Result<Vec<SourceDescriptor>, CaptureError> {
    let (mut mainloop, context) = connect_ready_context("list_sources")?;

    let sources: Rc<RefCell<Vec<SourceDescriptor>>> = Rc::new(RefCell::new(Vec::new()));
    let done = Rc::new(RefCell::new(false));
    let failed = Rc::new(RefCell::new(false));

    {
        let sources_cb = Rc::clone(&sources);
        let done_cb = Rc::clone(&done);
        let failed_cb = Rc::clone(&failed);
        let _op = context
            .introspect()
            .get_source_info_list(move |result| match result {
                ListResult::Item(info) => {
                    let name = info.name.as_deref().unwrap_or_default().to_string();
                    let is_monitor = name.ends_with(".monitor");
                    sources_cb
                        .borrow_mut()
                        .push(SourceDescriptor { name, is_monitor });
                }
                ListResult::End => *done_cb.borrow_mut() = true,
                ListResult::Error => {
                    *failed_cb.borrow_mut() = true;
                    *done_cb.borrow_mut() = true;
                }
            });

        drive_mainloop_until(&mut mainloop, &done, "list_sources")?;
    }

    if *failed.borrow() {
        return Err(CaptureError::ConnectionFailed {
            context: "list_sources".to_string(),
            reason: "servidor de áudio retornou erro ao listar sources".to_string(),
        });
    }

    let collected = sources.borrow().clone();
    Ok(collected)
}

/// Estado de saúde de um dispositivo de áudio — mute e volume. Serve tanto para
/// um sink (saída/loopback) quanto para uma source (microfone): os dois têm a
/// mesma forma (mudo + volume).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DeviceHealth {
    /// `true` quando o dispositivo está mudo.
    pub muted: bool,
    /// Volume médio, em porcentagem (100 == `Volume::NORMAL`).
    pub volume_pct: u8,
}

/// Piso de volume abaixo do qual um microfone é considerado baixo demais para
/// captar fala de forma utilizável. `[MEDIDO]` 2026-07-24: uma fala normal num
/// mic com volume muito baixo mediu RMS ≈ 0,0002 (silêncio efetivo). Heurística
/// de M0 — não há dado de campo para calibrar com precisão ainda.
const MIN_USABLE_SOURCE_VOLUME_PCT: u8 = 20;

/// Avisos derivados do estado de saúde de captura.
///
/// Existem porque um dispositivo mudo/baixo faz a captura render silêncio
/// legítimo — o falante deixa de ser transcrito **sem nenhum erro visível**.
/// Falha silenciosa é o pior modo de falha aqui (`m0-capture-probe-evidence.md`
/// § Experimento 2; `.claude/rules/error-handling.md` § 1).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Warning {
    /// O sink de saída está mudo ou com volume zero — o loopback não vai
    /// capturar o áudio do cliente.
    SinkMuted,
    /// A source de entrada (microfone) está muda ou com volume baixo demais — a
    /// voz do atendente não será captada.
    SourceMuted,
}

/// Consulta o estado de mute/volume de um sink pelo nome.
pub fn check_sink_health(sink_name: &str) -> Result<DeviceHealth, CaptureError> {
    let (mut mainloop, context) = connect_ready_context(sink_name)?;

    let result: Rc<RefCell<Option<DeviceHealth>>> = Rc::new(RefCell::new(None));
    let done = Rc::new(RefCell::new(false));

    {
        let result_cb = Rc::clone(&result);
        let done_cb = Rc::clone(&done);
        let _op = context
            .introspect()
            .get_sink_info_by_name(sink_name, move |item| match item {
                ListResult::Item(info) => {
                    let pct = (info.volume.avg().0 as f64 / Volume::NORMAL.0 as f64 * 100.0)
                        .round()
                        .clamp(0.0, 255.0) as u8;
                    *result_cb.borrow_mut() = Some(DeviceHealth {
                        muted: info.mute,
                        volume_pct: pct,
                    });
                }
                ListResult::End | ListResult::Error => *done_cb.borrow_mut() = true,
            });

        drive_mainloop_until(&mut mainloop, &done, sink_name)?;
    }

    let outcome = *result.borrow();
    match outcome {
        Some(health) => Ok(health),
        None => Err(CaptureError::ConnectionFailed {
            context: sink_name.to_string(),
            reason: "sink não encontrado no servidor de áudio".to_string(),
        }),
    }
}

/// Consulta o estado de mute/volume de uma source (microfone) pelo nome.
///
/// Espelha [`check_sink_health`], mas para o lado da entrada. `@DEFAULT_SOURCE@`
/// é aceito para a source padrão.
pub fn check_source_health(source_name: &str) -> Result<DeviceHealth, CaptureError> {
    let (mut mainloop, context) = connect_ready_context(source_name)?;

    let result: Rc<RefCell<Option<DeviceHealth>>> = Rc::new(RefCell::new(None));
    let done = Rc::new(RefCell::new(false));

    {
        let result_cb = Rc::clone(&result);
        let done_cb = Rc::clone(&done);
        let _op = context
            .introspect()
            .get_source_info_by_name(source_name, move |item| match item {
                ListResult::Item(info) => {
                    let pct = (info.volume.avg().0 as f64 / Volume::NORMAL.0 as f64 * 100.0)
                        .round()
                        .clamp(0.0, 255.0) as u8;
                    *result_cb.borrow_mut() = Some(DeviceHealth {
                        muted: info.mute,
                        volume_pct: pct,
                    });
                }
                ListResult::End | ListResult::Error => *done_cb.borrow_mut() = true,
            });

        drive_mainloop_until(&mut mainloop, &done, source_name)?;
    }

    let outcome = *result.borrow();
    match outcome {
        Some(health) => Ok(health),
        None => Err(CaptureError::ConnectionFailed {
            context: source_name.to_string(),
            reason: "source não encontrada no servidor de áudio".to_string(),
        }),
    }
}

/// Deriva um aviso da saúde de um **sink**.
///
/// Mudo OU volume zero → `Warning::SinkMuted`: o efeito prático (loopback
/// capturando silêncio) é o mesmo nos dois casos.
pub fn evaluate_sink_health(health: &DeviceHealth) -> Option<Warning> {
    if health.muted || health.volume_pct == 0 {
        Some(Warning::SinkMuted)
    } else {
        None
    }
}

/// Deriva um aviso da saúde de uma **source** (microfone).
///
/// Mudo OU volume abaixo de [`MIN_USABLE_SOURCE_VOLUME_PCT`] →
/// `Warning::SourceMuted`. Diferente do sink, um mic com volume baixo mas
/// não-zero ainda produz silêncio efetivo (foi o caso que motivou esta checagem),
/// por isso o piso é um percentual, não apenas zero.
pub fn evaluate_source_health(health: &DeviceHealth) -> Option<Warning> {
    if health.muted || health.volume_pct < MIN_USABLE_SOURCE_VOLUME_PCT {
        Some(Warning::SourceMuted)
    } else {
        None
    }
}

/// Conecta ao servidor de áudio local e bloqueia até o contexto ficar pronto
/// para executar operações de introspecção.
fn connect_ready_context(op_label: &str) -> Result<(Mainloop, Context), CaptureError> {
    let mut mainloop = Mainloop::new().ok_or_else(|| CaptureError::ConnectionFailed {
        context: op_label.to_string(),
        reason: "falha ao criar mainloop do PulseAudio".to_string(),
    })?;

    let mut context =
        Context::new(&mainloop, APP_NAME).ok_or_else(|| CaptureError::ConnectionFailed {
            context: op_label.to_string(),
            reason: "falha ao criar contexto do PulseAudio".to_string(),
        })?;

    context
        .connect(None, ContextFlagSet::NOFLAGS, None)
        .map_err(|err| CaptureError::ConnectionFailed {
            context: op_label.to_string(),
            reason: err
                .to_string()
                .unwrap_or_else(|| "conexão recusada pelo servidor de áudio".to_string()),
        })?;

    loop {
        match mainloop.iterate(true) {
            IterateResult::Quit(_) | IterateResult::Err(_) => {
                return Err(CaptureError::ConnectionFailed {
                    context: op_label.to_string(),
                    reason: "iteração do mainloop falhou durante a conexão".to_string(),
                });
            }
            IterateResult::Success(_) => {}
        }
        match context.get_state() {
            ContextState::Ready => break,
            ContextState::Failed | ContextState::Terminated => {
                return Err(CaptureError::ConnectionFailed {
                    context: op_label.to_string(),
                    reason: "servidor de áudio encerrou a conexão antes de ficar pronto"
                        .to_string(),
                });
            }
            _ => {}
        }
    }

    Ok((mainloop, context))
}

/// Roda o mainloop até a flag `done` ser sinalizada por um callback.
fn drive_mainloop_until(
    mainloop: &mut Mainloop,
    done: &Rc<RefCell<bool>>,
    op_label: &str,
) -> Result<(), CaptureError> {
    while !*done.borrow() {
        match mainloop.iterate(true) {
            IterateResult::Quit(_) | IterateResult::Err(_) => {
                return Err(CaptureError::ConnectionFailed {
                    context: op_label.to_string(),
                    reason: "iteração do mainloop falhou".to_string(),
                });
            }
            IterateResult::Success(_) => {}
        }
    }
    Ok(())
}
