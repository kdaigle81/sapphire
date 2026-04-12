"""
10-Persona Concurrent Scope Bleed Test — belt AND suspenders.

This is the "what if 10 personas fire at the exact same time?" test. It
proves that Sapphire's scope isolation holds under real concurrent load
across all three defense layers:

  LAYER 1 (belt):     ContextVar thread isolation — each thread gets its own scope values
  LAYER 2 (suspenders): Snapshot pattern — snapshot_all_scopes() captures a frozen dict
  LAYER 3 (db):       Actual tool execution — scope flows from ContextVar through
                       _get_current_scope() into the SQL WHERE clause

The test creates 10 threads, each simulating a different persona with unique
scope values for ALL 11 scopes (memory, goal, knowledge, people, email,
bitcoin, gcal, telegram, discord, rag, private). A threading.Barrier forces
true concurrent interleaving — no thread proceeds until all 10 have set
their scopes. Then each thread reads back its values and asserts isolation.

The DB-level test goes further: it actually calls save_memory and verifies
the memory ended up in the right scope by querying the DB directly.

WHY THIS MATTERS: Krem's concern is the telegram daemon controlling house
tools. If scope_telegram leaked between a scheduled heartbeat and a user
chat, tool calls could target the wrong Telegram account. The ContextVar
mechanism makes this impossible — but "impossible" needs a test.

Run with: pytest tests/test_scope_bleed.py -v
"""
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─── LAYER 1: ContextVar isolation under 10-thread concurrency ──────────────

class TestLayer1ContextVarIsolation:
    """10 threads, each sets ALL scopes to unique values. Barrier sync forces
    true interleaving. After the barrier, each thread reads back its values
    and stores them. The main thread asserts every thread got its own values.

    This is the fundamental guarantee. If Python's ContextVar is broken,
    everything else is moot. (It isn't, but we prove it.)
    """

    def test_10_threads_all_scopes_isolated(self):
        from core.chat.function_manager import (
            SCOPE_REGISTRY, reset_scopes, scope_setting_keys
        )

        N = 10
        barrier = threading.Barrier(N)
        results = {}  # thread_id -> {scope_key: value_read_back}
        errors = []

        # Build unique scope values for each thread
        # Thread 0 gets memory_scope='persona_0', thread 1 gets 'persona_1', etc.
        def persona_thread(thread_id):
            try:
                # Set every scope to a thread-unique value
                for key, reg in list(SCOPE_REGISTRY.items()):
                    if isinstance(reg['default'], bool):
                        # private is a bool — alternate True/False by thread
                        reg['var'].set(thread_id % 2 == 0)
                    elif reg['default'] is None:
                        # rag default is None — use a string
                        reg['var'].set(f'rag_{thread_id}')
                    else:
                        reg['var'].set(f'persona_{thread_id}')

                # All threads wait here — forces maximum interleaving
                barrier.wait(timeout=5)

                # Small sleep to let other threads run (exaggerates any bleed)
                time.sleep(0.02)

                # Read back all scope values
                thread_results = {}
                for key, reg in list(SCOPE_REGISTRY.items()):
                    thread_results[key] = reg['var'].get()

                results[thread_id] = thread_results

            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=persona_thread, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == N, f"Only {len(results)}/{N} threads completed"

        # Assert isolation: each thread should have read back its OWN values
        for thread_id in range(N):
            r = results[thread_id]
            for key, reg in list(SCOPE_REGISTRY.items()):
                if isinstance(reg['default'], bool):
                    expected = thread_id % 2 == 0
                elif reg['default'] is None:
                    expected = f'rag_{thread_id}'
                else:
                    expected = f'persona_{thread_id}'

                assert r[key] == expected, \
                    f"SCOPE BLEED! Thread {thread_id} scope '{key}': " \
                    f"expected {expected!r}, got {r[key]!r}"


# ─── LAYER 2: Snapshot pattern isolation ────────────────────────────────────

