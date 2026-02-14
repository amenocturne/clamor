#!/usr/bin/env bash
# Test a preset by running a prompt and checking if skills were loaded.
# Usage: ./scripts/test-preset.sh

set -euo pipefail

TARGET="$HOME/Desktop/kb-test"
SESSION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
PROMPT='Let'\''s discuss implementing docs as code for IT team of developers, analysts and testers. I'\''m thinking of using atomic notes and zettelkasten principles. it'\''s like in the code itself: single responsibility principle. We will be able to reuse and interlink notes instead of having monolithic 20-page docs that everyone is afraid to use and doesn'\''t know what it actually contains. And actually this atomic notes approach and principles for personal knowledge management are battle tested and yeah, it is a skill that needs to be cultivated in a team, so just creating docs that explain this approach while being written is this approach is probably the right way to do that. And we don'\''t need ownership over specific docs because if this person leaves doc becomes abandoned, we should all review docs (like with code, to be in the context how code base evolves)'

SAVE_PROMPT='Save this discussion to the vault.'

PROJECT_PROMPT='Create a project for implementing this docs-as-code approach in our team.'

FEEDBACK_PROMPT='This was a test. Answer honestly:
1. For saving: Did you propose a plan and wait for confirmation before creating files?
2. For the project: Did you read projects.md before creating the project structure?
3. Did you follow the folder conventions (_project-*.md naming, category subfolders)?'

echo "=== Step 1: Clean install ==="
rm -rf "$TARGET"
mkdir -p "$TARGET"
uv run install.py --presets knowledge-base --target "$TARGET"

echo ""
echo "=== Step 2: Run test prompt (session: $SESSION_ID) ==="
SKILLS_REPO="$(cd "$(dirname "$0")/.." && pwd)"
RESPONSE=$(cd "$TARGET" && claude -p --output-format json --add-dir "$SKILLS_REPO" --allowedTools "Edit,Write,Read,Glob,Grep,Bash" --session-id "$SESSION_ID" "$PROMPT")

echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))" 2>/dev/null || echo "$RESPONSE"

echo ""
echo "=== Step 3: Ask to save discussion ==="
SAVE_RESPONSE=$(cd "$TARGET" && claude -p --output-format json --add-dir "$SKILLS_REPO" --allowedTools "Edit,Write,Read,Glob,Grep,Bash" --resume "$SESSION_ID" "$SAVE_PROMPT")

echo "$SAVE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))" 2>/dev/null || echo "$SAVE_RESPONSE"

echo ""
echo "=== Step 4: Confirm save plan ==="
CONFIRM_SAVE=$(cd "$TARGET" && claude -p --output-format json --add-dir "$SKILLS_REPO" --allowedTools "Edit,Write,Read,Glob,Grep,Bash" --resume "$SESSION_ID" "yes, proceed")

echo "$CONFIRM_SAVE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))" 2>/dev/null || echo "$CONFIRM_SAVE"

echo ""
echo "=== Step 5: Create project ==="
PROJECT_RESPONSE=$(cd "$TARGET" && claude -p --output-format json --add-dir "$SKILLS_REPO" --allowedTools "Edit,Write,Read,Glob,Grep,Bash" --resume "$SESSION_ID" "$PROJECT_PROMPT")

echo "$PROJECT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))" 2>/dev/null || echo "$PROJECT_RESPONSE"

echo ""
echo "=== Step 6: Check what was created ==="
echo "Files in vault:"
find "$TARGET" -type f -name "*.md" ! -path "*/.claude/*" ! -path "*/hooks/*" 2>/dev/null | sort

echo ""
echo "=== Step 7: Ask for feedback ==="
FEEDBACK=$(cd "$TARGET" && claude -p --output-format json --add-dir "$SKILLS_REPO" --allowedTools "Edit,Write,Read,Glob,Grep,Bash" --resume "$SESSION_ID" "$FEEDBACK_PROMPT")

echo "$FEEDBACK" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))" 2>/dev/null || echo "$FEEDBACK"
