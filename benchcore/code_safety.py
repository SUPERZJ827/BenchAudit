from __future__ import annotations

import ast


class UnsafeGeneratedCode(ValueError):
    pass


BANNED_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Raise,
)

BANNED_NAMES = {
    "__import__", "breakpoint", "compile", "delattr", "dir", "eval", "exec",
    "getattr", "globals", "help", "input", "locals", "memoryview", "open",
    "setattr", "vars",
}

BANNED_ATTRIBUTES = {
    "system", "popen", "spawn", "fork", "connect", "bind", "listen", "accept",
    "read_pickle", "read_sql", "read_html", "read_xml", "load", "loads", "dump",
    "dumps", "save", "savez", "to_pickle", "to_csv", "to_excel", "to_json",
    "to_sql", "to_xml", "to_parquet", "to_feather", "to_hdf", "to_clipboard",
}


def validate_generated_table_code(code: str, *, max_nodes: int = 500) -> ast.Module:
    """Validate narrow dataframe-computation code before trusted local execution.

    This is defense in depth, not an OS sandbox. Callers must still use an
    isolated execution backend for untrusted benchmark content.
    """
    if not isinstance(code, str) or not code.strip():
        raise UnsafeGeneratedCode("generated code is empty")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise UnsafeGeneratedCode(f"generated code has invalid syntax: {exc.msg}") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > max_nodes:
        raise UnsafeGeneratedCode(f"generated code exceeds AST node limit ({len(nodes)} > {max_nodes})")
    for node in nodes:
        if isinstance(node, BANNED_NODES):
            raise UnsafeGeneratedCode(f"generated code contains banned syntax: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id.startswith("__") or node.id in BANNED_NAMES:
                raise UnsafeGeneratedCode(f"generated code references banned name: {node.id}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in BANNED_ATTRIBUTES:
                raise UnsafeGeneratedCode(f"generated code references banned attribute: {node.attr}")
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            text = node.value.decode("utf-8", errors="ignore") if isinstance(node.value, bytes) else node.value
            if "__import__" in text or "file://" in text:
                raise UnsafeGeneratedCode("generated code contains a suspicious literal")
    if not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
        for node in nodes
    ):
        raise UnsafeGeneratedCode("generated code must print its result")
    return tree
