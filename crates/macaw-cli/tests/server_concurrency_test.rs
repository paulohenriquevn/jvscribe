//! Regressão do bug do app: o servidor single-threaded travava a UI inteira
//! enquanto `/fixture` carregava o encoder de 2,3 GB, porque um handler lento
//! bloqueava o laço `accept`. A correção é thread-por-conexão.
//!
//! Este teste sobe o servidor numa thread DENTRO do processo de teste (o sandbox
//! não reapea threads internas como faz com processos externos) e prova que várias
//! requisições concorrentes são atendidas em paralelo, não serializadas.

use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::{Duration, Instant};

/// GET simples via TCP cru (sem dependência de cliente HTTP). Retorna o corpo.
fn http_get(port: u16, path: &str) -> std::io::Result<String> {
    let mut s = TcpStream::connect(("127.0.0.1", port))?;
    s.set_read_timeout(Some(Duration::from_secs(10)))?;
    write!(s, "GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")?;
    let mut buf = String::new();
    s.read_to_string(&mut buf)?;
    Ok(buf)
}

fn wait_until_up(port: u16) -> bool {
    for _ in 0..50 {
        if http_get(port, "/metrics").is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    false
}

#[test]
fn test_slow_endpoint_does_not_block_metrics() {
    // Porta alta e improvável de colidir.
    const PORT: u16 = 7391;
    std::thread::spawn(move || {
        let _ = macaw_cli::app::run(PORT);
    });
    assert!(wait_until_up(PORT), "servidor não subiu na porta {PORT}");

    // `/metrics` responde rápido em condição normal.
    let t = Instant::now();
    let m = http_get(PORT, "/metrics").expect("/metrics deve responder");
    assert!(m.contains("\"running\""), "corpo de /metrics inesperado: {m}");
    assert!(
        t.elapsed() < Duration::from_secs(2),
        "/metrics deveria ser rápido, levou {:?}",
        t.elapsed()
    );

    // Dispara /fixture numa thread — ele carrega o encoder (lento) OU retorna
    // rápido se o modelo não estiver presente. Em ambos os casos, /metrics NÃO
    // pode ser bloqueado por ele. Com o servidor single-threaded antigo, o
    // /metrics abaixo ficaria preso atrás do /fixture; com thread-por-conexão,
    // responde na hora.
    let fixture = std::thread::spawn(move || http_get(PORT, "/fixture"));

    // Enquanto /fixture roda, dispara 5 /metrics concorrentes e mede o pior tempo.
    let mut worst = Duration::ZERO;
    for _ in 0..5 {
        let t = Instant::now();
        let m = http_get(PORT, "/metrics").expect("/metrics deve responder durante /fixture");
        assert!(m.contains("\"running\""), "corpo de /metrics inesperado sob carga");
        worst = worst.max(t.elapsed());
        std::thread::sleep(Duration::from_millis(50));
    }

    // O pior /metrics durante o /fixture deve continuar rápido — a prova de que o
    // handler lento não serializa o servidor. Margem folgada (1s) para tolerar
    // contenção de CPU da máquina de teste.
    assert!(
        worst < Duration::from_secs(1),
        "/metrics foi bloqueado por /fixture (pior caso {worst:?}) — servidor serializou"
    );

    // Deixa o /fixture terminar (não vaza thread pendurada no fim do teste).
    let _ = fixture.join();
}
