# Link Proxy

URL masking hook for Claude Code. Transforms internal URLs to placeholders before Claude sees them, and restores them when writing files.

## Use Case

When working in environments where an LLM proxy masks URLs in API traffic, but files on disk contain real URLs. This hook ensures Claude can read/edit files without corrupting URLs.

## Setup

1. Copy `domains.txt.template` to `domains.txt`
2. Add your internal domains (one per line)
3. Configure hooks in your project's `.claude/settings.json`

## Configuration

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "path/to/link-proxy/hook.sh pre-tool-use",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "path/to/link-proxy/hook.sh post-tool-use",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "path/to/link-proxy/hook.sh stop",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## How It Works

Uses **in-place file transformation** to avoid Claude Code's file tracking issues:

1. User configures internal domains in `domains.txt`
2. On `PreToolUse` (Read): Transform URLs to placeholders **in the original file**
3. Claude reads the file normally (file is marked as "read")
4. On `PreToolUse` (Edit): Restore URLs in `new_string` if it contains placeholders
5. On `PostToolUse` (Edit): Re-transform any new URLs introduced by the edit
6. On `PreToolUse` (Write): Restore URLs in content before writing
7. On `Stop`: Restore all transformed files to original state (URLs restored)

## Data

- `data/mappings.json` - Global URL→hash mappings (shared across sessions)
- `data/sessions/{id}.json` - Per-session list of transformed files

## TODO

### Phase 3: PHONE + DATE (no external deps)

**PHONE** — skip the `phonenumbers` lib, use simplified regex only. Port `PhoneDigitsDetector` from anon:
```python
# Matches +7/8 followed by 10 digits, with optional spaces/dashes/parens
_NUMBER_REGEX = re.compile(r"\+?[78](?:\s*\d){10}(?!\d)")
_CLEAR_RE = re.compile(r"[()\-,;]")  # normalise before matching
# Placeholder: [Phone_hash8]
# Note: higher FP rate than anon's full detector (which uses phonenumbers lib) — acceptable
```

