"""Un giro del timer con piu' job dovuti: cosa arriva su disco, e quando.

``_on_timer`` calcola i job dovuti una volta sola e poi li esegue uno dopo
l'altro, e ogni esecuzione e' un turno d'agente che dura secondi o minuti. In
mezzo succedono cose: l'officina mette in pausa o elimina un job, lo
spegnimento ferma il servizio, Android uccide il processo.
"""

from __future__ import annotations

import asyncio
import functools
import json
import time
from pathlib import Path

from support.aio import wait_until

from jenny.cron.service import CronService
from jenny.cron.types import CronSchedule

_HOUR = 3_600_000
_wait_until = functools.partial(wait_until, timeout=2.0)


def _bound() -> dict[str, str]:
    return {
        "session_key": "websocket:chat-1",
        "origin_channel": "websocket",
        "origin_chat_id": "chat-1",
    }


def _now() -> int:
    return int(time.time() * 1000)


def _make_due(service: CronService, *job_ids: str) -> None:
    """Rende dovuti *job_ids* adesso e fa partire un giro del timer."""
    for job in service._store.jobs:
        if job.id in job_ids:
            job.state.next_run_at_ms = _now() - 1000
            if job.schedule.kind == "at":
                # Anche l'orario del promemoria: al riavvio un ``at`` si
                # riprogramma dal suo ``at_ms`` (v. ``_recompute_next_runs``).
                job.schedule.at_ms = job.state.next_run_at_ms
    service._save_store()
    service._arm_timer()


def _disk_jobs(path: Path) -> dict[str, dict]:
    return {j["name"]: j for j in json.loads(path.read_text(encoding="utf-8"))["jobs"]}


# -- CF3: lo stato di ogni job arriva su disco appena il job finisce -----------


async def test_a_job_that_ran_is_on_disk_before_the_next_one_starts(tmp_path) -> None:
    """Un kill durante il job B faceva ripartire A: lo store si salvava a fine giro."""
    path = tmp_path / "cron" / "jobs.json"
    disk_while_b_runs: dict[str, dict] = {}

    async def on_job(job):
        if job.name == "B":
            disk_while_b_runs.update(_disk_jobs(path))

    service = CronService(path, on_job=on_job, max_sleep_ms=100)
    await service.start()
    try:
        a = service.add_job("A", CronSchedule(kind="at", at_ms=_now() + _HOUR), "remind", **_bound())
        b = service.add_job("B", CronSchedule(kind="every", every_ms=_HOUR), "b", **_bound())
        _make_due(service, a.id, b.id)
        await _wait_until(lambda: "B" in disk_while_b_runs)
    finally:
        service.stop()

    reminder = disk_while_b_runs["A"]
    assert reminder["enabled"] is False
    assert reminder["state"]["nextRunAtMs"] is None
    assert reminder["state"]["lastStatus"] == "ok"


async def test_a_delivered_reminder_does_not_run_again_after_a_kill(tmp_path) -> None:
    """Il riavvio parte da quello che c'era su disco al momento del kill."""
    path = tmp_path / "cron" / "jobs.json"
    at_kill = tmp_path / "at-kill.json"
    ran: list[str] = []

    async def on_job(job):
        ran.append(job.name)
        if job.name == "B":
            at_kill.write_bytes(path.read_bytes())

    service = CronService(path, on_job=on_job, max_sleep_ms=100)
    await service.start()
    try:
        a = service.add_job("A", CronSchedule(kind="at", at_ms=_now() + _HOUR), "remind", **_bound())
        b = service.add_job("B", CronSchedule(kind="every", every_ms=_HOUR), "b", **_bound())
        _make_due(service, a.id, b.id)
        await _wait_until(lambda: at_kill.exists())
    finally:
        service.stop()

    path.write_bytes(at_kill.read_bytes())
    ran.clear()
    restarted = CronService(path, on_job=on_job, max_sleep_ms=100)
    await restarted.start()
    try:
        await asyncio.sleep(0.3)
    finally:
        restarted.stop()
    assert "A" not in ran


# -- RC1: prima di ogni job si guarda lo store di adesso, non quello d'inizio giro


async def _second_job_changed_while_first_runs(tmp_path, change) -> list[str]:
    path = tmp_path / "cron" / "jobs.json"
    started = asyncio.Event()
    gate = asyncio.Event()
    ran: list[str] = []

    async def on_job(job):
        ran.append(job.name)
        if job.name == "A":
            started.set()
            await gate.wait()

    service = CronService(path, on_job=on_job, max_sleep_ms=100)
    await service.start()
    try:
        a = service.add_job("A", CronSchedule(kind="every", every_ms=_HOUR), "a", **_bound())
        b = service.add_job("B", CronSchedule(kind="every", every_ms=_HOUR), "b", **_bound())
        _make_due(service, a.id, b.id)
        await asyncio.wait_for(started.wait(), 2)
        change(service, b.id)
        gate.set()
        await _wait_until(lambda: not service._timer_active)
    finally:
        service.stop()
    return ran


async def test_a_job_paused_while_the_previous_one_runs_does_not_run(tmp_path) -> None:
    def pause(service, job_id):
        assert service.set_paused(job_id, True) == "paused"

    assert await _second_job_changed_while_first_runs(tmp_path, pause) == ["A"]


async def test_a_job_removed_while_the_previous_one_runs_does_not_run(tmp_path) -> None:
    def remove(service, job_id):
        assert service.remove_job(job_id) == "removed"

    assert await _second_job_changed_while_first_runs(tmp_path, remove) == ["A"]


async def test_a_job_paused_and_resumed_meanwhile_waits_for_its_new_time(tmp_path) -> None:
    """Ripreso vuol dire «da adesso»: la scadenza vecchia non vale piu'."""
    def pause_and_resume(service, job_id):
        service.set_paused(job_id, True)
        assert service.set_paused(job_id, False) == "resumed"

    assert await _second_job_changed_while_first_runs(tmp_path, pause_and_resume) == ["A"]
