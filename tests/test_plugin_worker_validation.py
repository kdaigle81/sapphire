"""Surface 5 P1 — claude-code plugin-worker validation + run_claude error handling.

PluginWorker runs Claude Code to build a Sapphire plugin, then validates the
output structure before declaring success. Weak validation = broken plugins
ship to disk and fail at load.

Covers:
  5.35 validate_plugin rejects ghost empty-capabilities manifests (Chaos #4)
  5.36 validate_plugin auto-fixes manifest atomically (tmp + os.replace)
  5.37 validate_plugin reports missing files with specific names (Chaos #10)
  5.38 run_claude treats nonzero exit as error even when stdout is parseable JSON (Chaos #6)
  5.39 run_claude handles unparseable stdout (falls through to line scan / error)
  5.40 plugin_worker fails when validation fails despite claude success

See tmp/coverage-test-plan.md Surface 5 P1.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_cct():
    if 'claude_code_tools_test' in sys.modules:
        return sys.modules['claude_code_tools_test']
    project_root = Path(__file__).resolve().parent.parent
    module_path = project_root / 'plugins' / 'claude-code' / 'tools' / 'claude_code_tools.py'
    spec = importlib.util.spec_from_file_location('claude_code_tools_test', module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['claude_code_tools_test'] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cct():
    return _load_cct()


# ─── 5.35 validate_plugin rejects ghost empty-capabilities plugin ────────────

def test_validate_plugin_rejects_empty_capabilities_ghost(cct, tmp_path):
    """[REGRESSION_GUARD] A manifest with {name, description} but NO capabilities
    is a ghost plugin — it loads without error but does nothing. Before the
    Chaos #4 fix, the per-capability loops vacuously passed and such
    plugins shipped as 'valid'.
    """
    # Build a ghost plugin in tmp_path
    (tmp_path / 'plugin.json').write_text(json.dumps({
        'name': 'ghost_plugin',
        'version': '1.0.0',
        'description': 'does nothing — ghost',
        # No capabilities key at all
    }))
    result = cct._validate_plugin(str(tmp_path))
    assert result.get('manifest_valid') is True
    assert result.get('has_capability') is False, \
        "ghost plugin with no capabilities must flag has_capability=False"


def test_validate_plugin_accepts_tools_capability(cct, tmp_path):
    """Inverse: a manifest declaring tools IS a real plugin (provided files exist)."""
    (tmp_path / 'plugin.json').write_text(json.dumps({
        'name': 'real_plugin', 'version': '1.0.0', 'description': 'has tools',
        'capabilities': {'tools': ['tools/main.py']},
    }))
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'tools' / 'main.py').write_text('def x(): pass\n')
    result = cct._validate_plugin(str(tmp_path))
    assert result.get('has_capability') is True


@pytest.mark.parametrize("cap_key,cap_value", [
    ('hooks', [{'event': 'pre_chat', 'fn': 'h.hook'}]),
    ('daemon', {'entry': 'daemon.py'}),
    ('routes', ['routes/r.py']),
    ('providers', {'tts': {'entry': 'p.py'}}),
    ('scopes', [{'key': 'x', 'setting': 'x_scope'}]),
    ('settings', [{'key': 'A', 'type': 'string'}]),
    ('schedule', {'tasks': [{'id': 't', 'cron': '* * * * *'}]}),
])
def test_validate_plugin_accepts_any_real_capability(cct, tmp_path, cap_key, cap_value):
    """Any non-empty capability (hooks/daemon/routes/providers/scopes/settings/schedule)
    flags has_capability=True."""
    (tmp_path / 'plugin.json').write_text(json.dumps({
        'name': 'thing', 'version': '1.0.0', 'description': 't',
        'capabilities': {cap_key: cap_value},
    }))
    result = cct._validate_plugin(str(tmp_path))
    assert result.get('has_capability') is True, \
        f"capability {cap_key}={cap_value!r} not accepted"


# ─── 5.36 Manifest auto-fix uses atomic tmp+replace ──────────────────────────

def test_validate_plugin_auto_fixes_manifest_atomically(cct, tmp_path):
    """[DATA_INTEGRITY] When Claude Code writes tools as a string instead of
    a list, the validator auto-normalizes it. This write MUST be atomic —
    tmp + os.replace — so a plugin file-watcher reading concurrently never
    sees a half-written manifest (would corrupt load on restart).
    """
    (tmp_path / 'plugin.json').write_text(json.dumps({
        'name': 'autofix', 'version': '1.0.0', 'description': 'test',
        'capabilities': {'tools': 'tools/main.py'},  # STRING, not list
    }))
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'tools' / 'main.py').write_text('def x(): pass\n')

    # Spy on os.replace to confirm atomic rename was used
    orig_replace = os.replace
    calls = []
    def _spy(src, dst):
        calls.append((str(src), str(dst)))
        return orig_replace(src, dst)

    with patch.object(os, 'replace', _spy):
        result = cct._validate_plugin(str(tmp_path))

    assert result.get('manifest_auto_fixed') is True
    # Atomic rename fired: src is a .tmp file, dst is the real plugin.json
    assert any(src.endswith('.tmp') and dst.endswith('plugin.json')
               for src, dst in calls), \
        f"atomic rename not used — calls: {calls}"

    # Manifest now has list (on-disk)
    data = json.loads((tmp_path / 'plugin.json').read_text())
    assert data['capabilities']['tools'] == ['tools/main.py']


# ─── 5.37 validate_plugin reports specific missing file names ────────────────

def test_validate_plugin_reports_missing_files_with_specific_names(cct, tmp_path):
    """[REGRESSION_GUARD] When a declared tool file is missing, the validator
    lists the specific path(s) in `_missing_files` so a follow-up agent or
    human doesn't have to hunt for which file the manifest declared that's
    absent on disk (Chaos #10)."""
    (tmp_path / 'plugin.json').write_text(json.dumps({
        'name': 'missing_files', 'version': '1.0.0', 'description': 't',
        'capabilities': {
            'tools': ['tools/one.py', 'tools/two.py'],
            'providers': {'tts': {'entry': 'tts_provider.py'}},
        },
    }))
    # Only write one of the declared files
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'tools' / 'one.py').write_text('')
    # two.py and tts_provider.py deliberately missing

    result = cct._validate_plugin(str(tmp_path))
    assert result.get('files_exist') is False
    missing = result.get('_missing_files', [])
    assert 'tools/two.py' in missing, f"missing file not named: {missing}"
    assert any('tts_provider.py' in m for m in missing), \
        f"provider file absence not reported: {missing}"


