# Plugin Themes

Plugins can ship custom themes with CSS styling, animated JS backgrounds, and user-configurable settings. Themes appear in **Settings > Visual** as clickable cards with color previews.

## Quick Start

Add themes to your plugin manifest and provide CSS + optional JS files.

### plugin.json

```json
{
  "name": "my-theme-pack",
  "capabilities": {
    "themes": [
      {
        "id": "cyberpunk",
        "name": "Cyberpunk",
        "icon": "⚡",
        "description": "Neon city vibes with rain effects",
        "css": "web/themes/cyberpunk/cyberpunk.css",
        "scripts": ["web/themes/cyberpunk/rain.js"],
        "preview": {
          "bg": "#0a0a1a",
          "accent": "#ff00ff",
          "text": "#e0e0ff"
        },
        "settings": [
          {
            "key": "cyberpunk-rain-mode",
            "type": "select",
            "label": "Rain Effect",
            "default": "ambient",
            "options": [
              {"value": "off", "label": "Off"},
              {"value": "ambient", "label": "Ambient"},
              {"value": "reactive", "label": "Reactive"}
            ]
          }
        ]
      }
    ]
  }
}
```

### File Structure

```
plugins/my-theme-pack/
  plugin.json
  web/
    themes/
      cyberpunk/
        cyberpunk.css     # CSS variables + custom styles
        rain.js           # Optional animated background
        texture.png       # Optional assets
```

## Theme CSS

Theme CSS files override Sapphire's CSS variables. Wrap everything in a `[data-theme="your-id"]` selector:

```css
[data-theme="cyberpunk"] {
    --bg: #0a0a1a;
    --bg-secondary: #12122a;
    --text: #e0e0ff;
    --text-muted: #8888aa;
    --trim: #ff00ff;
    --accent: #ff00ff;
    --border: #333366;
    /* ... full variable list in any core theme for reference */
}
```

See `static/themes/dark.css` for the complete list of CSS variables.

## Preview Colors

The `preview` object controls the color swatch shown in the theme picker card:

```json
{
  "bg": "#0a0a1a",      // Background color (leftmost bar)
  "bg2": "#12122a",     // Secondary background (optional, auto-derived if missing)
  "text": "#e0e0ff",    // Text color
  "accent": "#ff00ff",  // Accent/trim color
  "border": "#333366"   // Border color (optional)
}
```

## Animated Backgrounds (JS)

Theme scripts are loaded as `<script>` tags when the theme is activated and removed when switching away. Use an IIFE to avoid polluting the global scope:

```js
(function() {
    'use strict';

    const canvas = document.createElement('canvas');
    canvas.id = 'cyberpunk-bg';
    canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;';
    document.body.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    let animId;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    function draw() {
        // Your animation logic here
        animId = requestAnimationFrame(draw);
    }

    resize();
    window.addEventListener('resize', resize);
    draw();

    // Cleanup when theme changes — check periodically
    const cleanup = setInterval(() => {
        if (!document.querySelector(`script[data-theme-script="cyberpunk"]`)) {
            cancelAnimationFrame(animId);
            window.removeEventListener('resize', resize);
            canvas.remove();
            clearInterval(cleanup);
        }
    }, 1000);
})();
```

### Reacting to Sapphire Events

Your background JS can react to AI activity:

```js
// Sapphire publishes these on the event bus (SSE)
window.addEventListener('sapphire-theme-event', e => {
    const { type } = e.detail;
    // type: 'thinking', 'speaking', 'idle', 'tool_call'
});
```

## Theme Settings

Declare settings that users can configure per-theme. Settings appear in a panel below the theme picker when the theme is active.

### Setting Types

**Select (dropdown)**
```json
{
  "key": "cyberpunk-rain-mode",
  "type": "select",
  "label": "Rain Effect",
  "help": "Controls the animated rain overlay",
  "default": "ambient",
  "options": [
    {"value": "off", "label": "Off"},
    {"value": "ambient", "label": "Ambient"},
    {"value": "reactive", "label": "Reactive"}
  ]
}
```

Options can also be simple strings: `"options": ["low", "medium", "high"]`

**Boolean (checkbox)**
```json
{
  "key": "cyberpunk-scanlines",
  "type": "boolean",
  "label": "Scanlines",
  "help": "CRT scanline overlay effect",
  "default": "true"
}
```

**Range (slider)**
```json
{
  "key": "cyberpunk-intensity",
  "type": "range",
  "label": "Rain Intensity",
  "min": 1,
  "max": 10,
  "step": 1,
  "default": "5"
}
```

**Text (freeform)**
```json
{
  "key": "cyberpunk-custom-color",
  "type": "text",
  "label": "Custom Accent",
  "help": "Hex color code",
  "default": "#ff00ff"
}
```

### How Settings Work

- All settings are stored in **localStorage** with the key you specify
- Your theme JS reads them via `localStorage.getItem('cyberpunk-rain-mode')`
- The Sapphire settings panel reads/writes the same keys — zero bridging needed
- Changes fire a custom event for instant reactivity:

```js
window.addEventListener('sapphire-theme-setting', e => {
    const { key, value } = e.detail;
    if (key === 'cyberpunk-rain-mode') {
        setRainMode(value);  // Update live without reload
    }
});
```

### Chat Style Settings

A common pattern is "frosted glass" chat messages. If your setting key matches `*-chat-style`, Sapphire automatically sets a `data-{theme}-chat` attribute on the document element:

```json
{"key": "cyberpunk-chat-style", "type": "select", "label": "Chat Style", "default": "transparent",
 "options": [{"value": "transparent", "label": "Transparent"}, {"value": "glass", "label": "Frosted Glass"}]}
```

Then in your CSS:
```css
[data-cyberpunk-chat="glass"] .message-content {
    background: rgba(10, 10, 26, 0.6);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 0, 255, 0.2);
}
```

## Legacy Theme Plugins

If your theme plugin exposes themes via `window.sapphireThemes.getAll()` instead of the manifest format, Sapphire will still discover and display them. Settings are supported if each theme object includes a `settings` array.

This is the backwards-compatible path — new themes should use the manifest format.

## Tips

- Use Sapphire's CSS variables (`var(--bg)`, `var(--text)`, etc.) in your theme CSS so elements inherit properly
- Core themes in `static/themes/` are good references for the full variable list
- Animated backgrounds should use `z-index: -1` and `pointer-events: none`
- Always provide a cleanup mechanism in your JS (canvas removal, interval clearing)
- Keep performance in mind — offer a performance tier setting so users on slow machines can dial it down
- Test with both light and dark base themes to ensure your variables cover everything
