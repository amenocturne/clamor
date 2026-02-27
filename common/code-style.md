## Code Style

- **Functional programming**: Pure functions, no classes, no `this`
- **Immutability**: Use `const`, spread operators, `readonly` in types
- **Side effects at boundaries**: IO operations only at entry points (CLI, server handlers)
- **No over-engineering**: Solve the current problem, not hypothetical future ones
