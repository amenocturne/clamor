---
name: frontend
description: Frontend development — stack, architecture, design, and production readiness. Use when building web UI, designing pages, planning UI/UX, working on frontend code, or preparing for launch. Triggers on "frontend", "website design", "UI design", "page layout", "web app design", "design the frontend", "pre-launch", "ship it".
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

## Pre-Launch Checklist

Apply before shipping to production. Priority: **High** = must fix, **Medium** = strongly recommended, **Low** = nice to have.

### HTML Head

**High:**
- `<!doctype html>` at top
- `<meta charset="utf-8">` first in `<head>`
- `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">`
- `<title>` on every page (under 55 characters)
- `<meta name="description">` unique per page (under 150 characters)
- CSS loaded before JS in `<head>`

**Medium:**
- Favicon as `.png` or `.svg` (not just `.ico`)
- `<link rel="canonical">` to prevent duplicate content
- Critical CSS inlined in `<style>` for above-the-fold content

**Low:**
- `<link rel="apple-touch-icon">` (200x200px minimum)
- RSS feed if content-driven

### Social Meta

```html
<!-- Open Graph -->
<meta property="og:type" content="website">
<meta property="og:url" content="https://example.com/page">
<meta property="og:title" content="Page Title">
<meta property="og:description" content="Description">
<meta property="og:image" content="https://example.com/og.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">

<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Page Title">
<meta name="twitter:description" content="Description">
<meta name="twitter:image" content="https://example.com/og.jpg">
```

OG images: minimum 600x315, recommended 1200x630.

### Semantic HTML & Accessibility

**High:**
- `<html lang="en">` (correct language)
- HTML5 semantic elements (`<header>`, `<main>`, `<nav>`, `<section>`, `<footer>`)
- Single `<h1>` per page, heading hierarchy H1-H6 in order
- Every `<img>` has meaningful `alt` text
- Every form input has a `<label>` (or `aria-label`)
- Keyboard navigation works for all interactive elements
- Focus styles visible (never `outline: none` without replacement)
- Error 404 and 5xx pages exist (with CSS inlined, no external deps)

**Medium:**
- Color contrast passes WCAG AA (4.5:1 for text, 3:1 for large text)
- `<html dir="rtl">` if RTL languages supported
- Screen reader tested (VoiceOver on Mac)
- HTML5 input types used (`email`, `tel`, `url`, `number`)
- `rel="noopener noreferrer"` on `target="_blank"` links

### Security

**High:**
- HTTPS on all pages and external resources
- CSRF protection on server-side requests
- No XSS vectors (sanitize user input, escape output)

**Medium:**
- `Strict-Transport-Security` header (HSTS)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY` (or `SAMEORIGIN`)
- `Content-Security-Policy` header defined

### Performance

**High:**
- All assets minified (Bun bundler handles this)
- Images optimized (WebP for photos, SVG for icons)
- `width` and `height` on `<img>` to prevent layout shift

**Medium:**
- First Meaningful Paint under 1 second
- Time To Interactive under 5 seconds on slow 3G
- Critical bundle under 170KB gzipped
- Images lazy loaded (`loading="lazy"`)
- `<link rel="preload">` for critical resources
- `<link rel="dns-prefetch">` for third-party domains
- Cookie size under 4KB per cookie, under 20 cookies per domain

### SEO

**High:**
- `robots.txt` exists and doesn't block pages
- `sitemap.xml` exists and submitted to Search Console
- Structured data (JSON-LD) for relevant content types

**Medium:**
- Heading hierarchy reflects content structure
- HTML sitemap linked from footer

### Images

**High:**
- All images optimized (use ImageOptim, TinyPNG, or SVGO)
- `alt` text on every `<img>`
- `width` and `height` attributes set

**Medium:**
- `<picture>` / `srcset` for responsive images
- SVG sprite for icon sets
- Lazy loading with `loading="lazy"`

**Low:**
- 2x/3x variants for retina displays

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
