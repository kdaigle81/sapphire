# Google Calendar tools
# Pure REST via requests — no Google client libraries needed.

import logging
import time
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

ENABLED = True
EMOJI = '\U0001f4c5'

GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
CALENDAR_API = 'https://www.googleapis.com/calendar/v3'

AVAILABLE_FUNCTIONS = ['calendar_today', 'calendar_range', 'calendar_add', 'calendar_delete']

TOOLS = [
    {
        "type": "function",
        "is_local": False,
        "network": True,
        "function": {
            "name": "calendar_today",
            "description": "Get today's calendar events. Shows schedule with times and free hours. Use when asked about today's plans, meetings, or schedule.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "is_local": False,
        "network": True,
        "function": {
            "name": "calendar_range",
            "description": "Get calendar events for a date range. Use for checking upcoming days, this week, availability on specific dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date (YYYY-MM-DD). Defaults to today."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date (YYYY-MM-DD). Defaults to 7 days from start."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "is_local": False,
        "network": True,
        "function": {
            "name": "calendar_add",
            "description": "Add an event to the calendar. Use when asked to schedule, book, or add something to the calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Event title"
                    },
                    "start": {
                        "type": "string",
                        "description": "Start datetime (YYYY-MM-DDTHH:MM) or date (YYYY-MM-DD) for all-day"
                    },
                    "end": {
                        "type": "string",
                        "description": "End datetime (YYYY-MM-DDTHH:MM) or date (YYYY-MM-DD). Defaults to 1 hour after start."
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description or notes"
                    }
                },
                "required": ["title", "start"]
            }
        }
    },
    {
        "type": "function",
        "is_local": False,
        "network": True,
        "function": {
            "name": "calendar_delete",
            "description": "Delete a calendar event by its number. Get the number from calendar_today or calendar_range first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "The event number to delete (e.g. '1' or '#1' from calendar results)"
                    }
                },
                "required": ["event_id"]
            }
        }
    }
]


# === Auth helpers ===

def _get_gcal_scope():
    """Get current gcal scope from ContextVar."""
    try:
        from core.chat.function_manager import scope_gcal
        return scope_gcal.get()
    except Exception:
        return 'default'


def _get_gcal_creds():
    """Get credentials for current gcal scope."""
    from core.credentials_manager import credentials
    scope = _get_gcal_scope()
    if scope is None:
        return None, "Google Calendar is disabled for this chat."
    return credentials.get_gcal_account(scope), None


def _get_access_token():
    """Get a valid access token, refreshing if expired."""
    creds, err = _get_gcal_creds()
    if err:
        return None, None, err

    refresh_token = creds.get('refresh_token', '')
    if not refresh_token:
        return None, None, "Google Calendar not connected. Go to Settings > Google Calendar and click Connect."

    client_id = creds.get('client_id', '')
    client_secret = creds.get('client_secret', '')
    if not client_id or not client_secret:
        return None, None, "Google Client ID/Secret not configured in Settings."

    calendar_id = creds.get('calendar_id', 'primary') or 'primary'

    # Check if cached access token is still valid (with 60s buffer)
    # We use credentials_manager's raw storage for the short-lived access_token cache
    from core.credentials_manager import credentials
    scope = _get_gcal_scope()
    raw = credentials._credentials.get('gcal_accounts', {}).get(scope, {})
    cached_token = raw.get('access_token', '')
    expires_at = raw.get('expires_at', 0)

    if cached_token and expires_at > time.time() + 60:
        return cached_token, calendar_id, None

    # Refresh the token
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'refresh_token',
    }, timeout=15)

    if resp.status_code != 200:
        logger.error(f"[GCAL] Token refresh failed: {resp.text}")
        return None, None, "Token refresh failed. Try reconnecting in Settings > Google Calendar."

    tokens = resp.json()
    access_token = tokens['access_token']
    new_expires = time.time() + tokens.get('expires_in', 3600)

    # Cache the short-lived token
    credentials.update_gcal_tokens(scope, refresh_token, access_token, new_expires)

    return access_token, calendar_id, None


def _api_get(token, endpoint, params=None):
    """Make an authenticated GET request to the Calendar API."""
    resp = requests.get(
        f"{CALENDAR_API}{endpoint}",
        headers={'Authorization': f'Bearer {token}'},
        params=params,
        timeout=15
    )
    if resp.status_code == 401:
        return None, "Authentication expired. Try reconnecting."
    if resp.status_code != 200:
        return None, f"API error {resp.status_code}: {resp.text[:200]}"
    return resp.json(), None


def _api_post(token, endpoint, data):
    """Make an authenticated POST request to the Calendar API."""
    resp = requests.post(
        f"{CALENDAR_API}{endpoint}",
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        json=data,
        timeout=15
    )
    if resp.status_code not in (200, 201):
        return None, f"API error {resp.status_code}: {resp.text[:200]}"
    return resp.json(), None


