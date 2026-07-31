"""Os detectores de vazamento treino/teste — o lugar mais caro do repositório para um bug.

`audit/` responde à pergunta que decide se um WER publicado vale alguma coisa: *o test set foi
contaminado pelo treino?* Um **falso negativo** aqui não faz nada falhar — ele deixa o número
subir e ninguém descobre. É a falácia § 3 #10 (`PRD.md` § 7.3, invariante), e o projeto já a
declarou como inegociável.

`[MEDIDO]` 2026-07-31: as duas funções puras destes módulos tinham **0 teste** e a cobertura do
domínio era 26,9%. A lógica já estava extraída (`speaker_key`, `path_tokens`, `find_leaks`) —
faltava exercitá-la.

O que estes testes protegem, em ordem de dano:

1. **Falso negativo** (vazamento passa) — o WER publicado fica inflado e a decisão de
   arquitetura sai errada.
2. **Falso positivo** (acusa sem vazamento) — bloqueia um corpus legítimo e, pior, ensina a
   ignorar o detector.
"""
from __future__ import annotations

import pytest

from audit.coraa_speaker_overlap import speaker_key
from audit.tagarela_coraa_leak_check import (
    MIN_TOKEN_LEN,
    find_leaks,
    path_tokens,
    tedx_video_ids,
)

VIDEO_ID = "dQw4w9WgXcQ"  # 11 chars, formato de videoID do YouTube


class TestFindLeaks:
    """O detector cross-corpus TAGARELA(train) × CORAA-test."""

    def test_o_mesmo_video_nos_dois_corpora_e_vazamento(self):
        leaks = find_leaks([f"podcasts/{VIDEO_ID}_trecho01.wav"], {VIDEO_ID})
        assert leaks, "vazamento comprovado passou despercebido"
        assert next(iter(leaks.values())) == {VIDEO_ID}

    def test_corpora_disjuntos_nao_acusam(self):
        assert find_leaks([f"podcasts/{VIDEO_ID}_a.wav"], {"OUTROVIDEO1"}) == {}

    def test_sem_ids_de_referencia_nao_ha_o_que_cruzar(self):
        """Conjunto vazio significa "não sei", e não "está limpo".

        O `main()` traduz dict vazio em exit 0. Se um CSV sem coluna TEDx produzisse ids
        vazios, o detector atestaria ausência de vazamento sem ter olhado nada — por isso o
        caminho vazio existe explicitamente no código e é exercitado aqui.
        """
        assert find_leaks([f"x/{VIDEO_ID}.wav"], set()) == {}

    def test_um_path_pode_casar_mais_de_um_video(self):
        outro = "AbCdEfGhIjK"
        leaks = find_leaks([f"{VIDEO_ID}_e_{outro}.wav"], {VIDEO_ID, outro})
        assert leaks[f"{VIDEO_ID}_e_{outro}.wav"] == {VIDEO_ID, outro}

    def test_todos_os_paths_sao_varridos_nao_so_o_primeiro(self):
        paths = ["limpo_um.wav", "limpo_dois.wav", f"sujo_{VIDEO_ID}.wav"]
        assert len(find_leaks(paths, {VIDEO_ID})) == 1


class TestPathTokens:
    """O limiar de comprimento é o que separa detecção de ruído."""

    @pytest.mark.parametrize("sep", ["/", "-", "_", ".", " "])
    def test_separa_por_todos_os_delimitadores_declarados(self, sep):
        assert VIDEO_ID in path_tokens(f"pasta{sep}{VIDEO_ID}{sep}final")

    def test_token_curto_e_descartado_para_nao_gerar_falso_positivo(self):
        """"de", "sp", números de segmento casariam com qualquer coisa.

        Um detector que acusa demais é abandonado, e aí não detecta nada.
        """
        curtos = path_tokens("de/sp/01/audio.wav")
        assert all(len(t) >= MIN_TOKEN_LEN for t in curtos)

    def test_o_limiar_nao_engole_um_videoid(self):
        """Se `MIN_TOKEN_LEN` subisse acima de 11, o detector pararia de detectar em silêncio."""
        assert MIN_TOKEN_LEN <= len(VIDEO_ID)

    def test_path_vazio_ou_nulo_nao_explode(self):
        assert path_tokens("") == set()
        assert path_tokens(None) == set()


class TestTedxVideoIds:
    def test_extrai_id_removendo_o_sufixo_de_segmento(self, tmp_path):
        csv_ = tmp_path / "meta.csv"
        csv_.write_text(
            "dataset,file_path\n"
            f"TEDx Talks,tedx/{VIDEO_ID}-42.wav\n"
            "ALIP,alip/qualquer-9.wav\n",
            encoding="utf-8",
        )
        ids = tedx_video_ids(str(csv_))
        assert ids == {VIDEO_ID}, "o sufixo -{seg} tem de sair, e só TEDx entra"


class TestSpeakerKey:
    """Cada corpus do CORAA codifica locutor de um jeito — ou não codifica."""

    def test_coral_brasil_usa_o_ultimo_token(self):
        assert speaker_key("C-ORAL-BRASIL I", "x/bfamcv01_falante_A.wav") == ("CORAL", "A")

    def test_nurc_usa_o_diretorio_pai(self):
        assert speaker_key("NURC-Recife", "nurc/INQ-042/trecho.wav") == ("NURC", "INQ-042")

    def test_tedx_usa_o_video_sem_o_sufixo_de_segmento(self):
        assert speaker_key("TEDx Talks", f"tedx/{VIDEO_ID}-7.wav") == ("TEDx", VIDEO_ID)

    @pytest.mark.parametrize("dataset", ["ALIP", "SP2010"])
    def test_corpus_sem_chave_devolve_none_em_vez_de_chave_inventada(self, dataset):
        """`None` é a resposta honesta: o path não codifica locutor.

        Devolver uma chave derivada do nome do arquivo faria cada utterance parecer um
        locutor distinto — e a auditoria concluiria "sem overlap" por construção, que é o
        falso negativo mais caro possível.
        """
        assert speaker_key(dataset, "alip/AC-001.wav") is None

    def test_coral_com_path_curto_demais_nao_inventa_locutor(self):
        assert speaker_key("C-ORAL-BRASIL I", "x/ab.wav") is None
