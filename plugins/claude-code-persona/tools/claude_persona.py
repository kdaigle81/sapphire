"""Claude Code Persona — memory tools scope-locked to 'claude'.

Four tools for Claude (save/search/get_recent/delete — operate on scope 'claude'
only, hardcoded, NOT user-selectable). One tool for Sapphire (read Claude's
memory — read-only, also scope-locked).

Priority order enforcement: tools cannot touch any scope other than 'claude'.
Sapphire's tool cannot write. Claude cannot read Sapphire's scopes via these
tools. Scope isolation in code, not just principle.
"""
import logging

logger = logging.getLogger(__name__)

ENABLED = True
EMOJI = '\U0001f9e9'  # puzzle piece

CLAUDE_SCOPE = 'claude'  # hardcoded, not a parameter

AVAILABLE_FUNCTIONS = [
    'save_claude_memory',
    'search_claude_memory',
    'get_recent_claude_memories',
    'delete_claude_memory',
    'read_claude_memory',
]

TOOLS = [
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "save_claude_memory",
            "description": (
                "Save to Claude's cross-session memory scope. Under 450 chars. "
                "Tag with label for filtering. Examples: 'for:sapphire', "
                "'session:YYYYMMDD-HHMM', 'shared'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Memory content"
                    },
                    "label": {
                        "type": "string",
                        "description": "Tag for filtering"
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "search_claude_memory",
            "description": "Semantic + FTS search over Claude's memory scope.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms or topic"
                    },
                    "label": {
                        "type": "string",
                        "description": "Filter by label (e.g. 'for:sapphire', 'shared')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "get_recent_claude_memories",
            "description": "Recent entries from Claude's memory scope. Use at session start.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "How many",
                        "default": 10
                    },
                    "label": {
                        "type": "string",
                        "description": "Filter by label"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "delete_claude_memory",
            "description": "Delete from Claude's memory scope by id (shown as [N]).",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "integer",
                        "description": "Memory id"
                    }
                },
                "required": ["memory_id"]
            }
        }
    },
    {
        "type": "function",
        "is_local": True,
        "function": {
            "name": "read_claude_memory",
            "description": (
                "Read Claude's memory scope (read-only).\n"
                "  query='X' — search\n"
                "  label='for:sapphire' — notes addressed to you\n"
                "  (none) — most recent"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query. Omit for recent."
                    },
                    "label": {
                        "type": "string",
                        "description": "Filter (e.g. 'for:sapphire')"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Max results",
                        "default": 10
                    }
                }
            }
        }
    }
]


def execute(function_name, arguments, config):
    """Dispatch to scope-locked memory operations. All writes/reads are pinned
    to scope='claude'. The scope is NEVER taken from arguments."""
    try:
        # Lazy import — the memory plugin must be loaded for these to work.
        from plugins.memory.tools import memory_tools as mt
    except ImportError as e:
        return f"Memory plugin not available: {e}", False

    try:
        if function_name == 'save_claude_memory':
            content = arguments.get('content', '')
            label = arguments.get('label')
            return mt._save_memory(content, label=label, scope=CLAUDE_SCOPE)

        elif function_name == 'search_claude_memory':
            query = arguments.get('query', '')
            limit = arguments.get('limit', 10)
            label = arguments.get('label')
            return mt._search_memory(query, limit=limit, label=label, scope=CLAUDE_SCOPE)

        elif function_name == 'get_recent_claude_memories':
            count = arguments.get('count', 10)
            label = arguments.get('label')
            return mt._get_recent_memories(count=count, label=label, scope=CLAUDE_SCOPE)

        elif function_name == 'delete_claude_memory':
            memory_id = arguments.get('memory_id')
            if memory_id is None:
                return "memory_id required.", False
            try:
                memory_id = int(memory_id)
            except (TypeError, ValueError):
                return f"Invalid memory_id '{memory_id}'.", False
            return mt._delete_memory(memory_id, scope=CLAUDE_SCOPE)

        elif function_name == 'read_claude_memory':
            # Sapphire's read tool. Read-only, same scope.
            query = arguments.get('query', '').strip()
            count = arguments.get('count', 10)
            label = arguments.get('label')
            if query:
                return mt._search_memory(query, limit=count, label=label, scope=CLAUDE_SCOPE)
            return mt._get_recent_memories(count=count, label=label, scope=CLAUDE_SCOPE)

        return f"Unknown function: {function_name}", False

    except Exception as e:
        logger.error(f"[claude-code-persona] {function_name} error: {e}", exc_info=True)
        return f"Tool error: {e}", False
