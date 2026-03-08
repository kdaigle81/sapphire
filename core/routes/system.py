# core/routes/system.py - Backup, audio devices, continuity, setup wizard, avatars, system restart/shutdown
import json
import os
import time
import logging
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

import config
from core.auth import require_login
from core.api_fastapi import get_system

logger = logging.getLogger(__name__)

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "interfaces" / "web" / "static"


# =============================================================================
# BACKUP ROUTES
# =============================================================================

@router.get("/api/backup/list")
async def list_backups(request: Request, _=Depends(require_login)):
    """List all backups."""
    from core.backup import backup_manager
    return {"backups": backup_manager.list_backups()}


@router.post("/api/backup/create")
async def create_backup(request: Request, _=Depends(require_login)):
    """Create a backup."""
    from core.backup import backup_manager
    data = await request.json() or {}
    backup_type = data.get('type', 'manual')
    if backup_type not in ('daily', 'weekly', 'monthly', 'manual'):
        raise HTTPException(status_code=400, detail="Invalid backup type")

    filename = backup_manager.create_backup(backup_type)
    if filename:
        backup_manager.rotate_backups()
        return {"status": "success", "filename": filename}
    else:
        raise HTTPException(status_code=500, detail="Backup creation failed")


@router.delete("/api/backup/delete/{filename}")
async def delete_backup(filename: str, request: Request, _=Depends(require_login)):
    """Delete a backup."""
    from core.backup import backup_manager
    if backup_manager.delete_backup(filename):
        return {"status": "success", "deleted": filename}
    else:
        raise HTTPException(status_code=404, detail="Backup not found")


@router.get("/api/backup/download/{filename}")
async def download_backup(filename: str, request: Request, _=Depends(require_login)):
    """Download a backup."""
    from core.backup import backup_manager
    filepath = backup_manager.get_backup_path(filename)
    if filepath:
        return FileResponse(filepath, filename=filename, media_type='application/gzip')
    else:
        raise HTTPException(status_code=404, detail="Backup not found")


# =============================================================================
# AUDIO DEVICE ROUTES
# =============================================================================

@router.get("/api/audio/devices")
async def get_audio_devices(request: Request, _=Depends(require_login)):
    """Get audio devices."""
    from core.audio import get_device_manager
    dm = get_device_manager()
    devices = dm.query_devices(force_refresh=True)

    input_devices = []
    output_devices = []

    for dev in devices:
        dev_info = {'index': dev.index, 'name': dev.name}
        if dev.max_input_channels > 0:
            input_devices.append({**dev_info, 'channels': dev.max_input_channels, 'sample_rate': int(dev.default_samplerate), 'is_default': dev.is_default_input})
        if dev.max_output_channels > 0:
            output_devices.append({**dev_info, 'channels': dev.max_output_channels, 'sample_rate': int(dev.default_samplerate), 'is_default': dev.is_default_output})

    return {
        'input': input_devices,
        'output': output_devices,
        'configured_input': getattr(config, 'AUDIO_INPUT_DEVICE', None),
        'configured_output': getattr(config, 'AUDIO_OUTPUT_DEVICE', None),
    }


