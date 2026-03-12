---
name: shh
description: Kill TTS playback immediately. Optionally turn off voice mode. Triggers on "shh", "quiet", "stop talking", "shut up", "tts off", "mute", "/shh".
author: amenocturne
---

# Stop TTS Playback

Immediately kill any running text-to-speech playback.

## Action

Run this immediately — no confirmation needed, no preamble:

```bash
kill "$(cat ~/.claude/tts.pid 2>/dev/null)" 2>/dev/null; rm -f ~/.claude/tts.pid
```

If the user also wants to disable voice mode entirely (said "tts off", "stop talking", "quiet mode"), also run:

```bash
rm -f ~/.claude/tts-active
```

And return to normal markdown response style.

Otherwise, keep voice mode active — the user just wanted to skip the current speech.

## Response

Keep it minimal. If voice mode is still on: "Stopped." If voice mode was turned off: "Voice mode off."
