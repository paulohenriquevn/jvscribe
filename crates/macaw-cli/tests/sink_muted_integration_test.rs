//! Prova de wiring end-to-end de T2.3 (review B2): a detecção de sink mudo é de
//! fato exercitada pelo caminho de produção — `check_sink_health` +
//! `evaluate_health` — e não só definida.
//!
//! O review pré-merge apontou que esses símbolos não tinham caller. `run_live` em
//! `macaw-cli` agora os chama; este teste prova que, sobre um sink comprovadamente
//! mudo, o caminho produz `Warning::SinkMuted`. Degrada graciosamente se o
//! ambiente não tiver servidor de áudio / `pactl`.

use std::process::Command;

use macaw_audio::capture::{check_sink_health, evaluate_health, Warning};

fn pactl_ok() -> bool {
    Command::new("which")
        .arg("pactl")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

#[test]
fn test_muted_sink_produces_sinkmuted_warning_end_to_end() {
    if !pactl_ok() {
        eprintln!("SKIP: pactl indisponível — não é possível criar um sink mudo controlado");
        return;
    }

    let sink = format!("macaw_muted_it_{}", std::process::id());
    let load = Command::new("pactl")
        .args([
            "load-module",
            "module-null-sink",
            &format!("sink_name={sink}"),
        ])
        .output()
        .expect("pactl load-module deve executar");
    if !load.status.success() {
        eprintln!("SKIP: não foi possível carregar null-sink neste ambiente");
        return;
    }
    let module_id = String::from_utf8_lossy(&load.stdout).trim().to_string();

    // Garante limpeza mesmo se um assert falhar.
    struct Guard(String);
    impl Drop for Guard {
        fn drop(&mut self) {
            let _ = Command::new("pactl")
                .args(["unload-module", &self.0])
                .status();
        }
    }
    let _guard = Guard(module_id);

    let mute = Command::new("pactl")
        .args(["set-sink-mute", &sink, "1"])
        .status()
        .expect("pactl set-sink-mute deve executar");
    assert!(mute.success(), "deveria conseguir mutar o sink de teste");

    // O caminho exato que `run_live` executa antes de capturar o loopback.
    let health = check_sink_health(&sink).expect("check_sink_health deve ler o sink de teste");
    assert!(health.muted, "o sink de teste foi mutado — health.muted deve ser true");

    let warning = evaluate_health(&health);
    assert_eq!(
        warning,
        Some(Warning::SinkMuted),
        "sink mudo deve produzir Warning::SinkMuted — a falha silenciosa que T2.3 previne"
    );
}