@router.post("/api/audio/test-input")
async def test_audio_input(request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Test audio input device."""
    import asyncio
    data = await request.json() or {}
    device_index = data.get('device_index')
    duration = min(data.get('duration', 3.0), 5.0)

    if device_index == 'auto' or device_index == '':
        device_index = None
    elif device_index is not None:
        try:
            device_index = int(device_index)
        except (ValueError, TypeError):
            device_index = None

    def _test_input():
        from core.audio import get_device_manager, classify_audio_error
        wakeword_paused = False
        try:
            if hasattr(system, 'wake_word_recorder') and system.wake_word_recorder:
                if hasattr(system.wake_word_recorder, 'pause_recording'):
                    wakeword_paused = system.wake_word_recorder.pause_recording()
                    if wakeword_paused:
                        time.sleep(0.3)
        except Exception:
            pass
        try:
            dm = get_device_manager()
            return dm.test_input_device_safe(device_index=device_index, duration=duration)
        except Exception as e:
            return {'success': False, 'error': classify_audio_error(e)}
        finally:
            if wakeword_paused:
                try:
                    time.sleep(0.2)
                    system.wake_word_recorder.resume_recording()
                except Exception:
                    pass

    import asyncio
    return await asyncio.to_thread(_test_input)


@router.post("/api/audio/test-output")
async def test_audio_output(request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Test audio output device."""
    import asyncio
    data = await request.json() or {}
    device_index = data.get('device_index')
    duration = min(data.get('duration', 0.5), 2.0)
    frequency = data.get('frequency', 440)

    if device_index == 'auto' or device_index == '' or device_index is None:
        device_index = None
    else:
        try:
            device_index = int(device_index)
        except (ValueError, TypeError):
            device_index = None

    def _test_output():
        import numpy as np
        import sounddevice as sd

        # Pause wakeword stream to avoid audio device conflict
        wakeword_paused = False
        try:
            if hasattr(system, 'wake_word_recorder') and system.wake_word_recorder:
                if hasattr(system.wake_word_recorder, 'pause_recording'):
                    wakeword_paused = system.wake_word_recorder.pause_recording()
                    if wakeword_paused:
                        time.sleep(0.3)
        except Exception:
            pass

        try:
            sample_rate = None
            default_rate = 44100
            if device_index is not None:
                try:
                    dev_info = sd.query_devices(device_index)
                    default_rate = int(dev_info['default_samplerate'])
                except Exception:
                    pass

            for rate in [default_rate, 48000, 44100, 32000, 24000, 22050, 16000]:
                try:
                    stream = sd.OutputStream(device=device_index, samplerate=rate, channels=1, dtype=np.float32)
                    stream.close()
                    sample_rate = rate
                    break
                except Exception:
                    continue

            if sample_rate is None:
                return {'success': False, 'error': 'Device does not support any common sample rate'}

            t = np.linspace(0, duration, int(sample_rate * duration), False)
            tone = np.sin(2 * np.pi * frequency * t)
            fade_samples = int(sample_rate * 0.02)
            fade_in = np.linspace(0, 1, fade_samples)
            fade_out = np.linspace(1, 0, fade_samples)
            tone[:fade_samples] *= fade_in
            tone[-fade_samples:] *= fade_out
            tone = (tone * 0.5 * 32767).astype(np.int16)

            sd.play(tone, sample_rate, device=device_index)
            sd.wait()
            return {'success': True, 'duration': duration, 'frequency': frequency, 'sample_rate': sample_rate}
        finally:
            if wakeword_paused:
                try:
                    time.sleep(0.2)
                    system.wake_word_recorder.resume_recording()
                except Exception:
                    pass

    return await asyncio.to_thread(_test_output)


# =============================================================================
# CONTINUITY ROUTES
# =============================================================================

@router.get("/api/continuity/tasks")
async def list_continuity_tasks(request: Request, _=Depends(require_login), system=Depends(get_system)):
    """List continuity tasks. Optional ?heartbeat=true/false filter."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        return {"tasks": []}
    tasks = system.continuity_scheduler.list_tasks()
    hb_filter = request.query_params.get("heartbeat")
    if hb_filter is not None:
        want_hb = hb_filter.lower() in ("true", "1", "yes")
        tasks = [t for t in tasks if t.get("heartbeat", False) == want_hb]
    return {"tasks": tasks}


@router.post("/api/continuity/tasks")
async def create_continuity_task(request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Create a continuity task."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        raise HTTPException(status_code=503, detail="Continuity scheduler not available")
    data = await request.json()
    task_id = system.continuity_scheduler.create_task(data)
    return {"status": "success", "task_id": task_id}


@router.get("/api/continuity/tasks/{task_id}")
async def get_continuity_task(task_id: str, request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Get a continuity task."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        raise HTTPException(status_code=503, detail="Continuity scheduler not available")
    task = system.continuity_scheduler.get_task(task_id)
    if task:
        return task
    else:
        raise HTTPException(status_code=404, detail="Task not found")


@router.put("/api/continuity/tasks/{task_id}")
async def update_continuity_task(task_id: str, request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Update a continuity task."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        raise HTTPException(status_code=503, detail="Continuity scheduler not available")
    data = await request.json()
    if system.continuity_scheduler.update_task(task_id, data):
        return {"status": "success"}
    else:
        raise HTTPException(status_code=404, detail="Task not found")


@router.delete("/api/continuity/tasks/{task_id}")
async def delete_continuity_task(task_id: str, request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Delete a continuity task."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        raise HTTPException(status_code=503, detail="Continuity scheduler not available")
    if system.continuity_scheduler.delete_task(task_id):
        return {"status": "success"}
    else:
        raise HTTPException(status_code=404, detail="Task not found")


@router.post("/api/continuity/tasks/{task_id}/run")
def run_continuity_task(task_id: str, request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Manually run a continuity task. Sync so it runs in threadpool, not blocking event loop."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        raise HTTPException(status_code=503, detail="Continuity scheduler not available")
    result = system.continuity_scheduler.run_task_now(task_id)
    return result


@router.get("/api/continuity/status")
async def get_continuity_status(request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Get continuity scheduler status."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        return {"running": False}
    return system.continuity_scheduler.get_status()


@router.get("/api/continuity/activity")
async def get_continuity_activity(request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Get continuity activity log."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        return {"activity": []}
    limit = int(request.query_params.get("limit", 50))
    return {"activity": system.continuity_scheduler.get_activity(limit)}


@router.get("/api/continuity/timeline")
async def get_continuity_timeline(request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Get continuity task timeline (future only, legacy)."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        return {"timeline": []}
    hours = int(request.query_params.get("hours", 24))
    return {"timeline": system.continuity_scheduler.get_timeline(hours)}


@router.get("/api/continuity/merged-timeline")
async def get_continuity_merged_timeline(request: Request, _=Depends(require_login), system=Depends(get_system)):
    """Get merged timeline: past activity + future schedule with NOW marker."""
    if not hasattr(system, 'continuity_scheduler') or not system.continuity_scheduler:
        return {"now": None, "past": [], "future": []}
    hours_back = int(request.query_params.get("hours_back", 12))
    hours_ahead = int(request.query_params.get("hours_ahead", 12))
    return system.continuity_scheduler.get_merged_timeline(hours_back, hours_ahead)


# =============================================================================
# SETUP WIZARD ROUTES
# =============================================================================

@router.get("/api/setup/check-packages")
async def check_packages(request: Request, _=Depends(require_login)):
    """Check optional packages. Returns format expected by setup wizard UI."""
    checks = {
        "tts": {"package": "Kokoro TTS", "requirements": "requirements-tts.txt", "mod": "kokoro"},
        "stt": {"package": "Faster Whisper", "requirements": "requirements-stt.txt", "mod": "faster_whisper"},
        "wakeword": {"package": "OpenWakeWord", "requirements": "requirements-wakeword.txt", "mod": "openwakeword"},
    }
    packages = {}
    for key, info in checks.items():
        try:
            __import__(info["mod"])
            installed = True
        except ImportError:
            installed = False
        packages[key] = {"installed": installed, "package": info["package"], "requirements": info["requirements"]}
    return {"packages": packages}


@router.get("/api/setup/wizard-step")
async def get_wizard_step(request: Request, _=Depends(require_login)):
    """Get wizard step."""
    from core.settings_manager import settings as sm
    managed = sm.is_managed()
    return {"step": getattr(config, 'SETUP_WIZARD_STEP', 'complete'), "managed": managed}


@router.put("/api/setup/wizard-step")
async def set_wizard_step(request: Request, _=Depends(require_login)):
    """Set wizard step."""
    from core.settings_manager import settings
    data = await request.json()
    step = data.get('step', 'complete')
    settings.set('SETUP_WIZARD_STEP', step, persist=True)
    return {"status": "success", "step": step}


# =============================================================================
# AVATAR ROUTES
# =============================================================================

@router.get("/api/avatars")
async def get_avatars(request: Request, _=Depends(require_login)):
    """Get avatar paths."""
    avatar_dir = PROJECT_ROOT / 'user' / 'public' / 'avatars'
    static_dir = STATIC_DIR / 'users'

    result = {}
    for role in ('user', 'assistant'):
        custom = list(avatar_dir.glob(f'{role}.*')) if avatar_dir.exists() else []
        if custom:
            ext = custom[0].suffix
            result[role] = f"/user-assets/avatars/{role}{ext}"
        else:
            for ext in ('.webp', '.png', '.jpg'):
                if (static_dir / f'{role}{ext}').exists():
                    result[role] = f"/static/users/{role}{ext}"
                    break
            else:
                result[role] = None
    return result


@router.post("/api/avatar/upload")
async def upload_avatar(file: UploadFile = File(...), role: str = Form(...), _=Depends(require_login)):
    """Upload avatar."""
    if role not in ('user', 'assistant'):
        raise HTTPException(status_code=400, detail="Invalid role")

    allowed_ext = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail="Invalid file type")

    contents = await file.read()
    if len(contents) > 4 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 4MB")

    avatar_dir = PROJECT_ROOT / 'user' / 'public' / 'avatars'
    avatar_dir.mkdir(parents=True, exist_ok=True)

    # Delete existing
    existing = list(avatar_dir.glob(f'{role}.*'))
    for old_file in existing:
        try:
            old_file.unlink()
        except Exception:
            pass

    save_path = avatar_dir / f'{role}{ext}'
    with open(save_path, 'wb') as f:
        f.write(contents)

    return {"status": "success", "path": f"/user-assets/avatars/{role}{ext}"}


@router.get("/api/avatar/check/{role}")
async def check_avatar(role: str, request: Request, _=Depends(require_login)):
    """Check if custom avatar exists."""
    if role not in ('user', 'assistant'):
        raise HTTPException(status_code=400, detail="Invalid role")

    avatar_dir = PROJECT_ROOT / 'user' / 'public' / 'avatars'
    existing = list(avatar_dir.glob(f'{role}.*')) if avatar_dir.exists() else []

    if existing:
        ext = existing[0].suffix
        return {"exists": True, "path": f"/user-assets/avatars/{role}{ext}"}
    return {"exists": False, "path": None}


# =============================================================================
# SYSTEM MANAGEMENT ROUTES
# =============================================================================

@router.post("/api/system/restart")
async def request_system_restart(request: Request, _=Depends(require_login)):
    """Request system restart."""
    from core.api_fastapi import get_restart_callback
    callback = get_restart_callback()
    if not callback:
        raise HTTPException(status_code=503, detail="Restart not available")
    callback()
    return {"status": "restarting", "message": "Restart initiated"}


@router.post("/api/system/shutdown")
async def request_system_shutdown(request: Request, _=Depends(require_login)):
    """Request system shutdown."""
    from core.api_fastapi import get_shutdown_callback
    callback = get_shutdown_callback()
    if not callback:
        raise HTTPException(status_code=503, detail="Shutdown not available")
    callback()
    return {"status": "shutting_down", "message": "Shutdown initiated"}
