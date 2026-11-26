"""`icefall/utils.py` faz `import k2.version` no topo — o submódulo precisa existir.

O valor declara o que este stub É, para que qualquer log que o imprima não sugira um k2 real.
"""
__version__ = "0.0.0+jvscribe-swoosh-stub"

# `icefall/env.py` lê estes quatro para o log de ambiente. Ausentes, o log quebra no meio de
# uma corrida — e o valor declara honestamente que não há k2 real por trás.
__build_type__ = "stub"
__git_sha1__ = "n/a"
__git_date__ = "n/a"
