//! VAD por stream (T2.1) e roteamento de falante por energia/ZCR (T2.2).
//!
//! O Silero ONNX — o VAD "real" citado no blueprint (§ Coverage Corner 4) —
//! ainda não foi baixado neste M0. Por `.claude/rules/asr-evidence-discipline.md`
//! § 0, trabalho **independente** de arquitetura (captura, VAD, roteamento) está
//! liberado antes do ADR de M2; o modelo de VAD em si não é essa decisão — é
//! encanamento substituível por construção.
//!
//! [`EnergyZcrVad`] é a implementação de M0: uma heurística de energia RMS +
//! taxa de cruzamento de zero (ZCR), **não** o Silero. O traço [`SpeechDetector`]
//! existe justamente para que trocar por Silero em M1 seja uma segunda
//! implementação do mesmo traço — [`route_speaker`] (T2.2) e o resto do
//! pipeline não mudam quando isso acontecer.

use crate::VAD_WINDOW;

/// Ganho de calibração aplicado ao RMS normalizado antes de comparar com
/// [`VadConfig::threshold`]. `[ESTIMATIVA]` — não existe dado real de call
/// center para calibrar isto ainda (mesma lacuna que motiva U2/U3 no plano).
/// O valor foi escolhido para que o `threshold` default (0.5, herdado da
/// convenção de probabilidade do Silero — blueprint § Coverage Corner 4)
/// classifique corretamente a fixture de referência (tom a `vol 0.5`, RMS
/// medido ≈ 0.353 — ver `scripts/make_fixtures.sh`) como fala, e o silêncio
/// digital puro como silêncio. Hipótese a revisar com dado real em M1.
const ENERGY_GAIN: f32 = 2.0;

/// Configuração do VAD de M0. Os quatro campos espelham a convenção usada
/// pelos dois exemplos do peer sherpa-onnx (blueprint § Coverage Corner 4).
///
/// `min_speech`, `min_silence` e `max_speech` descrevem durações (segundos)
/// destinadas à suavização por histerese de um VAD real (debounce de estado
/// ao longo do tempo). Essa suavização é responsabilidade da implementação
/// de VAD que a consumir — [`EnergyZcrVad`] classifica janela a janela e
/// ainda não a aplica; os valores ficam configurados aqui para que a troca
/// por Silero em M1 não precise de uma nova forma de configuração.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VadConfig {
    /// Limiar de decisão sobre o score de energia normalizado (0.0–1.0).
    pub threshold: f32,
    /// Duração mínima, em segundos, para confirmar transição para fala.
    pub min_speech: f32,
    /// Duração mínima, em segundos, para confirmar transição para silêncio.
    pub min_silence: f32,
    /// Duração máxima, em segundos, de um turno de fala contínuo.
    pub max_speech: f32,
}

impl Default for VadConfig {
    fn default() -> Self {
        Self {
            threshold: 0.5,
            min_speech: 0.25,
            // U2 do plano: os exemplos do peer divergem entre 0.1s e 0.25s;
            // M0 adota 0.25s por ser a opção mais conservadora contra corte
            // de fala. Revisar com dado real de call center em M1.
            min_silence: 0.25,
            // U3 do plano: os exemplos do peer divergem entre 5s e 8s; M0
            // adota 8s porque turnos de atendimento tendem a ser mais longos
            // que os de assistente de voz. Revisar com a distribuição real
            // de duração de turno em M1.
            max_speech: 8.0,
        }
    }
}

/// Estado de fala de uma janela processada.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpeechState {
    Silence,
    Speech,
}

/// Erros tipados do VAD. Nunca panic, nunca silêncio —
/// `.claude/rules/error-handling.md` § 2.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VadError {
    /// A janela recebida não tem exatamente [`VAD_WINDOW`] amostras.
    InvalidWindowSize { expected: usize, got: usize },
}

impl std::fmt::Display for VadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            VadError::InvalidWindowSize { expected, got } => write!(
                f,
                "janela do VAD deve ter {expected} amostras, recebeu {got}"
            ),
        }
    }
}

impl std::error::Error for VadError {}