def _api_delete(token, endpoint):
    """Make an authenticated DELETE request to the Calendar API."""
    resp = requests.delete(
        f"{CALENDAR_API}{endpoint}",
        headers={'Authorization': f'Bearer {token}'},
        timeout=15
    )
    if resp.status_code not in (200, 204):
        return None, f"API error {resp.status_code}: {resp.text[:200]}"
    return True, None


# === Formatting ===

def _format_time(dt_str):
    """Parse Google's datetime and return clean time string."""
    try:
        # Handle full datetime
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            return dt.strftime('%I:%M %p').lstrip('0')
        # Handle date-only (all-day events)
        return 'All day'
    except Exception:
        return dt_str


# Short ID map — maps #1, #2 etc to real Google event IDs within a session
_id_map = {}


def _format_events(events, title_line, now=None):
    """Format a list of events into AI-digestible text. Labels past/current if now is provided."""
    global _id_map
    if not events:
        return f"{title_line}\nNo events scheduled."

    _id_map.clear()
    lines = [title_line]
    total_minutes = 0

    for i, event in enumerate(events, 1):
        summary = event.get('summary', '(No title)')
        real_id = event.get('id', '')
        _id_map[str(i)] = real_id
        start = event.get('start', {})
        end = event.get('end', {})

        start_str = start.get('dateTime', start.get('date', ''))
        end_str = end.get('dateTime', end.get('date', ''))

        label = ''
        if start.get('dateTime') and end.get('dateTime'):
            start_time = _format_time(start_str)
            end_time = _format_time(end_str)
            time_str = f"{start_time}–{end_time}"
            try:
                s = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                e = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                total_minutes += (e - s).total_seconds() / 60
                if now:
                    if e <= now:
                        label = ' [past]'
                    elif s <= now < e:
                        label = ' [NOW]'
            except Exception:
                pass
        else:
            time_str = "All day"

        lines.append(f"  #{i}  {time_str}  {summary}{label}")

    # Summary line
    hours_busy = total_minutes / 60
    lines.append(f"\n{len(events)} event{'s' if len(events) != 1 else ''}, ~{hours_busy:.1f} hours scheduled")

    return '\n'.join(lines)


# === Tool execution ===

