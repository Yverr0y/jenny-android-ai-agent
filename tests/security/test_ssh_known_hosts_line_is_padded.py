"""La riga di known_hosts scritta dopo la sonda è base64 **con** padding.

``SshBridge.probeHostKey`` restituisce la riga che Python appende a
known_hosts. Fino al 26/09/2026 la chiave era codificata con
``Base64.NO_PADDING``: il blob ed25519 (51 byte) non ha padding e tutto
sembrava funzionare, ma quelli ECDSA (104 byte) e RSA≥3072 sì, e jsch rifiuta
allora l'**intero** file (``fromBase64: invalid base64 data``) — anche gli host
già pinnati smettono di connettersi. Provato con jsch 2.28.6, la versione del
``build.gradle.kts`` (voce AN1 della terza revisione).

L'impronta ``SHA256:`` resta senza padding, com'è in ``ssh-keygen -l``. E i
file già scritti male si leggono riparati: il pin fatto prima della correzione
torna valido senza rifarlo.
"""

from __future__ import annotations

import re

from support.kotlin_source import function_body, read_source


def _src() -> str:
    return read_source("SshBridge")


def _expression_body(name: str) -> str:
    """Il corpo di una funzione a espressione (``fun f(x): T = ...``)."""
    m = re.search(rf"fun {name}\([^)]*\): \w+ =\s*([^\n]+)", _src())
    assert m, f"{name} non trovata (o non è più una funzione a espressione)"
    return m.group(1)


def test_the_known_hosts_line_keeps_the_padding() -> None:
    probe = function_body(_src(), "probeHostKey")
    line = re.search(r'\.put\("line",[^\n]*', probe)
    assert line, "la riga di known_hosts non si costruisce più in probeHostKey"
    assert "knownHostsBase64(blob)" in line.group(0)
    encoder = _expression_body("knownHostsBase64")
    assert "Base64.NO_WRAP" in encoder
    assert "NO_PADDING" not in encoder, "senza padding jsch rifiuta l'intero file"


def test_the_fingerprint_stays_unpadded() -> None:
    probe = function_body(_src(), "probeHostKey")
    fingerprint = probe.split('"fingerprint"', 1)[1].split('"line"', 1)[0]
    assert "fingerprintBase64(MessageDigest" in fingerprint
    assert "NO_PADDING" in _expression_body("fingerprintBase64")


def test_no_host_key_is_encoded_without_padding_elsewhere() -> None:
    """Un solo punto senza padding, l'impronta: un terzo codificatore che lo
    togliesse riaprirebbe il difetto da un'altra parte."""
    src = _src()
    assert src.count("NO_PADDING") == 1


def test_an_old_unpadded_file_is_read_repaired() -> None:
    session = function_body(_src(), "openSession")
    assert "jsch.setKnownHosts(repaddedKnownHosts(File(knownHosts)))" in session
    assert "setKnownHosts(knownHosts)" not in session, "il percorso grezzo salta la riparazione"
    repair = function_body(_src(), "repaddedKnownHosts")
    # Resto 1 non è base64: si lascia a jsch; resto 2 o 3 manca uno o due '='.
    assert "missing !in 1..2" in repair
    assert '"=".repeat(missing)' in repair
