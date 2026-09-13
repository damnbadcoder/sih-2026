import pytest
from app.processing.tlp import TLPLevel, classify_tlp


def test_tlp_red_private_key():
    text = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC..."
    assert classify_tlp(text) == TLPLevel.RED.value


def test_tlp_red_credentials():
    text = "api_key = 'sk_live_9923847293847239847239'"
    assert classify_tlp(text) == TLPLevel.RED.value


def test_tlp_amber_ip_address():
    text = "Target internal server deployed at 192.168.1.45 for testing."
    assert classify_tlp(text) == TLPLevel.AMBER.value


def test_tlp_amber_email():
    text = "Contact investigator at suspect@domain.com for logs."
    assert classify_tlp(text) == TLPLevel.AMBER.value


def test_tlp_clear_generic_text():
    text = "This presentation contains public project documentation."
    assert classify_tlp(text) == TLPLevel.CLEAR.value


def test_tlp_none_or_empty_text():
    assert classify_tlp(None) == TLPLevel.CLEAR.value
    assert classify_tlp("") == TLPLevel.CLEAR.value