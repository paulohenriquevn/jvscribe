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

use std::fmt;
use std::path::Path;

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
        // Otimização de grafo DESABILITADA em M0. `[MEDIDO]` 2026-07-24: com a
        // otimização default (`Level3`), abrir o encoder (grafo de 40 MB +
        // pesos externos `encoder-model.onnx.data` de ~2,3 GB, fp32) não terminou
        // em 180 s neste ambiente. M0 prova o encanamento — a otimização de grafo é
        // escopo de M6 (runtime otimizado), não deste walking skeleton. Sem
        // otimização, o load é praticamente instantâneo.
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

    /// Caminho do modelo carregado.
    #[must_use]
    pub fn model_path(&self) -> &str {
        &self.model_path
    }
}