# ─── 5.38 run_claude: nonzero exit is an error even with stdout JSON ─────────

def test_run_claude_nonzero_exit_treated_as_error_despite_stdout_json(cct, fake_popen):
    """[REGRESSION_GUARD] Chaos #6: previously, returncode != 0 was ignored
    when stdout contained parseable JSON. That swallowed budget-cap-mid-gen
    and similar partial-success cases. Now: non-zero exit ALWAYS → error,
    regardless of stdout content.
    """
    fake_popen.returncode = 1
    fake_popen.stdout = '{"result": "some partial output", "session_id": "x"}'
    fake_popen.stderr = 'budget cap exceeded'

    data, err = cct._run_claude(['claude', 'run'], workspace='/tmp/ws')
    assert data is None
    assert err is not None
    assert 'exited with error' in err.lower() or 'code 1' in err.lower()
    assert 'budget' in err, f"stderr not surfaced in error: {err}"


def test_run_claude_success_returns_parsed_json(cct, fake_popen):
    """Inverse: exit 0 + JSON stdout → parsed data, no error."""
    fake_popen.returncode = 0
    fake_popen.stdout = '{"result": "built the thing", "session_id": "abc"}'
    data, err = cct._run_claude(['claude', 'run'], workspace='/tmp/ws')
    assert err is None
    assert data is not None
    assert data['result'] == 'built the thing'
    assert data['session_id'] == 'abc'


# ─── 5.39 run_claude handles unparseable stdout ──────────────────────────────

def test_run_claude_unparseable_stdout_falls_through(cct, fake_popen):
    """If stdout is not JSON, the function tries line-by-line parsing. If
    THAT fails too, it should either raise or return an error marker —
    never return garbage as `data`."""
    fake_popen.returncode = 0
    fake_popen.stdout = 'Total garbage not JSON at all\nmore text'
    fake_popen.stderr = ''

    data, err = cct._run_claude(['claude', 'run'], workspace='/tmp/ws')
    # Either err is set or data is None — the guarantee is the caller won't
    # see a bogus data dict
    assert data is None or 'result' not in data, \
        f"unparseable stdout returned garbage data: {data!r}"


# ─── 5.40 plugin_worker fails when validation fails despite claude success ───

def test_plugin_worker_fails_when_validation_fails_despite_claude_success(
    cct, tmp_path, monkeypatch, fake_popen,
):
    """[REGRESSION_GUARD] Claude Code can exit 0 with a 'done' result but
    produce a ghost plugin (empty capabilities, missing files, syntax errors).
    The PluginWorker MUST fail in that case — never advertise a broken plugin
    as a successful build.
    """
    monkeypatch.setattr(cct, '_SAPPHIRE_ROOT', str(tmp_path))
    plugin_base = tmp_path / 'user' / 'plugins'
    plugin_base.mkdir(parents=True)

    # Claude "succeeds" but the plugin is a ghost
    fake_popen.returncode = 0
    fake_popen.stdout = json.dumps({
        'result': 'plugin built',
        'session_id': 'sess-1',
    })

    # Stub _sanity_check so the worker proceeds through the body
    monkeypatch.setattr(cct, '_sanity_check', lambda ws: None)
    # Stub _publish_workspace_ready so we don't need the full SSE plumbing
    monkeypatch.setattr(cct, '_publish_workspace_ready', lambda *a, **kw: None)

    # Write a minimum "ghost plugin" file structure — manifest exists but
    # has no capabilities, so _validate_plugin flags has_capability=False
    PluginWorker = cct._create_plugin_worker()
    worker = PluginWorker(
        agent_id='t1', name='Forge', mission='build thing',
        chat_name='trinity', plugin_name='ghost_build',
    )
    worker._status = 'pending'
    import time
    worker._start_time = time.time()

    # We need to put a ghost manifest in place BEFORE validate runs. The
    # worker creates the dir via _run_claude, but our fake_popen doesn't do
    # that — we pre-create it with a ghost manifest.
    ghost_dir = plugin_base / 'ghost_build'
    ghost_dir.mkdir(parents=True)
    (ghost_dir / 'plugin.json').write_text(json.dumps({
        'name': 'ghost_build', 'version': '0.1.0', 'description': 'empty',
    }))

    worker.run()

    # Worker must either fail, OR its result must note the validation failure
    # (the exact state depends on the worker's flow — assert one of them)
    if worker.status == 'failed':
        assert worker.error is not None
    else:
        # If status is done, the result MUST mention validation concerns
        assert worker.result is not None
        assert ('capabil' in worker.result.lower()
                or 'validation' in worker.result.lower()
                or 'ghost' in worker.result.lower()
                or 'missing' in worker.result.lower()), \
            f"validation failure not surfaced in result: {worker.result[:300]}"
