"""``tools.pythonExec.maxOutputChars`` è il tetto vero dell'output (TL14, terza revisione).

``create`` passava il valore di config al costruttore, che lo salvava in
``self.max_output_chars``; ma ``execute`` ripiegava sulla costante di classe
``_MAX_OUTPUT`` (10.000), e la descrizione per il modello diceva «10000» fisso.
Alzare il tetto in config non cambiava niente.
"""

from __future__ import annotations

from types import SimpleNamespace

from jenny.agent.tools.python_exec import PythonExecTool
from jenny.config.schema import PythonExecConfig


def _tool(ws, limit: int) -> PythonExecTool:
    return PythonExecTool(
        working_dir=str(ws), workspace=str(ws), max_output_chars=limit,
        restrict_to_workspace=True,
    )


async def test_the_configured_ceiling_is_the_default(tmp_path) -> None:
    out = await _tool(tmp_path, 50_000).execute(code="print('x' * 30000)")
    assert out.count("x") == 30_000, len(out)

    out = await _tool(tmp_path, 2_000).execute(code="print('x' * 30000)")
    assert "chars truncated" in out and out.count("x") == 2_000, len(out)


async def test_an_explicit_argument_still_wins(tmp_path) -> None:
    out = await _tool(tmp_path, 50_000).execute(code="print('x' * 30000)", max_output_chars=1_000)
    assert out.count("x") == 1_000


def test_create_wires_the_config_and_the_description_tells_it(tmp_path) -> None:
    cfg = PythonExecConfig(max_output_chars=25_000)
    ctx = SimpleNamespace(
        config=SimpleNamespace(python_exec=cfg, restrict_to_workspace=True),
        workspace=tmp_path,
    )
    tool = PythonExecTool.create(ctx)
    assert tool.max_output_chars == 25_000
    assert "25000" in tool.description and "10000 chars" not in tool.description
