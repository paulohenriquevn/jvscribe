//! Adapter de inferência.
//!
//! **Descartável por construção.** A arquitetura do modelo segue pendente
//! (`PRD.md` § 8.1) e o ADR de M2 pode substituir este crate inteiro. A fronteira
//! existe justamente para que essa troca não alcance o DSP em `macaw-audio`.
//!
//! O modelo usado em M0 é emprestado — `nemo-conformer-tdt`, 16 kHz, offline
//! (ADR D4 do blueprint). **Nenhum número de qualidade ou latência obtido aqui é
//! válido para o produto**; todos devem ser rotulados
//! `[MEDIDO — encanamento apenas]`.

pub mod decode;

use std::fmt;
use std::path::Path;

/// Id do token blank na convenção do export icefall (Zipformer-CTC). Premissa específica
/// da arquitetura ainda não travada em M4 (`PRD.md` § 8.1, 2 finalistas) — nomeada para
/// que o swap ao decidir o finalista não caie em número mágico (ARCH-02 do /review).
const ICEFALL_BLANK_ID: usize = 0;

/// Erros da fronteira de inferência.
///
/// Todos tipados e com contexto suficiente para diagnóstico sem debugger, conforme
/// `.claude/rules/error-handling.md` § 2.
#[derive(Debug)]
pub enum AsrError {
    /// Arquivo de modelo ONNX não encontrado no caminho informado.
    ModelNotFound { path: String },
    /// Arquivo de vocabulário não encontrado.
    VocabNotFound { path: String },
    /// Vocabulário presente mas com conteúdo inválido.
    InvalidVocab { path: String, reason: String },
    /// Arquivo existe mas o runtime ONNX recusou abri-lo.
    SessionFailed { path: String, reason: String },
    /// Falha ao executar o forward pass.
    InferenceFailed { reason: String },
    /// Operação de inferência pedida a um motor sem sessão carregada.
    NoSession,
}

impl fmt::Display for AsrError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ModelNotFound { path } => write!(f, "modelo ONNX não encontrado: {path}"),
            Self::VocabNotFound { path } => write!(f, "vocabulário não encontrado: {path}"),
            Self::InvalidVocab { path, reason } => {
                write!(f, "vocabulário inválido em {path}: {reason}")
            }
            Self::SessionFailed { path, reason } => {
                write!(f, "runtime ONNX recusou o modelo {path}: {reason}")
            }
            Self::InferenceFailed { reason } => write!(f, "forward pass falhou: {reason}"),
            Self::NoSession => write!(f, "motor sem sessão carregada"),
        }
    }
}

impl std::error::Error for AsrError {}

/// Vocabulário de tokens do modelo.
///
/// Formato do modelo emprestado: uma entrada por linha, `<token> <id>`.
#[derive(Debug)]
pub struct Vocab {
    tokens: Vec<String>,
}

impl Vocab {
    /// Carrega o vocabulário de um arquivo.
    ///
    /// # Erros
    ///
    /// - [`AsrError::VocabNotFound`] quando o arquivo não existe
    /// - [`AsrError::InvalidVocab`] quando o arquivo não tem nenhuma linha útil
    pub fn load(path: &Path) -> Result<Self, AsrError> {
        let raw = std::fs::read_to_string(path).map_err(|_| AsrError::VocabNotFound {
            path: path.display().to_string(),
        })?;

        let tokens: Vec<String> = raw
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(|l| match l.rsplit_once(' ') {
                // `<token> <id>` — o token é tudo antes do último espaço.
                Some((tok, _id)) => tok.to_string(),
                None => l.to_string(),
            })
            .collect();

        if tokens.is_empty() {
            return Err(AsrError::InvalidVocab {
                path: path.display().to_string(),
                reason: "arquivo sem nenhuma linha não vazia".to_string(),
            });
        }

        Ok(Self { tokens })
    }

    /// Número de tokens carregados.
    #[must_use]
    pub fn len(&self) -> usize {
        self.tokens.len()
    }

