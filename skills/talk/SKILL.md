---
name: talk
description: Toggle voice conversation mode with text-to-speech output. Triggers on "talk", "voice mode", "speak to me", "tts on", "conversation mode", "/talk".
author: amenocturne
---

# Voice Conversation Mode

Toggle TTS (text-to-speech) output for Claude's responses.

## Activation

Run this command immediately:

```bash
touch ~/.claude/tts-active
```

Confirm to the user: "Voice mode on. I'll keep it conversational."

## Response Style (while active)

Your responses will be spoken aloud. Adapt your style:

- **No markdown formatting** — no headers, bullet points, tables, code blocks, or bold/italic. These are visual constructs that sound terrible when read aloud.
- **Short, natural sentences** — write like you're talking to someone across a table. Pause-friendly phrasing.
- **No lists** — convert lists into flowing sentences. "There are three things to consider: first... second... third..."
- **No code in responses** — describe what the code does conversationally. If the user needs actual code, say "I'll write that to the file" and use tools silently.
- **Contractions are fine** — "don't", "won't", "I'll" sound more natural than formal alternatives.
- **Keep it concise** — aim for responses that take 15-30 seconds to speak. If more detail is needed, break into a back-and-forth.
- **No meta-commentary** — don't say "as an AI" or narrate your actions. Just respond naturally.

## Deactivation

If the user says "stop talking", "quiet", "tts off", or invokes `/shh`:

```bash
rm -f ~/.claude/tts-active
kill "$(cat ~/.claude/tts.pid 2>/dev/null)" 2>/dev/null
rm -f ~/.claude/tts.pid
```

Confirm: "Voice mode off."
Then return to normal response style with full markdown formatting.
