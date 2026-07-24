use std::time::Instant;
fn main() {
    let path = std::env::args().nth(1).expect("uso: probe_load <modelo>");
    eprintln!("carregando {path} com otimização DISABLE...");
    let t = Instant::now();
    let mut b = ort::session::Session::builder().unwrap()
        .with_optimization_level(ort::session::builder::GraphOptimizationLevel::Disable).unwrap();
    match b.commit_from_file(&path) {
        Ok(s) => println!("OK LOAD_MS={} inputs={} outputs={}",
            t.elapsed().as_millis(), s.inputs().len(), s.outputs().len()),
        Err(e) => println!("ERRO após {}ms: {e}", t.elapsed().as_millis()),
    }
}
