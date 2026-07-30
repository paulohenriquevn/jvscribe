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
    // ⚠️ FLAKY CONHECIDO (M9) — `[MEDIDO]` 2026-07-30 nesta máquina:
    //   com o load do encoder de 2,3 GB : 2 falhas em 8
    //   sem o load                       : 0 falhas em 8
    //
    // Mecanismo: `/fixture` carrega um encoder de 2,3 GB. Com ~1 GB de RAM livre, o ONNX
    // Runtime aborta em C++ (`abort`, não panic de Rust), o processo de teste inteiro morre e
    // TODAS as conexões resetam — o sintoma observado é `ConnectionReset` em `/metrics`.
    //
    // NÃO foi "corrigido" apontando o teste para um diretório sem modelo: isso removeria a
    // lentidão que o teste existe para medir (endpoint lento não bloqueia `/metrics`), e
    // deixaria uma asserção vazia com cara de verde. Duas correções REAIS foram aplicadas no
    // caminho (dois `.expect` que envenenavam o mutex), o que reduziu de ~33% para ~10%; o
    // resíduo é pressão de memória do ambiente, não defeito do servidor.
    //
    // Fix apropriado, fora do escopo de M9: um endpoint lento sintético para exercitar
    // concorrência sem depender de um artefato de 2,3 GB.


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

// --- M9/T4.1 — a rota /m1 não pode devolver 200 vazio em silêncio ----------------
//
// Defeito medido em 2026-07-30: `m1_measurements_json` lia
// `../../knowledge-base/measurements` (removido no commit c7c67b9) e engolia o ENOENT com
// `unwrap_or_default()`. A rota respondia `200 OK` com `{"baseline":"","harness":""}` para
// sempre, e o dashboard renderizava o placeholder — indistinguível de "medição zero".
// Viola `.claude/rules/error-handling.md` § 2 (erro engolido).

#[test]
fn m1_measurements_sinaliza_ausencia_em_vez_de_devolver_vazio() {
    let json = macaw_cli::app::m1_measurements_json();
    // Ou traz conteúdo real, ou diz explicitamente que não encontrou — nunca string vazia
    // silenciosa.
    let vazio_silencioso = json.contains("\"baseline\":\"\"") && !json.contains("\"error\"");
    assert!(
        !vazio_silencioso,
        "a rota devolveu payload vazio sem sinalizar a causa: {json}"
    );
}
