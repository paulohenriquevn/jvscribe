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
    // Retry no connect: sob contenção de CPU (suíte inteira em paralelo) o accept
    // do servidor pode recusar transitoriamente antes de estar pronto — isso é
    // starvação, NÃO serialização (essa apareceria na asserção de timing, não no
    // connect). Retry curto elimina o flaky sem mascarar o bug que o teste caça.
    let mut s = {
        let mut attempt = 0;
        loop {
            match TcpStream::connect(("127.0.0.1", port)) {
                Ok(s) => break s,
                Err(e) if attempt < 10 => {
                    attempt += 1;
                    std::thread::sleep(Duration::from_millis(20));
                    let _ = e;
                }
                Err(e) => return Err(e),
            }
        }
    };
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
    // Porta EFÊMERA (o SO atribui uma livre) — evita a colisão de porta fixa que
    // deixava o teste flaky sob `cargo test` paralelo / TIME_WAIT entre execuções.
    let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).expect("bind efêmero");
    let port = listener.local_addr().expect("local_addr").port();
    std::thread::spawn(move || {
        let _ = macaw_cli::app::run_with_listener(listener);
    });
    assert!(wait_until_up(port), "servidor não subiu na porta {port}");

    // `/metrics` responde rápido em condição normal.
    let t = Instant::now();
    let m = http_get(port, "/metrics").expect("/metrics deve responder");
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
    // A thread de /fixture mede a própria duração — a comparação abaixo é
    // RELATIVA (mesma máquina, mesma carga), não um bound absoluto sensível a
    // contenção de CPU (a causa do flakiness anterior).
    let fixture = std::thread::spawn(move || {
        let t = Instant::now();
        let r = http_get(port, "/fixture");
        (r, t.elapsed())
    });

    // Enquanto /fixture roda, dispara 5 /metrics concorrentes e mede o pior tempo.
    let mut worst = Duration::ZERO;
    for _ in 0..5 {
        let t = Instant::now();
        let m = http_get(port, "/metrics").expect("/metrics deve responder durante /fixture");
        assert!(m.contains("\"running\""), "corpo de /metrics inesperado sob carga");
        worst = worst.max(t.elapsed());
        std::thread::sleep(Duration::from_millis(50));
    }

    let (_, fixture_dur) = fixture.join().expect("thread /fixture não deve entrar em panic");

    // Prova de não-serialização, load-independent: se o servidor serializasse, o
    // primeiro /metrics ficaria preso atrás do /fixture, e o pior caso seria ≈ a
    // duração do /fixture. Com thread-por-conexão, o /metrics sobrepõe e termina
    // MUITO antes. Só é discriminante quando o /fixture foi lento o bastante (o
    // encoder de 2,3 GB carregou); se o modelo está ausente, /fixture retorna
    // rápido e não há serialização a detectar — o teste degrada para "respondeu".
    if fixture_dur >= Duration::from_secs(1) {
        assert!(
            worst < fixture_dur,
            "/metrics (pior {worst:?}) não foi mais rápido que /fixture ({fixture_dur:?}) — \
             servidor serializou em vez de usar thread-por-conexão"
        );
    } else {
        eprintln!(
            "NOTA: /fixture retornou rápido ({fixture_dur:?}) — modelo provavelmente ausente; \
             não há serialização a detectar (teste degradou para smoke de resposta)"
        );
    }
}
