//! Tabela-verdade do roteamento de falante (T2.2).
//!
//! `route_speaker` é a decisão de maior alavancagem do projeto: no caso 1:1
//! dominante, a diarização não precisa existir (`PRD.md` § 5 RF-05).

use macaw_audio::vad::{route_speaker, Speaker, SpeechState};

#[test]
fn test_speaker_routing_truth_table() {
    assert_eq!(
        route_speaker(SpeechState::Speech, SpeechState::Silence),
        Speaker::Agent
    );
    assert_eq!(
        route_speaker(SpeechState::Silence, SpeechState::Speech),
        Speaker::Customer
    );
    assert_eq!(
        route_speaker(SpeechState::Speech, SpeechState::Speech),
        Speaker::Both
    );
    assert_eq!(
        route_speaker(SpeechState::Silence, SpeechState::Silence),
        Speaker::Neither
    );
}
