//! Biblioteca do `macaw-cli` — expõe o módulo `app` (o servidor do dashboard de
//! teste) para que testes de integração possam exercitá-lo dentro do próprio
//! processo, sem depender de subir um binário externo.

pub mod app;
pub mod transcribe;
