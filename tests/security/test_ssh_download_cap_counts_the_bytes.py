"""Il tetto di ``ssh_transfer direction=down`` vale per i byte scritti davvero.

``SshBridge.get`` confrontava ``maxBytes`` con la dimensione che il server
dichiara (``stat``) e poi scaricava senza contare: un file che cresce durante
il trasferimento, o un server che mente sulla dimensione, scriveva sul telefono
oltre il tetto (voce AN16 della terza revisione). Ora lo stream conta, si
interrompe oltre il tetto, e il download finisce su un ``.part`` rinominato
solo a trasferimento completo, così un'interruzione non lascia un file tronco.
"""

from __future__ import annotations

from support.kotlin_source import block_after, block_at, function_body, read_code


def _get_body() -> str:
    return function_body(read_code("SshBridge"), "get")


def test_the_stat_check_still_refuses_before_transferring() -> None:
    body = _get_body()
    assert "sftp.stat(remote).size" in body
    assert body.index("size > maxBytes") < body.index("sftp.get(")


def test_the_download_goes_through_a_counting_stream() -> None:
    body = _get_body()
    assert "CappedOutputStream(part.outputStream(), maxBytes)" in body
    assert "sftp.get(remote, it)" in body, "il download deve scrivere nello stream che conta"
    assert "sftp.get(remote, local)" not in body and "sftp.get(remote, target" not in body


def test_the_counting_stream_stops_past_the_limit() -> None:
    stream = block_after(read_code("SshBridge"), r"private class CappedOutputStream\(")
    admit = block_after(stream, r"private fun admit\(")
    assert "count + n > limit" in admit
    assert "throw IOException(" in admit
    # Entrambe le write passano dal contatore prima di toccare il file.
    for sig in (r"override fun write\(b: Int\)", r"override fun write\(b: ByteArray"):
        write = block_after(stream, sig)
        assert write.index("admit(") < write.index("inner.write(")


def test_an_interrupted_download_leaves_no_partial_file() -> None:
    body = _get_body()
    assert "part.renameTo(target)" in body
    catch = block_after(body, r"catch \(e: Throwable\)")
    assert "part.delete()" in catch
    assert "out.overflowed" in catch, "il motivo si legge dal contatore, non dal messaggio di jsch"


def test_the_reported_size_is_what_was_written() -> None:
    """I byte riportati a Python sono quelli contati, non quelli dichiarati."""
    body = _get_body()
    sftp_block = block_at(body, body.index("withSftp(req) {"))
    last = sftp_block.rstrip("}").rstrip().rsplit("\n", 1)[-1].strip()
    assert last == "out.count"
