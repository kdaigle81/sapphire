# core/code_validator.py
# AST validation for untrusted Python code (toolmaker + unsigned plugins in managed mode)

import ast
import os
import logging

logger = logging.getLogger(__name__)

# Always blocked — dangerous operations regardless of mode
BLOCKED_IMPORTS = {
    'subprocess', 'shutil', 'ctypes', 'multiprocessing',
    'socket', 'signal', 'importlib',
}

BLOCKED_CALLS = {
    'eval', 'exec', '__import__', 'compile',
    'globals', 'locals', 'getattr', 'setattr', 'delattr', 'open',
}

BLOCKED_ATTRS = {
    ('os', 'system'), ('os', 'popen'), ('os', 'exec'), ('os', 'execv'),
    ('os', 'execvp'), ('os', 'execvpe'), ('os', 'spawn'), ('os', 'spawnl'),
    ('os', 'remove'), ('os', 'unlink'), ('os', 'rmdir'), ('os', 'removedirs'),
    ('os', 'rename'), ('os', 'kill'), ('os', 'environ'),
}

# Additional blocks in managed/Docker mode
MANAGED_BLOCKED_IMPORTS = {'pathlib', 'io', 'tempfile', 'glob'}

MANAGED_BLOCKED_ATTRS = {
    ('os', 'getenv'), ('os', 'listdir'), ('os', 'scandir'), ('os', 'walk'),
    ('os', 'path'), ('os', 'getcwd'), ('os', 'stat'), ('os', 'lstat'),
    ('os', 'read'), ('os', 'open'), ('os', 'makedirs'), ('os', 'mkdir'),
    ('os', 'readlink'), ('os', 'access'), ('os', 'fspath'),
}

# Strict mode allowlist — covers HTTP clients, data processing, crypto, text, math
ALLOWED_STRICT = {
    # HTTP & data interchange
    'requests', 'urllib', 'json', 'xml', 'html', 'csv', 'base64',
    # Text & pattern processing
    're', 'string', 'textwrap', 'difflib', 'unicodedata',
    # Date, time, math
    'datetime', 'zoneinfo', 'calendar', 'time',
    'math', 'decimal', 'fractions', 'numbers', 'statistics', 'random',
    # Data structures & functional
    'collections', 'itertools', 'functools', 'operator', 'copy',
    # Crypto & encoding
    'hashlib', 'hmac', 'secrets', 'binascii', 'struct',
    # Type system & boilerplate
    'typing', 'enum', 'dataclasses', 'abc',
    # Misc safe stdlib
    'uuid', 'logging', 'pprint', 'textwrap', 'contextlib',
    # Allowed but managed-blocked (belt + suspenders)
    'os', 'io', 'pathlib',
}


def is_managed():
    from core.settings_manager import settings
    return settings.is_managed()


def validate_code(code, strictness='strict'):
    """Validate Python source code via AST.

    Args:
        code: Python source string
        strictness: 'strict' (allowlist), 'moderate' (blocklist), or 'trust' (syntax only)

    Returns:
        (ok: bool, error_msg: str)
    """
    if strictness == 'trust':
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    blocked_imports = BLOCKED_IMPORTS
    blocked_attrs = BLOCKED_ATTRS
    if is_managed():
        blocked_imports = blocked_imports | MANAGED_BLOCKED_IMPORTS
        blocked_attrs = blocked_attrs | MANAGED_BLOCKED_ATTRS

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split('.')[0]
                if mod in blocked_imports:
                    return False, f"Blocked import: {mod}"
                if strictness == 'strict' and mod not in ALLOWED_STRICT:
                    return False, f"Import '{mod}' not in allowlist"

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split('.')[0]
                if mod in blocked_imports:
                    return False, f"Blocked import: {mod}"
                if strictness == 'strict' and mod not in ALLOWED_STRICT:
                    return False, f"Import '{mod}' not in allowlist"

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                return False, f"Blocked call: {node.func.id}()"

        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if (node.value.id, node.attr) in blocked_attrs:
                return False, f"Blocked: {node.value.id}.{node.attr}"

    return True, ""


def validate_plugin_files(plugin_dir, strictness='strict'):
    """Validate all .py files in a plugin directory.

    Returns:
        (ok: bool, error_msg: str) — error_msg includes the failing file
    """
    from pathlib import Path
    plugin_path = Path(plugin_dir)

    for py_file in plugin_path.rglob('*.py'):
        try:
            source = py_file.read_text(encoding='utf-8')
        except Exception as e:
            return False, f"{py_file.name}: cannot read ({e})"

        ok, err = validate_code(source, strictness)
        if not ok:
            return False, f"{py_file.name}: {err}"

    return True, ""
