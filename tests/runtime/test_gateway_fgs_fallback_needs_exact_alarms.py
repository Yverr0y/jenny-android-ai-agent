"""Il ripiego che rialza il gateway dopo un avvio rifiutato esige sveglie esatte.

Da Android 12 un FGS non parte da background, salvo un'allowlist temporanea
che lo permetta. ``GatewayStarter.ensureUp`` a un avvio rifiutato armava una
sveglia per «rientrare dall'allowlist»; ma senza ``SCHEDULE_EXACT_ALARM``
``PowerBridge.scheduleWake`` ripiega su ``setAndAllowWhileIdle``, e
``AlarmManagerService.setImpl`` dà a quella ``mOptsWithoutFgs`` —
``TEMPORARY_ALLOWLIST_TYPE_FOREGROUND_SERVICE_NOT_ALLOWED`` (AOSP,
``android14-release`` e ``main``). La sveglia rientrava in un contesto che
rifiutava l'avvio come il primo: niente rialzava il gateway, e i KDoc dicevano
il contrario (voce AN2 della terza revisione; il Titan 2 lo maschera perché
l'app è esente dall'ottimizzazione batteria, e lì l'avvio non è mai rifiutato).

``setAlarmClock`` non è un'alternativa (è esatta, stesso permesso: verificato
sul telefono il 09/08, v. ``AlarmClockFallback``), né un job espresso di
WorkManager (``JobServiceContext`` lo lega senza allowlist per il FGS).
"""

from __future__ import annotations

from support.kotlin_source import block_after, function_body, read_code, read_comments


def test_the_recovery_alarm_is_armed_only_with_exact_alarms() -> None:
    body = function_body(read_code("GatewayStarter"), "ensureUp")
    catch = block_after(body, r"catch \(e: Exception\)")
    fallback = block_after(catch, r"if \(alarmFallback\)")
    guard = fallback.index("if (PowerBridge.canScheduleExactAlarms(appContext))")
    assert guard < fallback.index("PowerBridge.scheduleWake("), (
        "un'inesatta non concede il FGS: armarla è un tentativo che non può riuscire"
    )
    assert "else" in fallback[fallback.index("PowerBridge.scheduleWake(") :]


def test_the_kdocs_no_longer_promise_an_fgs_from_any_alarm() -> None:
    """Il difetto viveva nei commenti: si verificano i commenti."""
    assert "mOptsWithoutFgs" in read_comments("GatewayStarter")
    assert "Solo una sveglia esatta" in read_comments("WakeReceiver")
    assert "mOptsWithoutFgs" in read_comments("PowerBridge")
