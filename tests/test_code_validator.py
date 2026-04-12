"""
Code validator tests — core/code_validator.py.

This is the sandbox that protects Sapphire from malicious toolmaker output
and unsigned plugins in managed mode. If validate_code() has a bypass, an
attacker can escape the sandbox and run arbitrary code.

SECURITY-CRITICAL: every blocked pattern needs a test. If someone finds a
way around the check, the test for it goes here so it never regresses.

Run with: pytest tests/test_code_validator.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.code_validator import validate_code


# ─── Syntax errors ──────────────────────────────────────────────────────────

def test_syntax_error_rejected():
    ok, err = validate_code("def broken(")
    assert not ok
    assert "Syntax" in err


def test_syntax_error_in_system_killer_mode():
    """system_killer still rejects syntax errors (can't exec broken code)."""
    ok, err = validate_code("def broken(", strictness='system_killer')
    assert not ok


def test_valid_code_in_system_killer_passes_everything():
    """system_killer mode only checks syntax — imports are unrestricted."""
    ok, _ = validate_code("import shutil; shutil.rmtree('/')", strictness='system_killer')
    assert ok  # scary, but that's the mode's contract


# ─── Blocked imports (strict mode) ──────────────────────────────────────────

@pytest.mark.parametrize("module", [
    'shutil', 'ctypes', 'multiprocessing', 'socket', 'signal', 'importlib',
    'subprocess',  # strict-only block
])
def test_blocked_imports_rejected_strict(module):
    ok, err = validate_code(f"import {module}", strictness='strict')
    assert not ok, f"'{module}' should be blocked in strict mode"
    assert "Blocked import" in err or "not in allowlist" in err


@pytest.mark.parametrize("module", [
    'shutil', 'ctypes', 'multiprocessing', 'socket', 'signal', 'importlib',
])
def test_blocked_imports_rejected_moderate(module):
    ok, err = validate_code(f"import {module}", strictness='moderate')
    assert not ok, f"'{module}' should be blocked in moderate mode"


def test_subprocess_allowed_in_moderate():
    """subprocess is only blocked in strict — moderate unlocks it."""
    ok, _ = validate_code("import subprocess", strictness='moderate')
    assert ok


# ─── Allowed imports (strict mode allowlist) ────────────────────────────────

@pytest.mark.parametrize("module", [
    'requests', 'json', 'datetime', 'math', 'collections', 're',
    'hashlib', 'uuid', 'typing', 'base64',
])
def test_allowed_imports_pass_strict(module):
    ok, _ = validate_code(f"import {module}", strictness='strict')
    assert ok, f"'{module}' should be allowed in strict mode"


def test_unknown_import_blocked_strict():
    """Modules not in ALLOWED_STRICT should be rejected."""
    ok, err = validate_code("import antigravity", strictness='strict')
    assert not ok
    assert "not in allowlist" in err


def test_unknown_import_allowed_moderate():
    """Moderate mode doesn't use an allowlist — anything not blocked is OK."""
    ok, _ = validate_code("import antigravity", strictness='moderate')
    assert ok


# ─── Blocked calls ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("call", [
    'eval("1+1")', 'exec("pass")', '__import__("os")', 'compile("x","","exec")',
    'globals()', 'locals()', 'getattr(x, "y")', 'setattr(x, "y", 1)',
    'delattr(x, "y")', 'open("file")',
])
def test_blocked_calls_rejected(call):
    # Wrap in a function to make it valid syntax
    code = f"def f(x=None):\n    {call}"
    ok, err = validate_code(code, strictness='strict')
    assert not ok, f"Call '{call}' should be blocked"
    assert "Blocked call" in err


# ─── Blocked attributes ────────────────────────────────────────────────────

@pytest.mark.parametrize("attr_code,description", [
    ('os.system("ls")', 'os.system'),
    ('os.popen("ls")', 'os.popen'),
    ('os.remove("file")', 'os.remove'),
    ('os.unlink("file")', 'os.unlink'),
    ('os.kill(1, 9)', 'os.kill'),
    ('os.environ["KEY"]', 'os.environ'),
], ids=lambda x: x if isinstance(x, str) else "")
def test_blocked_attrs_rejected(attr_code, description):
    code = f"import os\n{attr_code}"
    ok, err = validate_code(code, strictness='strict')
    assert not ok, f"{description} should be blocked"
    assert "Blocked" in err


# ─── Alias tracking (the clever bypass attempts) ───────────────────────────

def test_alias_import_tracked():
    """import os as o → o.system should still be caught."""
    code = "import os as o\no.system('ls')"
    ok, err = validate_code(code, strictness='strict')
    assert not ok
    assert "Blocked" in err


def test_alias_assignment_tracked():
    """x = os → x.system should still be caught."""
    code = "import os\nx = os\nx.system('ls')"
    ok, err = validate_code(code, strictness='strict')
    assert not ok


def test_from_import_blocked_call_alias():
    """from builtins import eval as e → e() should be caught."""
    # This tests that `from X import blocked_name as alias` is tracked
    code = "e = eval\ne('1+1')"
    ok, err = validate_code(code, strictness='strict')
    assert not ok
    assert "Blocked call" in err


# ─── Safe code should pass ──────────────────────────────────────────────────

def test_normal_tool_code_passes():
    """A typical toolmaker-generated tool should validate cleanly."""
    code = '''
import json
import requests
from datetime import datetime

TOOLS = [{"type": "function", "function": {"name": "test_tool"}}]

def execute(function_name, arguments, config):
    data = json.dumps({"query": arguments.get("q", "")})
    response = requests.post("http://api.example.com", data=data)
    return response.text, True
'''
    ok, err = validate_code(code, strictness='strict')
    assert ok, f"Normal tool code should pass: {err}"
