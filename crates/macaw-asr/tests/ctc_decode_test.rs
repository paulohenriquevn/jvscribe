//! Fixture do decode CTC greedy + detok (plano m6-runtime-v0, Fase 1).
//! Padrão portado de sherpa-onnx `context-graph-test.cc` (input conhecido → saída esperada).
//! Fixes do /review 2026-07-26: T-01 (repetição por blank), T-04 (detok fora do range),
//! T-05/06 (um comportamento por teste, fixture único), T-07 (NaN/empate), T-08 (bordas).

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

/// Arquivo temp com nome único por processo+sufixo (T-06: sem estado compartilhado).
fn write_vocab(suffix: &str, body: &str) -> std::path::PathBuf {
    let p = std::env::temp_dir().join(format!("macaw_ctc_{}_{}.txt", std::process::id(), suffix));
    std::fs::write(&p, body).unwrap();
    p
}

// --- argmax (T-05: um comportamento por teste; T-07: NaN/empate) ---------------

#[test]
fn argmax_retorna_indice_do_maior() {
    assert_eq!(argmax(&[0.1, 0.9, 0.3]), 1);
}

#[test]
fn argmax_frame_vazio_retorna_zero() {
    assert_eq!(argmax(&[]), 0); // fail-safe, não panica
}

#[test]
fn argmax_com_nan_nao_panica_e_retorna_indice_valido() {
    // NaN em log-probs indica corrupção upstream (int8/ONNX); não pode panicar.
    let i = argmax(&[0.1, f32::NAN, 0.9]);
    assert!(i < 3, "índice {i} fora de faixa");
}

#[test]
fn argmax_empate_retorna_ultimo() {
    // max_by devolve o último máximo em caso de empate — contrato observável fixado.
    assert_eq!(argmax(&[0.5, 0.5]), 1);
}

// --- ctc_greedy (T-01 semântica central; T-08 bordas) --------------------------

#[test]
fn ctc_greedy_colapsa_blank_e_repeticoes_adjacentes() {
    let vocab = 5;
    let lp = flatten(&[1, 1, 0, 2], vocab); // token1, token1(rep), blank, token2
    assert_eq!(ctc_greedy(&lp, 4, vocab, 0), vec![1, 2]);
}

#[test]
fn ctc_greedy_preserva_repeticao_separada_por_blank() {
    // A PROPRIEDADE QUE DEFINE O CTC: [1, blank, 1] NÃO colapsa → [1, 1].
    // Regressão para decode.rs:41 (prev=blank no frame de blank). Se alguém remover
    // essa atualização, [1,0,1] colapsaria para [1] e ESTE teste pega.
    let vocab = 5;
    let lp = flatten(&[1, 0, 1], vocab);
    assert_eq!(ctc_greedy(&lp, 3, vocab, 0), vec![1, 1]);
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
    assert_eq!(ctc_greedy(&lp, 4, vocab, 0), vec![1, 2]); // para no último completo
}

#[test]
fn ctc_greedy_vocab_zero_da_vazio() {
    // Guard defensivo de decode.rs:28 — ramo antes coberto só por leitura.
    assert_eq!(ctc_greedy(&[], 3, 0, 0), Vec::<usize>::new());
}

#[test]
fn ctc_greedy_t_len_zero_da_vazio() {
    let lp = flatten(&[1, 2], 5);
    assert_eq!(ctc_greedy(&lp, 0, 5, 0), Vec::<usize>::new());
}

#[test]
fn ctc_greedy_respeita_blank_diferente_de_zero() {
    // blank != 0 (o parâmetro nunca era exercitado fora de 0): colapsa o índice 4.
    let vocab = 5;
    let lp = flatten(&[4, 4, 1], vocab); // blank(4), blank(4), token1
    assert_eq!(ctc_greedy(&lp, 3, vocab, 4), vec![1]);
}

// --- detok (T-06 fixture único, um comportamento; T-04 caso negativo) ----------

#[test]
fn detok_troca_fronteira_de_palavra_por_espaco() {
    let p = write_vocab("boundary", "<blk> 0\n\u{2581}ola 1\n\u{2581}mundo 2\n");
    let v = Vocab::load(&p).unwrap();
    assert_eq!(detok(&[1, 2], &v), "ola mundo");
    let _ = std::fs::remove_file(&p);
}

#[test]
fn detok_cola_subword_sem_fronteira() {
    let p = write_vocab("subword", "<blk> 0\n\u{2581}mun 1\ndo 2\n");
    let v = Vocab::load(&p).unwrap();
    assert_eq!(detok(&[1, 2], &v), "mundo"); // ▁mun + do (sem espaço)
    let _ = std::fs::remove_file(&p);
}

#[test]
fn detok_ids_vazios_da_string_vazia() {
    let p = write_vocab("empty_ids", "<blk> 0\n\u{2581}ola 1\n");
    let v = Vocab::load(&p).unwrap();
    assert_eq!(detok(&[], &v), "");
    let _ = std::fs::remove_file(&p);
}

#[test]
fn detok_id_fora_do_range_e_descartado_silenciosamente() {
    // CONTRATO (T-04): quando o vocab de log_probs do modelo diverge do tokens.txt,
    // um id sem piece é descartado (vocab.decode → None → skip). Documenta o descarte
    // como intencional — o teste é o documento executável desse contrato.
    let p = write_vocab("out_of_range", "<blk> 0\n\u{2581}ola 1\n");
    let v = Vocab::load(&p).unwrap(); // len = 2 (ids válidos: 0, 1)
    assert_eq!(detok(&[99], &v), ""); // id 99 não existe → descartado
    assert_eq!(detok(&[1, 99, 1], &v), "ola ola"); // válidos rendem, 99 sumiu
    let _ = std::fs::remove_file(&p);
}
