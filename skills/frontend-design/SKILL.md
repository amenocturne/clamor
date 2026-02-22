---
name: frontend-design
description: Frontend development with TypeScript, Snabbdom, and Elm Architecture. Use when building web UI, designing pages, discussing website design, planning UI/UX, or working on frontend code. Triggers on "frontend", "website design", "UI design", "page layout", "web app design", "design the frontend".
author: amenocturne
---

# Frontend Design & Development

Create distinctive, production-grade interfaces with TypeScript + Snabbdom + Elm Architecture.

## Stack

| Layer | Tool |
|-------|------|
| Runtime | Bun |
| UI | Snabbdom |
| Graphics | PixiJS (when needed) |
| Formatter | Biome |
| Bundler | Bun |
| Tests | bun:test |

## Commands

```bash
just install     # bun install
just dev         # bun run dev
just build       # bun build
just test        # bun test
just fix         # biome check --apply .
just typecheck   # tsc --noEmit
```

## Design Philosophy

### Theme Follows Purpose + Identity

Don't apply generic styles. Understand the context and commit to a **bold aesthetic direction**:

- **Purpose**: What problem does this solve? Who uses it? How often?
- **Tone**: Pick a direction and commit fully (brutally minimal, maximalist chaos, retro-futuristic, organic, luxury, playful, editorial, brutalist, art deco, cyberpunk, etc.)
- **Differentiation**: What makes this UNFORGETTABLE?

### Interactions Serve the Use Case

- **Entertainment apps**: Rich animations, sounds, micro-interactions
- **Utility apps**: Fast, responsive, no-nonsense
- Match complexity to aesthetic vision

## Aesthetics Guidelines

- **Typography**: Distinctive and characterful, not Inter/Roboto/Arial
- **Color**: Dominant colors with sharp accents, CSS variables for consistency
- **Motion**: CSS-first animations, PixiJS for complex graphics
- **Composition**: Break the grid when it serves design, generous negative space OR controlled density

## TypeScript Conventions

```typescript
// Pure functions, no classes
const processItem = (item: Item): ProcessedItem => ({ ... })

// Explicit return types
const calculate = (x: number, y: number): number => x + y

// Readonly for immutability
type Model = {
  readonly items: readonly Item[]
  readonly selected: string | null
}

// Discriminated unions for messages
type Msg =
  | { type: 'select'; id: string }
  | { type: 'clear' }
  | { type: 'load'; items: Item[] }

// No any, use unknown and narrow
const parse = (data: unknown): Item | null => {
  if (isItem(data)) return data
  return null
}
```

## Elm Architecture

### Structure

```
src/
├── model.ts      # Types and initial state
├── update.ts     # Pure state transitions
├── view.ts       # VNode rendering
├── app.ts        # Snabbdom setup, patch loop
└── main.ts       # Entry point, side effects
```

### Pattern

```typescript
// Model (State)
type Model = {
  readonly items: readonly Item[]
  readonly filter: string
  readonly loading: boolean
}

// Update (Pure Transitions)
const update = (model: Model, msg: Msg): Model => {
  switch (msg.type) {
    case 'setFilter':
      return { ...model, filter: msg.value }
    case 'loadItems':
      return { ...model, items: msg.items, loading: false }
  }
}

// View (Pure Rendering)
const view = (model: Model, dispatch: (msg: Msg) => void): VNode =>
  h('div.container', [
    h('input', {
      props: { value: model.filter },
      on: { input: (e) => dispatch({ type: 'setFilter', value: e.target.value }) }
    }),
    h('ul', model.items.map(item => itemView(item, dispatch)))
  ])
```

### App Loop

```typescript
import { init, h } from 'snabbdom'

const patch = init([/* modules */])
let model = initialModel
let vnode = document.getElementById('app')!

const dispatch = (msg: Msg) => {
  model = update(model, msg)
  const newVnode = view(model, dispatch)
  vnode = patch(vnode, newVnode)
}

vnode = patch(vnode, view(model, dispatch))
```

## CSS Patterns

```css
:root {
  --color-bg: #1a1a2e;
  --color-text: #eee;
  --color-accent: #ff6b6b;
  --font-body: system-ui, sans-serif;
  --space-unit: 8px;
}

/* Component scoping via BEM-lite */
.card { }
.card-header { }
.card--selected { }
```

- CSS variables for everything themeable
- No CSS frameworks (no Tailwind, no Bootstrap)

## Minimal Dependencies

**Add packages for:**
- Snabbdom, PixiJS, d3.js, crypto libraries

**Implement yourself:**
- Small utilities (debounce, throttle), date formatting (use Intl), array helpers

**Avoid entirely:**
- React, Vue, Angular, Tailwind, Bootstrap, Lodash

## Process

1. **Clarify purpose**: What's it for? Who uses it?
2. **Explore inspirations**: What has the right vibe?
3. **Visual demo first**: Static HTML/CSS before functional implementation
4. **Align on vision**: What's unforgettable about this?

## Testing

```typescript
import { expect, test, describe } from 'bun:test'

describe('update', () => {
  test('setFilter updates filter', () => {
    const model = { filter: '', items: [] }
    const result = update(model, { type: 'setFilter', value: 'test' })
    expect(result.filter).toBe('test')
  })
})
```

Test pure functions (update, helpers). UI requires manual testing.

## Anti-patterns

**Design:**
- Default fonts (Inter, Roboto, Arial)
- Generic palettes (purple gradients, generic blue)
- Jumping to implementation without design discussion

**Technical:**
- Mutating state directly
- Side effects in update or view
- Using `any` type
- CSS frameworks
