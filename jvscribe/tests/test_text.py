

class TestExpansaoDeNumeros:
    """A régua que compara forma FALADA com forma FALADA.

    Defeito medido em 2026-07-31: 187 das 919 referências do FLEURS trazem DÍGITO
    (`20 anos`), o modelo emite forma falada (`vinte anos`), e a régua canônica preserva
    dígito e não faz ITN — então conta acerto como erro. Custo medido: 2,38 p.p. do WER
    publicado, IC95 [1,97; 2,81].
    """

    def test_expande_cardinal(self):
        from text import expandir_numeros
        assert expandir_numeros("na casa dos 20 anos") == "na casa dos vinte anos"

    def test_expande_varios_no_mesmo_texto(self):
        from text import expandir_numeros
        assert expandir_numeros("notas de 5 e 100 dolares") == "notas de cinco e cem dolares"

    def test_texto_sem_digito_passa_intacto(self):
        from text import expandir_numeros
        t = "mandibulas cravejadas com dentes afiados"
        assert expandir_numeros(t) == t

    def test_e_idempotente(self):
        from text import expandir_numeros
        uma = expandir_numeros("dedicar 10 agentes")
        assert expandir_numeros(uma) == uma, "aplicar duas vezes não pode mudar o resultado"

    def test_nao_altera_a_regua_publicada(self):
        """`normalize_for_wer_compare` NÃO pode mudar — 12 chamadores e toda a série histórica.

        A expansão é uma régua ADICIONAL, publicada ao lado, nunca no lugar.
        """
        from text import normalize_for_wer_compare
        assert normalize_for_wer_compare("na casa dos 20 anos") == "na casa dos 20 anos"

    def test_numero_grande_demais_nao_derruba_o_processo(self):
        """Regressão: a Wikipédia tem inteiros de 20 dígitos e `num2words` levanta OverflowError.

        Encontrado ao construir o corpus do LM em 2026-08-01: o processo morreu com
        `abs(46250370042016100256) must be less than 1000000000000000000`. Capturar só
        ValueError/NotImplementedError deixava passar. Um número que a lib recusa volta como
        veio — apagá-lo falsearia o texto.
        """
        from text import expandir_numeros
        assert expandir_numeros("id 46250370042016100256 fim") == "id 46250370042016100256 fim"
