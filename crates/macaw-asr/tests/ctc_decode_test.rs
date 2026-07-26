//! Fixture do decode CTC greedy + detok (plano m6-runtime-v0, Fase 1).
//! Padrão portado de sherpa-onnx `context-graph-test.cc` (input conhecido → saída esperada).

use macaw_asr::decode::{argmax, ctc_greedy, detok};
use macaw_asr::Vocab;

/// Frame de `vocab` classes com o máximo (log-prob 1.0) na classe `hot`.
fn frame(vocab: usize, hot: usize) -> Vec<f32> {
    let mut f = vec![0.0f32; vocab];
    f[hot] = 1.0;
    f
}

fn flatten(frames: &[usize], vocab: usize) -> Vec<f32> {
    let mut lp = Vec::new();
    for &h in frames {
        lp.extend(frame(vocab, h));
    }
    lp
}

#[test]
fn argmax_pega_o_maior() {
    assert_eq!(argmax(&[0.1, 0.9, 0.3]), 1);
    assert_eq!(argmax(&[]), 0); // fail-safe
}

#[test]
fn ctc_greedy_colapsa_blank_e_repeticoes() {
    let vocab = 5;
    // frames argmax: token1, token1 (repetido), blank(0), token2
    let lp = flatten(&[1, 1, 0, 2], vocab);
    let out = ctc_greedy(&lp, 4, vocab, 0);
    assert_eq!(out, vec![1, 2]); // repetido colapsado, blank removido
}

#[test]
fn ctc_greedy_tudo_blank_da_vazio() {
    let vocab = 5;
    let lp = flatten(&[0, 0, 0], vocab);
    assert_eq!(ctc_greedy(&lp, 3, vocab, 0), Vec::<usize>::new());
}

#[test]
fn ctc_greedy_entrada_curta_nao_panica() {
    let vocab = 5;
    let lp = flatten(&[1, 2], vocab); // só 2 frames de dados
    // pede 4 frames mas só há 2 — para no último completo, sem panic
    assert_eq!(ctc_greedy(&lp, 4, vocab, 0), vec![1, 2]);
}

#[test]
fn detok_junta_pieces_e_troca_fronteira_por_espaco() {
    let dir = std::env::temp_dir();
    let p = dir.join("macaw_ctc_decode_test_tokens.txt");
    // formato do Vocab::load: "<token> <id>" por linha, em ordem de id
    std::fs::write(&p, "<blk> 0\n\u{2581}ola 1\n\u{2581}mundo 2\ndo 3\n").unwrap();
    let v = Vocab::load(&p).unwrap();

    assert_eq!(detok(&[1, 2], &v), "ola mundo");
    // subword sem fronteira cola na palavra anterior: ▁mun + do
    std::fs::write(&p, "<blk> 0\n\u{2581}mun 1\ndo 2\n").unwrap();
    let v2 = Vocab::load(&p).unwrap();
    assert_eq!(detok(&[1, 2], &v2), "mundo");
    let _ = std::fs::remove_file(&p);
}
