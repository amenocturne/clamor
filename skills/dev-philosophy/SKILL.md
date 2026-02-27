---
name: dev-philosophy
description: Core development principles. Apply to all code across languages. Triggers automatically when writing code, reviewing approaches, or making architectural decisions.
author: amenocturne
---

# Dev Philosophy

## Functional First

- Pure functions, immutability, no side effects in core logic
- Composition over inheritance
- Declarative over imperative when language allows
- Side effects pushed to boundaries (CLI, handlers, main)
- Effect systems (ZIO, IO, etc.) are great for complex apps - or roll a simple one if needed

## KISS with Context

- No premature abstraction - solve current problem
- Throwaway scripts can be quick and dirty
- BUT: complex domains (audio engines, state machines) deserve proper design
- Abstraction worth it when:
  - Domain has inherent complexity
  - Composability genuinely helps (connect nodes, chain transforms)
  - Imperative version would be tangled/hard to modify

## Right-Size for the Use Case

- Personal project ≠ production system
- Simple Docker over k8s cluster for single-user apps
- SQLite over Postgres when it's just you
- Match tooling to actual scale and audience
- Don't cargo-cult enterprise patterns into hobby projects

## Strong Typing (Pragmatic)

- Make invalid states unrepresentable
- Types as documentation and guardrails
- Use types for errors (Result, Either, typed exceptions)
- Not type-astronaut level - serve the code, don't over-engineer

## Error Handling

- Fail fast, explicit errors, no silent swallowing
- Prefer typed errors over stringly-typed exceptions
- Use Result/Either types where language supports
- Errors are part of the API - design them

## Iterative Development

- Explore before committing - try different approaches
- Implement simplest version first to validate idea
- Compare approaches when uncertain
- Polish only when writing final implementation
- Strip away exploration scaffolding at the end

## No Premature Optimization

- Readability and composability over raw performance
- Optimize only critical paths (large datasets, hot loops)
- Know your complexity: O(n²) on thousands of entries = problem
- Performance benchmarks for critical algorithms, not everything

## Testing

- Unit test complex logic, not trivial functions
- Integration tests sparingly - manual verification often enough
- Performance benchmarks for critical paths
- Ask user to verify when uncertain
