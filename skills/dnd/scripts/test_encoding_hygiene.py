"""test_encoding_hygiene.py — regression guard for the UTF-8 encoding sweep
(see commit 3b9de36 and its scripts/graph + display/ follow-up).

Windows' cp1252 console/file default crashes or mojibakes campaign text
(em-dashes, curly quotes, combat glyphs) unless every script forces UTF-8.
This scans every .py file in scripts/ and display/ (skipping __pycache__)
for the two defect classes that caused that:

  (a) a runnable script whose import graph never reaches _stdio.py, so
      stdout/stderr never gets reconfigured to UTF-8.
  (b) a bare `open()` call in text mode, or a `.read_text()`/`.write_text()`
      call, missing an explicit `encoding=` keyword.
"""
from __future__ import annotations

import ast
import pathlib

_HERE = pathlib.Path(__file__).resolve().parent
_SCRIPTS_DIR = _HERE
_DISPLAY_DIR = _HERE.parent / "display"


def _iter_py_files():
    for base in (_SCRIPTS_DIR, _DISPLAY_DIR):
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            yield p


def _build_registry():
    """module name -> path, separately for scripts/ (+ scripts/graph/) and display/."""
    scripts_modules = {}
    display_modules = {}
    for p in _SCRIPTS_DIR.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        scripts_modules.setdefault(p.stem, p)
    for p in _DISPLAY_DIR.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        display_modules.setdefault(p.stem, p)
    return scripts_modules, display_modules


def _imported_names(path: pathlib.Path) -> set:
    """All module names this file imports, anywhere in the module (including
    inside try/except and if blocks) — mirrors what actually executes."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _is_runnable(path: pathlib.Path) -> bool:
    """Shebang or __main__ guard — either marks a script meant to be executed
    directly rather than only imported as a library."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("#!"):
        return True
    return '__name__ == "__main__"' in text or "__name__ == '__main__'" in text


def _reaches_stdio(path: pathlib.Path, scripts_modules: dict, display_modules: dict,
                    seen=None) -> bool:
    if seen is None:
        seen = set()
    if path in seen:
        return False
    seen.add(path)
    imported = _imported_names(path)
    if "_stdio" in imported:
        return True
    is_display = _DISPLAY_DIR in path.parents
    candidates = dict(scripts_modules)
    if is_display:
        candidates.update(display_modules)
    for name in imported:
        sibling = candidates.get(name)
        if sibling is not None and sibling != path:
            if _reaches_stdio(sibling, scripts_modules, display_modules, seen):
                return True
    return False


def test_no_missing_stdio_import():
    scripts_modules, display_modules = _build_registry()
    violations = []
    for path in _iter_py_files():
        if path.name in ("_stdio.py",) or path.name.startswith("test_"):
            continue
        if not _is_runnable(path):
            continue
        if not _reaches_stdio(path, scripts_modules, display_modules):
            violations.append(str(path.relative_to(_HERE.parent)))
    assert not violations, (
        "Runnable script(s) missing UTF-8 stdio wiring — add `import _stdio` "
        "per the established pattern (adjust sys.path first if the script "
        "isn't a direct sibling of _stdio.py):\n  " + "\n  ".join(violations)
    )


def _check_open_and_text_calls(path: pathlib.Path):
    violations = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            has_encoding = any(kw.arg == "encoding" for kw in node.keywords)
            if has_encoding:
                continue
            mode = ""
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) \
                    and isinstance(node.args[1].value, str):
                mode = node.args[1].value
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str):
                    mode = kw.value.value
            if "b" in mode:
                continue  # binary mode — encoding doesn't apply
            violations.append((node.lineno, 'open() missing encoding="utf-8"'))
        elif isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
            has_encoding = any(kw.arg == "encoding" for kw in node.keywords)
            if not has_encoding:
                violations.append((node.lineno, f'{func.attr}() missing encoding="utf-8"'))
    return violations


def test_no_missing_encoding():
    all_violations = []
    for path in _iter_py_files():
        for lineno, message in _check_open_and_text_calls(path):
            all_violations.append(f"{path.relative_to(_HERE.parent)}:{lineno}: {message}")
    assert not all_violations, (
        "File I/O missing explicit UTF-8 encoding (Windows cp1252 default "
        "will crash or mojibake on non-ASCII campaign text):\n  "
        + "\n  ".join(all_violations)
    )
