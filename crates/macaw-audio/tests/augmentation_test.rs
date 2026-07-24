//! Testes da cadeia de augmentação telefônica (M1 — T2.1).
//!
//! Invocam `scripts/telephone_augment.sh` (que usa `sox`) sobre um tom gerado, e
//! verificam as propriedades do WAV de saída. Degradam graciosamente quando
//! `sox` está ausente (padrão de `capture_test.rs`), em vez de falhar por um
//! motivo alheio ao código sob teste.

use std::process::Command;

fn tool_available(name: &str) -> bool {
    Command::new("which")
        .arg(name)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn script_path() -> String {
    format!("{}/../../scripts/telephone_augment.sh", env!("CARGO_MANIFEST_DIR"))
}

/// Gera um tom senoidal 16 kHz mono via sox e retorna o caminho.
fn generate_tone_16k(path: &std::path::Path, secs: u32, freq: u32) {
    let status = Command::new("sox")
        .args([
            "-n",
            "-r",
            "16000",
            "-c",
            "1",
            "-b",
            "16",
            path.to_str().unwrap(),
            "synth",
            &secs.to_string(),
            "sine",
            &freq.to_string(),
            "vol",
            "0.5",
        ])
        .status()
        .expect("sox deve executar (pré-checado)");
    assert!(status.success(), "sox falhou ao gerar tom");
}

fn soxi_field(path: &std::path::Path, flag: &str) -> String {
    let out = Command::new("soxi")
        .args([flag, path.to_str().unwrap()])
        .output()
        .expect("soxi deve executar");
    String::from_utf8_lossy(&out.stdout).trim().to_string()
}

/// Caminho temporário único por processo (review TEST-M1-06) — evita colisão de
/// filesystem entre execuções concorrentes do binário de teste.
fn tmp_unique(name: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!("macaw_aug_{}_{}", std::process::id(), name))
}

#[test]
fn test_augment_output_is_8khz_mono() {
    if !(tool_available("sox") && tool_available("soxi")) {
        eprintln!("SKIP: sox/soxi ausentes — cadeia de augmentação não pode ser exercitada");
        return;
    }
    let input = tmp_unique("in_16k.wav");
    let output = tmp_unique("out_8k.wav");
    generate_tone_16k(&input, 2, 440);

    let status = Command::new("bash")
        .args([script_path(), input.to_string_lossy().into_owned(), output.to_string_lossy().into_owned()])
        .status()
        .expect("script deve executar");
    assert!(status.success(), "cadeia de augmentação deveria ter sucesso");

    // Saída 8 kHz mono (canal telefônico).
    assert_eq!(soxi_field(&output, "-r"), "8000", "saída deve ser 8 kHz");
    assert_eq!(soxi_field(&output, "-c"), "1", "saída deve ser mono");

    let _ = std::fs::remove_file(&input);
    let _ = std::fs::remove_file(&output);
}

#[test]
fn test_augment_missing_input_is_error() {
    if !tool_available("sox") {
        eprintln!("SKIP: sox ausente");
        return;
    }
    // Input inexistente → o script falha fast (exit code não-zero), não silencioso.
    let output = std::env::temp_dir().join("macaw_aug_should_not_exist.wav");
    let status = Command::new("bash")
        .args([
            script_path(),
            "/caminho/que/nao/existe/xyz.wav".to_string(),
            output.to_string_lossy().into_owned(),
        ])
        .status()
        .expect("script deve executar");
    assert!(
        !status.success(),
        "input inexistente deveria falhar com exit code não-zero"
    );
}

#[test]
fn test_augment_band_attenuates_above_3400hz() {
    if !(tool_available("sox") && tool_available("soxi")) {
        eprintln!("SKIP: sox/soxi ausentes");
        return;
    }
    // Tom de 3800 Hz (acima da banda telefônica 300-3400) deve ser fortemente
    // atenuado; um tom de 1000 Hz (dentro da banda) deve passar.
    let in_high = tmp_unique("3800.wav");
    let in_mid = tmp_unique("1000.wav");
    let out_high = tmp_unique("3800_out.wav");
    let out_mid = tmp_unique("1000_out.wav");
    generate_tone_16k(&in_high, 2, 3800);
    generate_tone_16k(&in_mid, 2, 1000);

    for (i, o) in [(&in_high, &out_high), (&in_mid, &out_mid)] {
        let status = Command::new("bash")
            .args([script_path(), i.to_string_lossy().into_owned(), o.to_string_lossy().into_owned()])
            .status()
            .expect("script deve executar");
        assert!(status.success());
    }

    // Amplitude RMS via `sox stat`: o tom fora da banda deve ter RMS bem menor
    // que o dentro da banda. Retorna Option — parse-failure NÃO pode virar 0.0 e
    // satisfazer a asserção trivialmente (review TEST-M1-01, falso-verde).
    let rms = |p: &std::path::Path| -> Option<f64> {
        let out = Command::new("sox")
            .args([p.to_str().unwrap(), "-n", "stat"])
            .output()
            .expect("sox stat deve executar");
        let s = String::from_utf8_lossy(&out.stderr);
        s.lines()
            .find(|l| l.contains("RMS") && l.contains("amplitude"))
            .and_then(|l| l.split_whitespace().last())
            .and_then(|v| v.parse::<f64>().ok())
    };
    let rms_high = rms(&out_high).expect("RMS do tom de 3800 Hz deve ser parseável");
    let rms_mid = rms(&out_mid).expect("RMS do tom de 1000 Hz deve ser parseável");
    assert!(
        rms_high > 0.0 && rms_mid > 0.0,
        "ambos os RMS devem ser > 0 (parse real, não falso-verde): high={rms_high}, mid={rms_mid}"
    );
    assert!(
        rms_high < rms_mid * 0.5,
        "tom de 3800 Hz (RMS {rms_high}) deveria ser fortemente atenuado vs 1000 Hz (RMS {rms_mid})"
    );

    for p in [&in_high, &in_mid, &out_high, &out_mid] {
        let _ = std::fs::remove_file(p);
    }
}
