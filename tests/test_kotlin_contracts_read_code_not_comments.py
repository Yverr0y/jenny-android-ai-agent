"""Nessun contratto Kotlin legge il ``.kt`` grezzo.

I test che fissano regole sui sorgenti Android (il Kotlin in CI non gira)
cercano sottostringhe. Letto grezzo, il file le offre anche nei commenti: la
revisione terza (TD12) ha commentato il cancello di ``JennyBrowserBridge.kt``,
ha messo ``setSupportZoom(true)`` sotto un commento che diceva ``false``, e i
test sono rimasti verdi. Era già la regressione di una voce precedente: i test
nuovi erano tornati a ``read_text``.

Qui si guarda l'AST di ogni test: una chiamata ``.read_text(...)`` il cui
oggetto nomina un ``.kt`` — direttamente, tramite una costante di modulo o di
classe, o in una comprensione su ``rglob("*.kt")`` — è un difetto. La lettura
giusta passa da ``support.kotlin_source`` (``read_source``/``read_code``, o
``strip_comments``/``code_only`` sul testo). Unica eccezione dichiarata: il
test che controlla i KDoc, che i commenti li deve leggere.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parent

# Leggono i commenti apposta: il loro oggetto *è* il KDoc.
_READS_COMMENTS_ON_PURPOSE = {"test_kotlin_kdoc_is_attached.py"}
_CLEANERS = {"code_only", "strip_comments"}


def _names_bound_to_kotlin(tree: ast.Module) -> set[str]:
    """Nomi (di modulo o di classe) assegnati a un'espressione che nomina un ``.kt``."""
    names: set[str] = set()
    scopes = [tree.body] + [n.body for n in tree.body if isinstance(n, ast.ClassDef)]
    for body in scopes:
        for node in body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                value = ast.unparse(node.value)
                if ".kt" in value and ".kts" not in value:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    names.update(ast.unparse(t) for t in targets)
    return names


def _raw_kotlin_reads(path: Path, base: Path = TESTS) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound = _names_bound_to_kotlin(tree)
    offenders: list[str] = []

    # Una lettura passata subito a code_only/strip_comments è già quella giusta.
    cleaned: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) in _CLEANERS:
            cleaned.update(id(a) for a in node.args)

    comprehension_iters: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            iters = " ".join(ast.unparse(g.iter) for g in node.generators)
            for child in ast.walk(node.elt):
                comprehension_iters[id(child)] = iters

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "read_text"
            and id(node) not in cleaned
        ):
            continue
        receiver = ast.unparse(node.func.value)
        context = receiver + " " + comprehension_iters.get(id(node), "")
        bare = receiver.removeprefix("self.").removeprefix("cls.")
        if ".kt" in context or receiver in bound or bare in bound:
            if ".kts" in context:  # build.gradle.kts non è un contratto sul Kotlin dell'app
                continue
            offenders.append(f"{path.relative_to(base)}:{node.lineno} {receiver}.read_text")
    return offenders


def test_no_kotlin_contract_reads_the_raw_source() -> None:
    offenders: list[str] = []
    for path in sorted(TESTS.rglob("test_*.py")):
        if path.name in _READS_COMMENTS_ON_PURPOSE or path == Path(__file__).resolve():
            continue
        offenders.extend(_raw_kotlin_reads(path))
    assert not offenders, (
        "un contratto Kotlin legge il sorgente grezzo: un commento lo soddisfa. "
        "Usa support.kotlin_source.read_source/read_code:\n" + "\n".join(offenders)
    )


def test_the_detector_sees_the_three_shapes(tmp_path: Path) -> None:
    """Il rilevatore stesso: costante, percorso diretto, comprensione su rglob."""
    sample = tmp_path / "test_sample.py"
    sample.write_text(
        "from pathlib import Path\n"
        'MAIN = Path("x") / "MainActivity.kt"\n'
        "class T:\n"
        '    FLIGHT = Path("FloatingFlight.kt")\n'
        "    def a(self):\n"
        '        return self.FLIGHT.read_text(encoding="utf-8")\n'
        "def b():\n"
        '    return MAIN.read_text("utf-8")\n'
        "def c(root):\n"
        '    return (root / "X.kt").read_text()\n'
        "def d(root):\n"
        '    return [p.read_text() for p in root.rglob("*.kt")]\n'
        "def e(root):\n"
        '    return (root / "build.gradle.kts").read_text()\n'
        "def f(root):\n"
        '    return code_only((root / "X.kt").read_text())\n',
        encoding="utf-8",
    )
    found = _raw_kotlin_reads(sample, tmp_path)
    assert sorted(int(f.split(":")[1].split()[0]) for f in found) == [6, 8, 10, 12], found
