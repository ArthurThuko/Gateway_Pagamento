"""Regra central nº 3: como saber que a notificação vem do gateway e não de um atacante?"""
import hashlib
import hmac

import pytest

from app.signature import SignatureError, sign_payload, verify_signature

SEGREDO = "whsec_teste"
CORPO = b'{"id":"evt_1","type":"payment_intent.succeeded"}'


def test_assinatura_valida_passa():
    verify_signature(CORPO, sign_payload(CORPO, SEGREDO, timestamp=1000), SEGREDO, now=1000)


def test_formato_identico_ao_do_stripe():
    esperado = hmac.new(SEGREDO.encode(), b"1000." + CORPO, hashlib.sha256).hexdigest()
    assert sign_payload(CORPO, SEGREDO, timestamp=1000) == f"t=1000,v1={esperado}"


def test_segredo_errado_e_rejeitado():
    with pytest.raises(SignatureError):
        verify_signature(CORPO, sign_payload(CORPO, "whsec_do_atacante", timestamp=1000), SEGREDO, now=1000)


def test_corpo_adulterado_e_rejeitado():
    header = sign_payload(CORPO, SEGREDO, timestamp=1000)
    with pytest.raises(SignatureError):
        verify_signature(CORPO.replace(b"succeeded", b"refunded"), header, SEGREDO, now=1000)


def test_replay_antigo_e_rejeitado():
    header = sign_payload(CORPO, SEGREDO, timestamp=1000)
    with pytest.raises(SignatureError):
        verify_signature(CORPO, header, SEGREDO, tolerance_seconds=300, now=1000 + 301)


@pytest.mark.parametrize("header", [None, "", "lixo", "t=abc,v1=ff", "t=1000", "v1=ff"])
def test_cabecalho_ausente_ou_malformado_e_rejeitado(header):
    with pytest.raises(SignatureError):
        verify_signature(CORPO, header, SEGREDO, now=1000)


def test_aceita_varias_assinaturas_v1_durante_rotacao_de_segredo():
    boa = sign_payload(CORPO, SEGREDO, timestamp=1000).split("v1=")[1]
    verify_signature(CORPO, f"t=1000,v1=00ff,v1={boa}", SEGREDO, now=1000)
