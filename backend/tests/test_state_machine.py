from itertools import permutations

import pytest

from app.state_machine import RANK, TRANSITIONS, OrderEvent as E, OrderStatus as S, decide


def aplicar(estado, *eventos):
    for e in eventos:
        estado = decide(estado, e).new_status
    return estado


def test_fluxo_feliz():
    assert aplicar(S.PENDENTE, E.PAGAMENTO_CONFIRMADO, E.PEDIDO_ENVIADO) == S.ENVIADO


def test_recusado_e_nova_tentativa_aprovada():
    assert aplicar(S.PENDENTE, E.PAGAMENTO_RECUSADO) == S.RECUSADO
    assert aplicar(S.RECUSADO, E.PAGAMENTO_CONFIRMADO) == S.PAGO


@pytest.mark.parametrize("estado", list(S))
def test_estornado_e_terminal(estado):
    estornado = aplicar(estado, E.PAGAMENTO_ESTORNADO)
    assert estornado == S.ESTORNADO
    for evento in E:
        assert decide(S.ESTORNADO, evento).applied is False


def test_pago_depois_de_estornado_e_ignorado():
    d = decide(S.ESTORNADO, E.PAGAMENTO_CONFIRMADO)
    assert d.applied is False and d.new_status == S.ESTORNADO


def test_recusado_atrasado_nao_derruba_pedido_pago():
    assert decide(S.PAGO, E.PAGAMENTO_RECUSADO).applied is False


def test_nao_envia_pedido_nao_pago():
    for estado in (S.PENDENTE, S.RECUSADO, S.ESTORNADO):
        assert decide(estado, E.PEDIDO_ENVIADO).applied is False


def test_o_estado_so_avanca():
    for (origem, _), destino in TRANSITIONS.items():
        assert RANK[destino] > RANK[origem]


@pytest.mark.parametrize("ordem", list(permutations([E.PAGAMENTO_CONFIRMADO, E.PAGAMENTO_RECUSADO, E.PAGAMENTO_ESTORNADO])))
def test_qualquer_ordem_chega_no_mesmo_estado_final(ordem):
    assert aplicar(S.PENDENTE, *ordem) == S.ESTORNADO


@pytest.mark.parametrize("ordem", list(permutations([E.PAGAMENTO_CONFIRMADO, E.PAGAMENTO_RECUSADO])))
def test_recusado_e_pago_em_qualquer_ordem_termina_pago(ordem):
    assert aplicar(S.PENDENTE, *ordem) == S.PAGO