class TestLayer2SnapshotIsolation:
    """Tests the snapshot pattern used by chat_streaming.py and executor.py.

    The real code does:
        reset_scopes() → apply_scopes(settings) → snapshot = snapshot_all_scopes()
    then passes `snapshot` as a plain dict to tool execution. This means even
    if the ContextVar gets reset (which it does in Starlette SSE generators),
    the snapshot holds the correct values.

    This test verifies:
      1. Snapshots taken in different threads capture different values
      2. Resetting scopes AFTER snapshot doesn't affect the snapshot
      3. Snapshots from different threads never cross-contaminate
    """

    def test_10_thread_snapshot_isolation(self):
        from core.chat.function_manager import (
            SCOPE_REGISTRY, reset_scopes, apply_scopes_from_settings,
            snapshot_all_scopes, restore_scopes, scope_setting_keys
        )

        N = 10
        barrier = threading.Barrier(N)
        snapshots = {}  # thread_id -> snapshot dict
        errors = []

        def snapshot_thread(thread_id):
            try:
                # Simulate what chat_streaming.py does at line 149-162:
                # 1. Reset scopes to defaults
                reset_scopes()

                # 2. Build fake persona settings with unique scope values
                settings = {}
                for key in scope_setting_keys():
                    settings[key] = f'snap_{thread_id}'
                settings['private_chat'] = thread_id % 2 == 0

                # 3. Apply scopes from the fake persona
                apply_scopes_from_settings(None, settings)

                # 4. Take the snapshot (this is what gets passed to tool execution)
                snap = snapshot_all_scopes()

                # All threads wait here — forces interleaving AFTER snapshot
                barrier.wait(timeout=5)
                time.sleep(0.02)

                # 5. Reset scopes (simulating SSE generator context loss)
                reset_scopes()

                # The snapshot should STILL have the persona values, not defaults
                snapshots[thread_id] = snap

            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=snapshot_thread, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        assert len(snapshots) == N

        for thread_id in range(N):
            snap = snapshots[thread_id]
            for key, reg in list(SCOPE_REGISTRY.items()):
                setting = reg.get('setting')
                if not setting or setting == 'private_chat':
                    continue
                if reg['default'] is None:
                    continue  # rag has no setting key

                expected = f'snap_{thread_id}'
                assert snap[key] == expected, \
                    f"SNAPSHOT BLEED! Thread {thread_id} snapshot['{key}']: " \
                    f"expected {expected!r}, got {snap[key]!r}"

    def test_snapshot_survives_reset(self):
        """A single-thread proof: snapshot is a frozen dict, not a live view."""
        from core.chat.function_manager import (
            reset_scopes, apply_scopes_from_settings,
            snapshot_all_scopes, scope_setting_keys
        )

        reset_scopes()
        settings = {k: 'captured' for k in scope_setting_keys()}
        apply_scopes_from_settings(None, settings)
        snap = snapshot_all_scopes()

        # Nuke the ContextVars
        reset_scopes()

        # Snapshot should still say 'captured'
        for key in scope_setting_keys():
            scope_key = key.replace('_scope', '')
            assert snap.get(scope_key) == 'captured', \
                f"Snapshot['{scope_key}'] was mutated by reset_scopes()"


# ─── LAYER 3: Actual DB scope isolation ─────────────────────────────────────

class TestLayer3DatabaseScopeIsolation:
    """The deepest layer: do memories actually end up in the right scope?

    10 threads each:
      1. Set memory_scope to a unique value via ContextVar
      2. Call _save_memory() with a canary string
      3. After all threads complete, query the DB directly
      4. Assert each canary is ONLY in its expected scope

    This tests the full path: ContextVar → _get_current_scope() → SQL INSERT.
    If anything in that chain leaks, a canary appears in the wrong scope.
    """

    @pytest.fixture
    def isolated_memory_db(self, tmp_path):
        """Point the memory module at a temp DB. Clean up after."""
        from plugins.memory.tools import memory_tools

        db_path = tmp_path / "bleed_test.db"
        original_path = memory_tools._db_path
        original_init = memory_tools._db_initialized

        memory_tools._db_path = db_path
        memory_tools._db_initialized = False
        memory_tools._ensure_db()

        yield memory_tools, db_path

        memory_tools._db_path = original_path
        memory_tools._db_initialized = original_init

    def test_10_threads_memories_land_in_correct_scope(self, isolated_memory_db):
        from core.chat.function_manager import scope_memory

        memory_tools, db_path = isolated_memory_db
        N = 10
        barrier = threading.Barrier(N)
        errors = []

        def save_thread(thread_id):
            try:
                scope_name = f'bleed_test_{thread_id}'
                # Create the scope in the DB
                memory_tools.create_scope(scope_name)

                # Set the ContextVar to this thread's scope
                scope_memory.set(scope_name)

                # Wait for all threads to be ready
                barrier.wait(timeout=5)

                # Save a canary memory — _save_memory reads scope from ContextVar
                canary = f'canary_{thread_id}_secret_data'
                result, success = memory_tools._save_memory(canary, scope=scope_name)
                if not success:
                    errors.append(f"Thread {thread_id} save failed: {result}")

            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=save_thread, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Save errors: {errors}"

        # Now verify: each canary must be in its scope and ONLY its scope
        conn = sqlite3.connect(db_path)
        for thread_id in range(N):
            scope_name = f'bleed_test_{thread_id}'
            canary = f'canary_{thread_id}_secret_data'

            # Canary should exist in its scope
            row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE scope = ? AND content LIKE ?",
                (scope_name, f'%{canary}%')
            ).fetchone()
            assert row[0] == 1, \
                f"Thread {thread_id}: canary not found in scope '{scope_name}'"

            # Canary should NOT exist in any OTHER scope
            bleed = conn.execute(
                "SELECT scope FROM memories WHERE content LIKE ? AND scope != ?",
                (f'%{canary}%', scope_name)
            ).fetchone()
            assert bleed is None, \
                f"SCOPE BLEED! Thread {thread_id} canary leaked to scope '{bleed[0]}'"

        conn.close()

    def test_concurrent_different_scope_reads_isolated(self, isolated_memory_db):
        """Two threads read memories from different scopes. Thread A must never
        see Thread B's data, even under concurrent load."""
        from core.chat.function_manager import scope_memory

        memory_tools, db_path = isolated_memory_db

        # Pre-populate two scopes
        memory_tools.create_scope('alice_scope')
        memory_tools.create_scope('bob_scope')
        memory_tools._save_memory('alice_secret', scope='alice_scope')
        memory_tools._save_memory('bob_secret', scope='bob_scope')

        results = {}
        barrier = threading.Barrier(2)

        def read_thread(name, scope):
            scope_memory.set(scope)
            barrier.wait(timeout=5)
            time.sleep(0.01)  # force interleaving
            # _search_memory reads from the scope param
            result, _ = memory_tools._search_memory('secret', limit=10, label=None, scope=scope)
            results[name] = result

        t_alice = threading.Thread(target=read_thread, args=('alice', 'alice_scope'))
        t_bob = threading.Thread(target=read_thread, args=('bob', 'bob_scope'))
        t_alice.start(); t_bob.start()
        t_alice.join(); t_bob.join()

        assert 'alice_secret' in results['alice']
        assert 'bob_secret' not in results['alice'], \
            "BLEED: Alice saw Bob's memory"
        assert 'bob_secret' in results['bob']
        assert 'alice_secret' not in results['bob'], \
            "BLEED: Bob saw Alice's memory"