**DATE** — all 17 patterns from anon's `date_regular.py`, joined as alternation, compiled with `re.IGNORECASE`:
```python
DATE_REGEX_PATTERNS = [
    # verbal Russian ordinals + month names (e.g. "двадцать первого января две тысячи...")
    r"\b(?:((((двадцать|тридцать)\s+)?((перв|втор|четверт|пят|шест|седьм|восьм|девят)(?:ое|ого|ому|ым|ом)|(треть(?:е|его|ему|им|ем))))|((одиннадцат|двенадцат|тринадцат|четырнадцат|пятнадцат|шестнадцат|семнадцат|восемнадцат|девятнадцат|десят|двадцат|тридцат)(?:ое|ого|ому|ым|ом))))\s+(?:((?:январ|феврал|апрел|июн|июл|сентябр|октябр|ноябр|декабр)(?:ь|я|ю|ем|ём|е)|(?:март|август)(?:а|ю|у|ом|е|)|(?:ма)(?:й|я|ю|ем|е)))(?:(\s+(?:две\s+тысячи|(одна\s+)?тысяча\s+девятьсот))?((((\s+(?:(?:девяносто|восьмидесято|семидесято|шестидесято|пятидесято|сороково|тридцато|двадцато|десято|одиннадцато|двенадцато|тринадцато|четырнадцато|пятнадцато|шестнадцато|семнадцато|восемнадцато|девятнадцато)|(?:((?:девяносто|восемьдесят|семьдесят|шестьдесят|пятьдесят|сорок|тридцать|двадцать)\s+)?(?:перво|второ|третье|четверто|пято|шесто|седьмо|восьмо|девято))|двухтысячно)го))(?!\s+(?:((?:январ|феврал|апрел|июн|июл|сентябр|октябр|ноябр|декабр)(?:ь|я|ю|ем|ём|е)|(?:март|август)(?:а|ю|у|ом|е|)|(?:ма)(?:й|я|ю|ем|е))))))(?:\s+года)?)?\b",
    # month name + ordinal year (e.g. "января двухтысячного")
    r"\b(?:(?:январ|феврал|апрел|июн|июл|сентябр|октябр|ноябр|декабр)(?:ь|я|ю|ем|ём|е)|(?:март|август)(?:а|ю|у|ом|е|)|(?:ма)(?:й|я|ю|ем|е))((((\s+(?:две\s+тысячи|(одна\s+)?тысяча\s+девятьсот))?(\s+(?:(?:девяностого|восьмидесятого|семидесятого|шестидесятого|пятидесятого|сорокового|тридцатого|двадцатого|десятого|одиннадцатого|двенадцатого|тринадцатого|четырнадцатого|пятнадцатого|шестнадцатого|семнадцатого|восемнадцатого|девятнадцатого)|(?:((?:девяносто|восемьдесят|семьдесят|шестьдесят|пятьдесят|сорок|тридцать|двадцать)\s+)?(?:первого|второго|третьего|четвертого|пятого|шестого|седьмого|восьмого|девятого))|двухтысячного))(?:\s+года)?)))\b",
    # month name + 4-digit year (e.g. "января 2024 года")
    r"\b(?:(?:январ|феврал|апрел|июн|июл|сентябр|октябр|ноябр|декабр)(?:ь|я|ю|ем|ём|е)|(?:март|август)(?:а|ю|у|ом|е|)|(?:ма)(?:й|я|ю|ем|е))(?:\s+(?:\d{4})(?:\s+года)?)\b",
    # digit + month name (e.g. "1 января 2024")
    r"\b\d{1,2}(?:его|ого|ому|ему|ье|ое|го|му|ым|им|ом|ем|м|о|е)?\s+(?:(?:январ|феврал|апрел|июн|июл|сентябр|октябр|ноябр|декабр)(?:ь|я|ю|ем|ём|е)|(?:март|август)(?:а|ю|у|ом|е|)|(?:ма)(?:й|я|ю|ем|е))(?:\s+(?:\d{4})(?:\s+года)?)?\b",
    r"\b\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})\b",   # 01.01.2024
    r"\b(?:\d{4}|\d{2})\.\d{1,2}\.\d{1,2}\b",   # 2024.01.01
    r"\b\d{1,2}\-\d{1,2}\-(?:\d{4}|\d{2})\b",   # 01-01-2024
    r"\b(?:\d{4}|\d{2})\-\d{1,2}\-\d{1,2}\b",   # 2024-01-01
    r"\b\d{1,2}\/\d{1,2}\/(?:\d{4}|\d{2})\b",   # 01/01/2024
    r"\b(?:\d{4}|\d{2})\/\d{1,2}\/\d{1,2}\b",   # 2024/01/01
    r"\b\d{1,2}\.\d{1,2}\b",                     # 01.01
    r"\b\d{1,2}\-\d{1,2}\b",                     # 01-01
    r"\b\d{1,2}\-\d{1,2}\b",                     # 01-01 (duplicate in source)
    r"\b\d{1,2}\/\d{1,2}\b",                     # 01/01
    r"\b\d{1,2}\.\d{4}\b",                       # 01.2024
    r"\b\d{1,2}\-\d{4}\b",                       # 01-2024
    r"\b\d{1,2}\/\d{4}\b",                       # 01/2024
]
# Joined: r"(?:(?:pat1)|(?:pat2)|...)" compiled with re.IGNORECASE
# Placeholder: [Date_hash8]
# WARNING: short patterns (01.01, 01-01) will have high FP rate — consider skipping last 7
```

### Phase 4: NAME/SURNAME/PATRONYMIC + ADDRESS (natasha)

Add `natasha` to `pyproject.toml` deps. At startup, initialise once:
```python
from natasha import Segmenter, MorphVocab, NewsEmbedding, NewsNERTagger, Doc
segmenter = Segmenter()
emb = NewsEmbedding()
ner_tagger = NewsNERTagger(emb)
morph_vocab = MorphVocab()

def extract_ner(text, types):  # types e.g. {'PER', 'LOC'}
    doc = Doc(text)
    doc.segment(segmenter)
    doc.tag_ner(ner_tagger)
    return [(span.start, span.stop, span.type) for span in doc.spans if span.type in types]
# PER → NAME/SURNAME/PATRONYMIC placeholder, LOC → Address placeholder
# Natasha F1: PER=99%, LOC=98% on news text
```
