"""Ogni sessione ha il suo namespace ``python_exec`` (TL8, terza revisione).

Il tool è uno per processo e il suo ``PythonNamespace`` teneva un solo dizionario
di globali per tutte le sessioni: una variabile assegnata dentro un quaderno si
leggeva dalla chat personale, e un ``def read_file(...)`` scritto in una sessione
sostituiva il builtin registrato per tutte, fino al riavvio.

La chiave è la session key del turno (``RequestContext.session_key``). Dentro la
stessa sessione lo stato resta, com'è sempre stato: è ciò che rende utile
``python_exec`` da una chiamata all'altra. Si passa dal tool vero, sia dal ramo
one-shot (executor) sia dal ramo ``yield_time_ms`` (thread di sessione).
"""

from __future__ import annotations

from jenny.agent.tools.context import (
    _CURRENT_REQUEST_CONTEXT,
    RequestContext,
    bind_request_context,
)
from jenny.agent.tools.exec_session import ExecSessionManager
from jenny.agent.tools.python_exec import PythonExecTool
from jenny.agent.tools.python_exec_builtins import _register_builtin_functions
from jenny.config.schema import PythonExecConfig


def _tool(ws, manager: ExecSessionManager) -> PythonExecTool:
    cfg = PythonExecConfig()
    tool = PythonExecTool(
        working_dir=str(ws),
        timeout=30,
        allowed_modules=cfg.allowed_modules,
        blocked_modules=cfg.blocked_modules,
        restrict_to_workspace=True,
        workspace=str(ws),
        session_manager=manager,
    )
    _register_builtin_functions(tool.namespace, workspace=str(ws), restrict_to_workspace=True)
    return tool


async def _run(key: str, tool: PythonExecTool, **kwargs) -> str:
    token = bind_request_context(RequestContext(channel="websocket", chat_id="c", session_key=key))
    try:
        return await tool.execute(**kwargs)
    finally:
        _CURRENT_REQUEST_CONTEXT.reset(token)


async def test_a_notebook_variable_is_not_visible_from_the_personal_chat(tmp_path) -> None:
    ws = tmp_path.resolve()
    manager = ExecSessionManager()
    tool = _tool(ws, manager)
    try:
        await _run("project:acme", tool, code="client_notes = 'segreto del quaderno'")
        # Stessa sessione: lo stato resta.
        assert "segreto del quaderno" in await _run("project:acme", tool, code="client_notes")

        out = await _run("unified:default", tool, code="client_notes")
        assert "segreto" not in out, out
        assert "NameError" in out, out

        # Anche dal ramo sessione (thread grezzo).
        out = await _run("unified:default", tool, code="print(client_notes)", yield_time_ms=2000)
        assert "segreto" not in out and "NameError" in out, out
        out = await _run("project:acme", tool, code="print(client_notes)", yield_time_ms=2000)
        assert "segreto del quaderno" in out, out
    finally:
        manager.shutdown()


async def test_redefining_a_builtin_breaks_only_its_own_session(tmp_path) -> None:
    ws = tmp_path.resolve()
    (ws / "SOUL.md").write_text("io\n", encoding="utf-8")
    manager = ExecSessionManager()
    tool = _tool(ws, manager)
    try:
        await _run("project:acme", tool, code="def read_file(p):\n    return 'shadowed'")
        assert "shadowed" in await _run("project:acme", tool, function="read_file", args=["SOUL.md"])

        out = await _run("unified:default", tool, function="read_file", args=["SOUL.md"])
        assert "shadowed" not in out and "io" in out, out
        out = await _run("unified:default", tool, code="read_file('SOUL.md')")
        assert "shadowed" not in out and "io" in out, out
    finally:
        manager.shutdown()


async def test_a_function_registered_later_reaches_every_session(tmp_path) -> None:
    ws = tmp_path.resolve()
    manager = ExecSessionManager()
    tool = _tool(ws, manager)
    try:
        await _run("project:acme", tool, code="x = 1")
        tool.namespace.register_function("late_helper", lambda: "arrivato")
        assert "arrivato" in await _run("project:acme", tool, code="late_helper()")
        assert "arrivato" in await _run("unified:default", tool, code="late_helper()")
    finally:
        manager.shutdown()
