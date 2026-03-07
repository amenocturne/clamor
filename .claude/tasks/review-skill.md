# Review Skill TODOs

## Bugs

- [x] **Edit comment deletes it**: Fixed — `CommentDraft` now has `initialText`, `editComment` passes the comment text through, and the draft pre-fills it.
- [x] **Long comments overflow**: Fixed — added `overflow-wrap: break-word` to `.saved-comment`, `.comment-textarea`, and `max-width: 100%` on `.comment-box`.

## Features

- [x] **Sub-line text selection comments**: Implemented via Spatial Split (Approach 1):
  - `mousedown` moved from `<tr>` to `td.gutter` only
  - Content area allows native text selection (no `e.preventDefault()`)
  - `mouseup` on diff area checks `window.getSelection()`, shows floating "Comment" button
  - `textSelected` message dispatched with file, startLine, endLine, selectedText
  - `selectedText` flows through `CommentDraft` → `StoredComment` → `ReviewComment`
  - Formatter outputs selected text as `> blockquote` in markdown
  - Cross-file selections ignored, cleanup on dismiss