/// Interface de detecção de fala por janela. Existe para que o Silero ONNX
/// (M1) seja uma segunda implementação deste traço, sem que o roteamento de
/// falante (T2.2) ou o resto do pipeline precisem mudar.
pub trait SpeechDetector {
    /// Classifica uma janela de exatamente [`VAD_WINDOW`] amostras.
    fn process_window(&mut self, window: &[i16]) -> Result<SpeechState, VadError>;
}

/// Implementação de M0: heurística de energia RMS + ZCR. **Não é o Silero** —
/// ver o comentário de módulo. Prova o encanamento (roteamento, buffers,
/// latência) sem depender de um modelo ainda não baixado (`ROADMAP.md` M0 vs
/// M1).
#[derive(Debug, Clone, Copy)]
pub struct EnergyZcrVad {
    config: VadConfig,
}

impl EnergyZcrVad {
    pub fn new(config: VadConfig) -> Self {
        Self { config }
    }
}

impl SpeechDetector for EnergyZcrVad {
    fn process_window(&mut self, window: &[i16]) -> Result<SpeechState, VadError> {
        if window.len() != VAD_WINDOW {
            return Err(VadError::InvalidWindowSize {
                expected: VAD_WINDOW,
                got: window.len(),
            });
        }

        let (rms, zcr) = window_features(window);
        let energy_score = (rms * ENERGY_GAIN).min(1.0);

        // Sinal constante (sem nenhuma oscilação) tem RMS alto mas zero
        // cruzamentos de zero — é DC, não fala. A ZCR existe para filtrar
        // exatamente esse caso; é a metade "ZCR" da heurística de energia/ZCR.
        let is_dc_only = zcr == 0.0 && rms > 0.0;

        let state = if is_dc_only || energy_score < self.config.threshold {
            SpeechState::Silence
        } else {
            SpeechState::Speech
        };
        Ok(state)
    }
}

/// Calcula RMS normalizado (0.0–1.0) e taxa de cruzamento de zero (0.0–1.0)
/// de uma janela de amostras `i16`. Função pura, sem alocação.
fn window_features(window: &[i16]) -> (f32, f32) {
    let n = (window.len().max(1)) as f32;
    let mut sum_sq = 0.0f32;
    let mut crossings = 0u32;
    let mut prev_positive: Option<bool> = None;

    for &sample in window {
        let v = sample as f32 / i16::MAX as f32;
        sum_sq += v * v;

        let positive = sample >= 0;
        if let Some(prev) = prev_positive {
            if prev != positive {
                crossings += 1;
            }
        }
        prev_positive = Some(positive);
    }

    let rms = (sum_sq / n).sqrt();
    let zcr = crossings as f32 / n;
    (rms, zcr)
}

/// Falante atribuído por par de estados de VAD — nunca por modelo de
/// diarização. No caso 1:1 (dominante), a atribuição é 100% correta a custo
/// zero (`PRD.md` § 5 RF-05).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Speaker {
    Agent,
    Customer,
    Both,
    Neither,
}

/// Deriva o falante do par (mic, loopback). Função pura, sem I/O e sem
/// estado compartilhado — thread-safe por construção.
pub fn route_speaker(mic: SpeechState, loopback: SpeechState) -> Speaker {
    match (mic, loopback) {
        (SpeechState::Speech, SpeechState::Silence) => Speaker::Agent,
        (SpeechState::Silence, SpeechState::Speech) => Speaker::Customer,
        (SpeechState::Speech, SpeechState::Speech) => Speaker::Both,
        (SpeechState::Silence, SpeechState::Silence) => Speaker::Neither,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Cobre a metade "ZCR" da heurística: RMS alto sozinho não basta para
    /// classificar como fala quando não há oscilação nenhuma.
    #[test]
    fn constant_dc_signal_is_not_classified_as_speech() {
        let mut vad = EnergyZcrVad::new(VadConfig::default());
        let window = vec![20_000i16; VAD_WINDOW];

        let state = vad
            .process_window(&window)
            .expect("janela de tamanho correto não deve falhar");

        assert_eq!(state, SpeechState::Silence);
    }
}