    /// `true` quando o vocabulário está vazio.
    ///
    /// Nunca ocorre em instâncias de [`Vocab::load`], que rejeita arquivos vazios —
    /// existe para satisfazer a convenção de API esperada pelo clippy.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.tokens.is_empty()
    }

    /// `true` para símbolo de desambiguação do lexicon FST do icefall (`#0`, `#1`, …).
    ///
    /// Esses símbolos existem no `tokens.txt` para a construção do `L.fst` e **nunca são
    /// emitidos pelo modelo**. `[MEDIDO]` 2026-07-30: o export do runtime tem 2 deles
    /// (502 linhas para 500 classes) e o de avaliação tem 3 (503 linhas para 500 classes).
    fn is_disambig(token: &str) -> bool {
        matches!(token.strip_prefix('#'), Some(rest)
            if !rest.is_empty() && rest.bytes().all(|b| b.is_ascii_digit()))
    }

    /// Número de tokens **emitíveis** — exclui os símbolos de desambiguação.
    ///
    /// É esta a grandeza comparável com a última dimensão de `log_probs`;
    /// [`Vocab::len`] conta linhas do arquivo e **não** serve para essa comparação.
    #[must_use]
    pub fn real_len(&self) -> usize {
        self.tokens.iter().filter(|t| !Self::is_disambig(t)).count()
    }

    /// Fingerprint de **identidade** do vocabulário: SHA-256 sobre a sequência ordenada
    /// `id\ttoken\n` dos tokens emitíveis.
    ///
    /// Cardinalidade não distingue vocabulários: `[MEDIDO]` 2026-07-30, os dois artefatos
    /// em disco têm 500 tokens reais cada e **492 dos 500 ids mapeiam tokens diferentes**.
    /// Só o conteúdo distingue — daí o hash sobre `(id, token)`, e não sobre a contagem.
    ///
    /// Símbolos de desambiguação são excluídos para que dois lang-dirs equivalentes com
    /// número diferente de `#N` produzam o mesmo fingerprint (D2 do plano de M9).
    #[must_use]
    pub fn fingerprint(&self) -> String {
        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        for (id, token) in self.tokens.iter().enumerate() {
            if Self::is_disambig(token) {
                continue;
            }
            hasher.update(id.to_string().as_bytes());
            hasher.update(b"\t");
            hasher.update(token.as_bytes());
            hasher.update(b"\n");
        }
        hasher
            .finalize()
            .iter()
            .fold(String::with_capacity(64), |mut acc, b| {
                use std::fmt::Write as _;
                let _ = write!(acc, "{b:02x}");
                acc
            })
    }

    /// Resolve um id de token para o texto correspondente.
    #[must_use]
    pub fn decode(&self, id: usize) -> Option<&str> {
        self.tokens.get(id).map(String::as_str)
    }
}

/// Motor de inferência.
///
/// Deliberadamente **não compartilhado entre threads**: a sessão ONNX é stateful e
/// drenada por um único consumidor. Compartilhá-la exigiria sincronização sem
/// ganho no desenho de M0 (um consumidor por pipeline).
#[derive(Debug)]
pub struct AsrEngine {
    model_path: String,
    session: Option<ort::session::Session>,
}

impl AsrEngine {
    /// Verifica a presença dos artefatos do modelo.
    ///
    /// Em M0 esta função valida a fronteira de I/O; a sessão ONNX propriamente dita
    /// é construída em `macaw-cli`, que é o ponto de composição
    /// (`.claude/rules/architecture.md` § 1).
    ///
    /// # Erros
    ///
    /// [`AsrError::ModelNotFound`] quando o arquivo não existe.
    pub fn load(model_path: &Path) -> Result<Self, AsrError> {
        if !model_path.exists() {
            return Err(AsrError::ModelNotFound {
                path: model_path.display().to_string(),
            });
        }

        let path_str = model_path.display().to_string();
        let session_err = |reason: String| AsrError::SessionFailed {
            path: path_str.clone(),
            reason,
        };
        // Otimização de grafo DESABILITADA. `[MEDIDO]` 2026-07-24: com a otimização
        // default (`Level3`), abrir o encoder fp32 de 2,3 GB de M0 não terminou em
        // 180 s. `[MEDIDO]` 2026-07-26: `Level3` também DEGRADA a inferência do int8
        // de produção com esta `libonnxruntime` carregada via `load-dynamic` (clip
        // de 6,84 s: 0,55 s com Disable → >30 s com Level3). Por isso Disable fica.
        // A lentidão em utterances LONGAS (ver `runtime-eval-findings.md`) é ortogonal
        // — não é o nível de otimização.
        let mut builder = ort::session::Session::builder()
            .map_err(|e| session_err(e.to_string()))?
            .with_optimization_level(ort::session::builder::GraphOptimizationLevel::Disable)
            .map_err(|e| session_err(e.to_string()))?;
        let session = builder
            .commit_from_file(model_path)
            .map_err(|e| session_err(e.to_string()))?;

        Ok(Self {
            model_path: model_path.display().to_string(),
            session: Some(session),
        })
    }

    /// Nomes das entradas do grafo carregado.
    ///
    /// Em M0 serve como evidência de que o modelo foi de fato aberto pelo runtime,
    /// não apenas encontrado no sistema de arquivos.
    #[must_use]
    pub fn input_names(&self) -> Vec<String> {
        self.session
            .as_ref()
            .map(|s| s.inputs().iter().map(|i| i.name().to_string()).collect())
            .unwrap_or_default()
    }

    /// Nomes das saídas do grafo carregado.
    #[must_use]
    pub fn output_names(&self) -> Vec<String> {
        self.session
            .as_ref()
            .map(|s| s.outputs().iter().map(|o| o.name().to_string()).collect())
            .unwrap_or_default()
    }