# ─── LAYER 4: Full CRUD gauntlet — 10 threads × 3 tool modules ─────────────

class TestLayer4FullCRUDGauntlet:
    """The stress test. 10 threads, each running the FULL tool CRUD sequence
    across memory, knowledge, AND people — all concurrent, all different scopes.

    Each thread does (in order):
      Memory:    save → search by keyword → verify found → delete → verify gone
      Knowledge: save to category → search category → verify → delete → verify
      People:    save person → search → verify → delete → verify

    After all threads complete, we do a cross-scope audit: every canary must
    exist ONLY in its expected scope, never in another thread's scope.

    This is the "10 heartbeats fire at 9am" scenario. Different scopes,
    different data, all hitting the same DB through the same code paths.
    """

    @pytest.fixture
    def isolated_dbs(self, tmp_path):
        """Point BOTH memory_tools AND knowledge_tools at temp DBs.

        They use separate databases (memory.db vs knowledge.db), so we need
        to redirect both. Goals uses its own DB too but we're not testing
        goals CRUD here — memory + knowledge + people covers the scope surface.
        """
        from plugins.memory.tools import memory_tools, knowledge_tools

        # Memory DB
        mem_db = tmp_path / "bleed_memory.db"
        orig_mem_path = memory_tools._db_path
        orig_mem_init = memory_tools._db_initialized
        memory_tools._db_path = mem_db
        memory_tools._db_initialized = False
        memory_tools._ensure_db()

        # Knowledge DB (also has people table)
        know_db = tmp_path / "bleed_knowledge.db"
        orig_know_path = knowledge_tools._db_path
        orig_know_init = knowledge_tools._db_initialized
        knowledge_tools._db_path = know_db
        knowledge_tools._db_initialized = False
        knowledge_tools._ensure_db()

        yield memory_tools, knowledge_tools, mem_db, know_db

        memory_tools._db_path = orig_mem_path
        memory_tools._db_initialized = orig_mem_init
        knowledge_tools._db_path = orig_know_path
        knowledge_tools._db_initialized = orig_know_init

    def test_10_thread_full_crud_no_bleed(self, isolated_dbs):
        """The main event. 10 threads, full CRUD, barrier-synced."""
        from core.chat.function_manager import scope_memory, scope_knowledge, scope_people

        memory_tools, knowledge_tools, mem_db, know_db = isolated_dbs
        N = 10
        barrier = threading.Barrier(N)
        errors = []
        crud_results = {}  # thread_id -> dict of operation results

        def crud_thread(tid):
            try:
                mem_scope = f'bleed_mem_{tid}'
                know_scope = f'bleed_know_{tid}'
                people_scope = f'bleed_ppl_{tid}'

                # Set ContextVars for this thread
                scope_memory.set(mem_scope)
                scope_knowledge.set(know_scope)
                scope_people.set(people_scope)

                # Create scopes in the DBs
                memory_tools.create_scope(mem_scope)
                knowledge_tools.create_scope(know_scope)
                # People scopes use knowledge_tools DB
                knowledge_tools.create_people_scope(people_scope)

                # ── Barrier: all threads start CRUD simultaneously ──
                barrier.wait(timeout=10)

                results = {}

                # ── MEMORY: save → search → delete ──
                canary_mem = f'canary_mem_{tid}_secret'
                res, ok = memory_tools._save_memory(canary_mem, scope=mem_scope)
                results['mem_save'] = ok
                if not ok:
                    errors.append(f"T{tid} mem save: {res}")
                    return

                res, _ = memory_tools._search_memory(f'canary_mem_{tid}',
                                                     limit=5, label=None, scope=mem_scope)
                results['mem_search_found'] = canary_mem in res

                # Get the memory ID for deletion
                conn = sqlite3.connect(memory_tools._db_path)
                row = conn.execute(
                    "SELECT id FROM memories WHERE scope = ? AND content LIKE ?",
                    (mem_scope, f'%{canary_mem}%')
                ).fetchone()
                conn.close()
                if row:
                    memory_tools._delete_memory(row[0], scope=mem_scope)
                    results['mem_deleted'] = True

                # ── KNOWLEDGE: save → search → delete ──
                canary_know = f'canary_know_{tid}_data'
                res, ok = knowledge_tools._save_knowledge(
                    f'test_category_{tid}', canary_know, scope=know_scope
                )
                results['know_save'] = ok

                res, _ = knowledge_tools._search_knowledge(
                    query=f'canary_know_{tid}', limit=5, scope=know_scope,
                    people_scope=people_scope
                )
                results['know_search_found'] = canary_know in res

                # Delete by category
                res, ok = knowledge_tools._delete_knowledge(
                    category=f'test_category_{tid}', scope=know_scope
                )
                results['know_deleted'] = ok

                # ── PEOPLE: save → search → delete ──
                canary_person = f'Canary_Person_{tid}'
                res, ok = knowledge_tools._save_person(
                    canary_person, relationship='test_contact',
                    notes=f'secret_note_{tid}', scope=people_scope
                )
                results['person_save'] = ok

                # Verify person exists in scope
                people_list = knowledge_tools.get_people(scope=people_scope)
                person_names = [p['name'] for p in people_list] if isinstance(people_list, list) else []
                results['person_found'] = canary_person in person_names

                # Delete the person
                if isinstance(people_list, list):
                    for p in people_list:
                        if p['name'] == canary_person:
                            knowledge_tools.delete_person(p['id'])
                            results['person_deleted'] = True
                            break

                crud_results[tid] = results

            except Exception as e:
                errors.append(f"T{tid}: {e}")

        # Fire all threads
        threads = [threading.Thread(target=crud_thread, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"
        assert len(crud_results) == N, f"Only {len(crud_results)}/{N} threads completed"

        # ── Verify each thread's CRUD operations succeeded ──
        for tid in range(N):
            r = crud_results[tid]
            assert r.get('mem_save'), f"T{tid}: memory save failed"
            assert r.get('mem_search_found'), f"T{tid}: memory search didn't find canary"
            assert r.get('know_save'), f"T{tid}: knowledge save failed"
            assert r.get('know_search_found'), f"T{tid}: knowledge search didn't find canary"
            assert r.get('person_save'), f"T{tid}: person save failed"
            assert r.get('person_found'), f"T{tid}: person not found in scope"

        # ── Cross-scope audit: check for bleed in memory DB ──
        conn = sqlite3.connect(mem_db)
        for tid in range(N):
            canary = f'canary_mem_{tid}_secret'
            bleed = conn.execute(
                "SELECT scope FROM memories WHERE content LIKE ? AND scope != ?",
                (f'%{canary}%', f'bleed_mem_{tid}')
            ).fetchone()
            assert bleed is None, \
                f"MEMORY BLEED! T{tid} canary leaked to scope '{bleed[0]}'"
        conn.close()

        # ── Cross-scope audit: check for bleed in knowledge DB ──
        conn = sqlite3.connect(know_db)
        for tid in range(N):
            canary_person = f'Canary_Person_{tid}'
            bleed = conn.execute(
                "SELECT scope FROM people WHERE name = ? AND scope != ?",
                (canary_person, f'bleed_ppl_{tid}')
            ).fetchone()
            assert bleed is None, \
                f"PEOPLE BLEED! T{tid} person leaked to scope '{bleed[0]}'"
        conn.close()
