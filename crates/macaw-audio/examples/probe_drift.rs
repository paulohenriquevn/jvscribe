//! Sonda de sincronia entre mic e loopback (T5.2 / R1).
//! Captura ambos por N segundos e reporta a diferença de contagem.
//! Rodado em durações crescentes, distingue offset de startup (diferença
//! ABSOLUTA constante) de drift contínuo (diferença cresce com o tempo).
use macaw_audio::capture::{spawn_capture, CaptureConfig};
use std::process::Command;
use std::sync::mpsc::Receiver;
use std::thread;
use std::time::Duration;

fn drain(rx: &Receiver<Vec<i16>>) -> usize {
    let mut t = 0;
    while let Ok(c) = rx.try_recv() { t += c.len(); }
    t
}

fn main() {
    let secs: u64 = std::env::args().nth(1).and_then(|s| s.parse().ok()).unwrap_or(8);
    let sink = format!("macaw_drift_probe_{}", std::process::id());
    // null-sink + tom contínuo
    let load = Command::new("pactl").args(["load-module","module-null-sink",
        &format!("sink_name={sink}")]).output().expect("pactl load");
    let mod_id = String::from_utf8_lossy(&load.stdout).trim().to_string();
    let tone = format!("/tmp/{sink}.wav");
    Command::new("sox").args(["-n","-r","16000","-c","1",&tone,"synth",
        &format!("{}",secs+6),"sine","440","vol","0.5"]).status().ok();
    let mut play = Command::new("paplay").args(["-d",&sink,&tone]).spawn().expect("paplay");
    thread::sleep(Duration::from_millis(2500));

    let mic = spawn_capture(CaptureConfig{ source:"@DEFAULT_SOURCE@".into(), sample_rate:16000, channels:1 })
        .or_else(|_| spawn_capture(CaptureConfig{ source:"alsa_input.pci-0000_00_1f.3.analog-stereo".into(), sample_rate:16000, channels:1 }))
        .expect("mic");
    let mon = spawn_capture(CaptureConfig{ source:format!("{sink}.monitor"), sample_rate:16000, channels:1 })
        .expect("monitor");

    thread::sleep(Duration::from_secs(secs));
    let m = drain(&mic); let n = drain(&mon);
    let diff = (m as i64 - n as i64).abs();
    println!("DUR={}s mic={} mon={} diff_abs={} diff_s={:.2} pct={:.1}",
        secs, m, n, diff, diff as f64/16000.0, diff as f64/m.max(n) as f64*100.0);

    let _ = play.kill();
    let _ = play.wait();
    Command::new("pactl").args(["unload-module",&mod_id]).status().ok();
    let _ = std::fs::remove_file(&tone);
}