    /// Roda o forward pass do encoder sobre features log-mel reais.
    ///
    /// `mel` é o log-mel achatado em ordem row-major `[n_mels * n_frames]` (128
    /// bins por frame); `n_frames` é o número de frames temporais. Retorna o shape
    /// `[dim0, hidden, dim2]` do tensor de saída do encoder — evidência de que a
    /// fronteira features→modelo funciona de ponta a ponta sobre dados reais.
    ///
    /// Este é o encanamento acústico que M0 prova. O decode completo (encoder →
    /// decoder_joint → texto) é específico da arquitetura do modelo e está
    /// **BLOQUEADO POR M2** (`asr-evidence-discipline.md` § 0).
    ///
    /// # Erros
    ///
    /// [`AsrError::InferenceFailed`] se o grafo não roda, ou
    /// [`AsrError::NoSession`] se o motor foi construído sem sessão.
    pub fn encode(
        &mut self,
        mel: &[f32],
        n_mels: usize,
        n_frames: usize,
    ) -> Result<Vec<i64>, AsrError> {
        let session = self.session.as_mut().ok_or(AsrError::NoSession)?;

        let audio = ndarray::Array3::from_shape_vec((1, n_mels, n_frames), mel.to_vec())
            .map_err(|e| AsrError::InferenceFailed {
                reason: format!("shape de features inválido: {e}"),
            })?;
        let length = ndarray::Array1::from_vec(vec![n_frames as i64]);

        let audio_val = ort::value::Value::from_array(audio)
            .map_err(|e| AsrError::InferenceFailed { reason: e.to_string() })?;
        let length_val = ort::value::Value::from_array(length)
            .map_err(|e| AsrError::InferenceFailed { reason: e.to_string() })?;

        let outputs = session
            .run(ort::inputs![
                "audio_signal" => audio_val,
                "length" => length_val,
            ])
            .map_err(|e| AsrError::InferenceFailed { reason: e.to_string() })?;

        let (shape, _) = outputs["outputs"]
            .try_extract_tensor::<f32>()
            .map_err(|e| AsrError::InferenceFailed { reason: e.to_string() })?;
        Ok(shape.to_vec())
    }

    /// Roda a inferência CTC do NOSSO modelo icefall (contrato `x`(1,T,80)/`x_lens` →
    /// `log_probs`(1,T,vocab)) e retorna `(log_probs achatado, T, vocab)`.
    ///
    /// Diferente de [`Self::encode`] (placeholder de M0 com nomes NeMo `audio_signal`/`length`
    /// que só devolve o SHAPE), este método usa os nomes do export do icefall e retorna os
    /// **dados** — habilitando o decode. ADR-1 do plano `m6-runtime-v0`: adicionar, não mudar.
    ///
    /// `mel` é o log-mel `(T, 80)` achatado em row-major.
    ///
    /// # Erros
    /// [`AsrError::NoSession`] sem sessão; [`AsrError::InferenceFailed`] em shape/grafo inválido.
    pub fn ctc_logits(
        &mut self,
        mel: &[f32],
        n_frames: usize,
    ) -> Result<(Vec<f32>, usize, usize), AsrError> {
        let session = self.session.as_mut().ok_or(AsrError::NoSession)?;

        let x = ndarray::Array3::from_shape_vec((1, n_frames, 80), mel.to_vec()).map_err(|e| {
            AsrError::InferenceFailed { reason: format!("shape de features inválido: {e}") }
        })?;
        let x_lens = ndarray::Array1::from_vec(vec![n_frames as i64]);

        let x_val = ort::value::Value::from_array(x)
            .map_err(|e| AsrError::InferenceFailed { reason: e.to_string() })?;
        let xl_val = ort::value::Value::from_array(x_lens)
            .map_err(|e| AsrError::InferenceFailed { reason: e.to_string() })?;

        let outputs = session
            .run(ort::inputs!["x" => x_val, "x_lens" => xl_val])
            .map_err(|e| AsrError::InferenceFailed { reason: e.to_string() })?;

        let (shape, data) = outputs["log_probs"]
            .try_extract_tensor::<f32>()
            .map_err(|e| AsrError::InferenceFailed { reason: e.to_string() })?;
        if shape.len() != 3 {
            return Err(AsrError::InferenceFailed {
                reason: format!("log_probs esperado 3-D, veio {:?}", shape),
            });
        }
        let t = shape[1] as usize;
        let vocab = shape[2] as usize;
        Ok((data.to_vec(), t, vocab))
    }

    /// Transcreve um log-mel `(T, 80)` em texto: `ctc_logits` → CTC greedy → detok BPE.
    /// `vocab` mapeia ids de token → pieces (carregado do `tokens.txt`). blank = 0 (icefall).
    ///
    /// # Erros
    /// Propaga os erros de [`Self::ctc_logits`].
    pub fn transcribe(
        &mut self,
        mel: &[f32],
        n_frames: usize,
        vocab: &Vocab,
    ) -> Result<String, AsrError> {
        let (logits, t, v) = self.ctc_logits(mel, n_frames)?;
        let ids = crate::decode::ctc_greedy(&logits, t, v, ICEFALL_BLANK_ID);
        Ok(crate::decode::detok(&ids, vocab))
    }

    /// Caminho do modelo carregado.
    #[must_use]
    pub fn model_path(&self) -> &str {
        &self.model_path
    }
}
