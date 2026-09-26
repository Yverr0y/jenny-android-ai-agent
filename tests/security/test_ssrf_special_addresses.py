"""Indirizzi che nessuna delle tre policy SSRF deve lasciar passare (CF5, terza revisione).

``::`` (non specificato) su Linux raggiunge l'host stesso, come ``0.0.0.0``: con
``::1`` bloccato e ``::`` no, un servizio in ascolto sul telefono era
raggiungibile. ``::127.0.0.1`` è la forma IPv4-compatibile (deprecata) del
loopback, che ``_normalize_addr`` non riconosce perché non è una IPv4-mapped.
Multicast e broadcast non sono mai un server: né una pagina, né l'app server di
un utente, né un suo host SSH. Tutti letterali: nessuna risoluzione DNS vera.
"""

from __future__ import annotations

import pytest

from jenny.security.network import (
    validate_app_server_target,
    validate_ssh_target,
    validate_url_target,
)

_SPECIAL = [
    "::",
    "::127.0.0.1",
    "::10.0.0.1",
    "224.0.0.1",
    "239.255.255.250",
    "ff02::1",
    "255.255.255.255",
]


def _url(host: str) -> str:
    return f"http://[{host}]/" if ":" in host else f"http://{host}/"


@pytest.mark.parametrize("host", _SPECIAL)
def test_web_fetch_refuses_it(host: str) -> None:
    ok, err = validate_url_target(_url(host))
    assert not ok, f"{host} è passato per validate_url_target"
    assert "Blocked" in err, err


@pytest.mark.parametrize("host", [h for h in _SPECIAL if h != "::10.0.0.1"])
def test_an_app_server_refuses_it(host: str) -> None:
    ok, err = validate_app_server_target(_url(host))
    assert not ok, f"{host} è passato per validate_app_server_target"


@pytest.mark.parametrize("host", [h for h in _SPECIAL if h != "::10.0.0.1"])
def test_ssh_refuses_it(host: str) -> None:
    ok, err = validate_ssh_target(host)
    assert not ok, f"{host} è passato per validate_ssh_target"


def test_the_unspecified_address_is_the_phone_itself_for_ssh_even_whitelisted() -> None:
    """Come il loopback: il pavimento dell'SSH non cede alla whitelist globale."""
    from jenny.security import network

    network.configure_ssrf_whitelist(["::/0", "0.0.0.0/0"])
    try:
        assert not validate_ssh_target("::")[0]
        assert not validate_ssh_target("0.0.0.0")[0]
    finally:
        network.configure_ssrf_whitelist([])


@pytest.mark.parametrize("host", ["8.8.8.8", "2001:4860:4860::8888"])
def test_public_addresses_still_pass(host: str) -> None:
    assert validate_url_target(_url(host)) == (True, "")
    assert validate_ssh_target(host) == (True, "")
