"""O stub de `k2` tem de reproduzir a Swoosh do icefall — não uma ativação parecida.

O `k2` desta máquina foi compilado contra PyTorch 1.13.1+cu117 e o ambiente roda 2.13.0+cpu;
importá-lo levanta `ImportError` de ABI, e sem ele o `scaling.py` do icefall não importa —
logo o smoke de finetune não roda. O stub existe para essa lacuna.

O risco de um stub de ativação é específico e feio: uma fórmula ligeiramente diferente **não
falha**. O modelo carrega, a loss desce, e o número que sai é sobre outra rede. Mesma classe do
vocabulário trocado — saída plausível e errada.

Por isso os testes abaixo comparam contra duas referências independentes:

1. **Valores fechados**, derivados da definição publicada no `scaling.py` do icefall.
2. **O ramo JIT do icefall real**, quando o clone está disponível — o mesmo código que o
   TorchScript usa quando não pode chamar o k2 compilado.

E a derivada é conferida contra o **autograd**, não contra si mesma.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "finetune" / "k2stub"))
import k2  # noqa: E402

X = torch.tensor([-8.0, -2.0, -0.5, 0.0, 0.5, 1.0, 4.0, 12.0])


def test_swoosh_r_passa_exatamente_pela_origem():
    """Propriedade de desenho da SwooshR: `f(0) = 0`.

    Uma constante errada no lugar de `0.313261687` desloca a curva inteira e ainda assim
    treina — este é o teste que pega isso com um único ponto.
    """
    assert k2.swoosh_r(torch.tensor([0.0])).item() == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    "fn, offset, const",
    [(k2.swoosh_l, 4.0, 0.035), (k2.swoosh_r, 1.0, 0.313261687)],
)
def test_bate_com_a_definicao_publicada(fn, offset, const):
    esperado = torch.logaddexp(torch.tensor(0.0), X - offset) - 0.08 * X - const
    assert torch.allclose(fn(X), esperado, atol=1e-6)


@pytest.mark.parametrize("nome", ["swoosh_l", "swoosh_r"])
def test_forward_e_o_mesmo_da_versao_com_gradiente(nome):
    """No k2 real `*_forward` é o kernel sem gradiente; aqui os dois caminhos são o mesmo.

    `scaling.py` indexa esses nomes num dict por string — um nome faltando vira `KeyError` no
    meio do backward, longe da causa.
    """
    assert torch.allclose(getattr(k2, nome)(X), getattr(k2, f"{nome}_forward")(X))


@pytest.mark.parametrize(
    "fn_deriv, fn", [(k2.swoosh_l_forward_and_deriv, k2.swoosh_l),
                     (k2.swoosh_r_forward_and_deriv, k2.swoosh_r)]
)
def test_derivada_confere_com_o_autograd(fn_deriv, fn):
    """A derivada é verificada contra o PyTorch, não contra a própria fórmula.

    Derivar à mão e testar contra a mesma conta à mão prova que ela é consistente consigo —
    não que esteja certa.
    """
    x = X.clone().requires_grad_(True)
    fn(x).sum().backward()
    _, d = fn_deriv(X)
    assert torch.allclose(d, x.grad, atol=1e-6)


def test_confere_contra_o_ramo_jit_do_icefall_real():
    """A referência mais forte: o próprio `scaling.py` do clone, se ele existir aqui."""
    zip_dir = Path.home() / "workspace/icefall-f84270c/egs/commonvoice/ASR/zipformer"
    if not (zip_dir / "scaling.py").exists():
        pytest.skip("clone do icefall na revisão pinada indisponível nesta máquina")

    sys.path.insert(0, str(zip_dir))
    import scaling  # o import só funciona porque o stub já está no path

    for modulo, fn in ((scaling.SwooshL(), k2.swoosh_l), (scaling.SwooshR(), k2.swoosh_r)):
        with torch.jit.optimized_execution(False):
            referencia = torch.jit.script(modulo)(X)
        assert torch.allclose(referencia, fn(X), atol=1e-6), (
            f"{type(modulo).__name__} do stub diverge do icefall real"
        )


class TestNomesNaoImplementados:
    """O stub resolve qualquer nome de k2 — mas usá-lo levanta."""

    def test_nome_desconhecido_resolve_para_o_marcador(self):
        """Anotações como `word_table: k2.SymbolTable = None` são avaliadas na DEFINIÇÃO.

        Caçar os nomes um a um era tentativa-e-erro: cada import do icefall revelava o
        próximo (`Fsa`, `RaggedTensor`, `SymbolTable`, …), sempre como `AttributeError` numa
        assinatura que ninguém chama. PEP 562 resolve todos de uma vez.
        """
        assert k2.SymbolTable is not None
        assert k2.Fsa is k2.RaggedTensor is k2.QualquerCoisaNova

    def test_construir_um_nome_nao_implementado_levanta(self):
        """Devolver algo inócuo deixaria uma decodificação por grafo rodar sobre estrutura
        falsa e produzir hipóteses plausíveis e erradas."""
        with pytest.raises(NotImplementedError, match="APENAS a ativação Swoosh"):
            k2.Fsa()

    def test_dunder_continua_levantando_attribute_error(self):
        """Senão `copy`, `pickle` e o próprio import machinery se confundem com o marcador."""
        with pytest.raises(AttributeError):
            _ = k2.__algo_magico__

    def test_a_versao_declara_que_e_stub(self):
        """Um log que imprima a versão não pode sugerir um k2 real por trás."""
        import k2.version

        assert "stub" in k2.version.__version__
        assert k2.version.__build_type__ == "stub"