def execute(function_name, arguments, config, plugin_settings=None):
    token, calendar_id, err = _get_access_token()
    if err:
        return err, False

    if function_name == 'calendar_today':
        tz = _get_local_tz()
        try:
            from zoneinfo import ZoneInfo
            user_tz = ZoneInfo(tz)
        except Exception:
            user_tz = None
        now = datetime.now(user_tz) if user_tz else datetime.now().astimezone()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        data, err = _api_get(token, f'/calendars/{calendar_id}/events', {
            'timeMin': today.isoformat(),
            'timeMax': tomorrow.isoformat(),
            'timeZone': tz,
            'singleEvents': 'true',
            'orderBy': 'startTime',
            'maxResults': 50,
        })
        if err:
            return err, False

        events = data.get('items', [])
        day_name = today.strftime('%A %B %d')
        return _format_events(events, f"Today ({day_name}):", now=now), True

    elif function_name == 'calendar_range':
        start_str = arguments.get('start_date', '')
        end_str = arguments.get('end_date', '')
        tz = _get_local_tz()

        try:
            from zoneinfo import ZoneInfo
            user_tz = ZoneInfo(tz)
        except Exception:
            user_tz = None

        try:
            start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            return f"Invalid start_date format: '{start_str}'. Use YYYY-MM-DD.", False

        try:
            end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else start + timedelta(days=7)
        except ValueError:
            return f"Invalid end_date format: '{end_str}'. Use YYYY-MM-DD.", False

        # Attach timezone so isoformat() includes the UTC offset
        if user_tz:
            start = start.replace(tzinfo=user_tz)
            end = end.replace(tzinfo=user_tz)
        else:
            start = start.astimezone()
            end = end.astimezone()

        # End should be end of day
        end = end.replace(hour=23, minute=59, second=59)

        data, err = _api_get(token, f'/calendars/{calendar_id}/events', {
            'timeMin': start.isoformat(),
            'timeMax': end.isoformat(),
            'timeZone': tz,
            'singleEvents': 'true',
            'orderBy': 'startTime',
            'maxResults': 100,
        })
        if err:
            return err, False

        events = data.get('items', [])

        # Group by day
        days = {}
        for event in events:
            e_start = event.get('start', {})
            date_str = e_start.get('dateTime', e_start.get('date', ''))[:10]
            days.setdefault(date_str, []).append(event)

        lines = [f"Schedule: {start.strftime('%b %d')} – {end.strftime('%b %d')}"]
        total_events = 0

        # Walk each day in the range, show events or "free"
        current = start
        while current <= end:
            date_key = current.strftime('%Y-%m-%d')
            day_label = current.strftime('%A %b %d')
            if date_key in days:
                lines.append(f"\n{day_label}:")
                for event in days[date_key]:
                    summary = event.get('summary', '(No title)')
                    event_id = event.get('id', '')
                    e_start = event.get('start', {})
                    e_end = event.get('end', {})
                    if e_start.get('dateTime'):
                        start_time = _format_time(e_start['dateTime'])
                        end_time = _format_time(e_end.get('dateTime', ''))
                        lines.append(f"  {start_time}–{end_time}  {summary}  (id: {event_id})")
                    else:
                        lines.append(f"  All day  {summary}  (id: {event_id})")
                    total_events += 1
            else:
                lines.append(f"\n{day_label}:\n  No events — free all day")
            current += timedelta(days=1)

        lines.append(f"\n{total_events} event{'s' if total_events != 1 else ''} total")
        return '\n'.join(lines), True

    elif function_name == 'calendar_add':
        title = arguments.get('title', '').strip()
        start_str = arguments.get('start', '').strip()
        end_str = arguments.get('end', '').strip()
        description = arguments.get('description', '').strip()

        if not title:
            return "Event title is required.", False
        if not start_str:
            return "Start time is required.", False

        # Build event body
        event = {'summary': title}
        if description:
            event['description'] = description

        is_all_day = 'T' not in start_str

        if is_all_day:
            event['start'] = {'date': start_str}
            if end_str and 'T' not in end_str:
                # Google's all-day end date is exclusive, add 1 day
                try:
                    end_dt = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(days=1)
                    event['end'] = {'date': end_dt.strftime('%Y-%m-%d')}
                except ValueError:
                    event['end'] = {'date': start_str}
            else:
                # Single all-day: end = start + 1 day
                try:
                    end_dt = datetime.strptime(start_str, '%Y-%m-%d') + timedelta(days=1)
                    event['end'] = {'date': end_dt.strftime('%Y-%m-%d')}
                except ValueError:
                    return f"Invalid date format: '{start_str}'. Use YYYY-MM-DD.", False
        else:
            tz = _get_local_tz()
            # Normalize to full ISO (YYYY-MM-DDTHH:MM:SS)
            try:
                start_dt = datetime.fromisoformat(start_str)
            except ValueError:
                return f"Invalid datetime format: '{start_str}'. Use YYYY-MM-DDTHH:MM.", False
            event['start'] = {'dateTime': start_dt.isoformat(), 'timeZone': tz}
            if end_str and 'T' in end_str:
                try:
                    end_dt = datetime.fromisoformat(end_str)
                except ValueError:
                    return f"Invalid datetime format: '{end_str}'. Use YYYY-MM-DDTHH:MM.", False
                event['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': tz}
            else:
                # Default: 1 hour after start
                end_dt = start_dt + timedelta(hours=1)
                event['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': tz}

        data, err = _api_post(token, f'/calendars/{calendar_id}/events', event)
        if err:
            return err, False

        # Format confirmation
        e_start = data.get('start', {})
        if e_start.get('dateTime'):
            start_display = _format_time(e_start['dateTime'])
            e_end = data.get('end', {})
            end_display = _format_time(e_end.get('dateTime', ''))
            try:
                day = datetime.fromisoformat(e_start['dateTime'].replace('Z', '+00:00'))
                day_str = day.strftime('%A %b %d')
            except Exception:
                day_str = ''
            return f"Added: \"{title}\" — {day_str}, {start_display}–{end_display}\n(id: {data.get('id', '')})", True
        else:
            return f"Added: \"{title}\" — all day event\n(id: {data.get('id', '')})", True

    elif function_name == 'calendar_delete':
        event_id = arguments.get('event_id', '').strip().lstrip('#')
        if not event_id:
            return "Event ID is required. Use calendar_today or calendar_range to find IDs.", False
        # Resolve short ID (#1, #2) to real Google ID
        event_id = _id_map.get(event_id, event_id)

        _, err = _api_delete(token, f'/calendars/{calendar_id}/events/{event_id}')
        if err:
            return err, False

        return f"Deleted event {event_id}.", True

    return f"Unknown function: {function_name}", False


def _get_local_tz():
    """Get local IANA timezone name (e.g. America/New_York)."""
    try:
        # Prefer Sapphire's configured timezone
        import config as cfg
        tz_name = getattr(cfg, 'USER_TIMEZONE', '') or ''
        if tz_name and tz_name != 'UTC':
            return tz_name
        # Python 3.9+: tzinfo.key gives IANA name
        tz = datetime.now().astimezone().tzinfo
        if hasattr(tz, 'key'):
            return tz.key
        # Fallback: read from system
        from pathlib import Path
        tz_link = Path('/etc/localtime')
        if tz_link.is_symlink():
            target = str(tz_link.resolve())
            if 'zoneinfo/' in target:
                return target.split('zoneinfo/')[-1]
    except Exception:
        pass
    return 'UTC'
