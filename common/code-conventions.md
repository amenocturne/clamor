## Code Conventions

- **Functional programming**: Pure functions, no classes, no `this`
- **Immutability**: Use `const`, spread operators, `readonly` in types
- **Side effects at boundaries**: IO operations only at entry points (CLI, server handlers)
- **No over-engineering**: Solve the current problem, not hypothetical future ones

### Comments

Only meaningful comments that add value:
- **Good**: Why something is done a certain way, complex flow explanations, non-obvious tradeoffs
- **Bad**: What the code does (code is self-documenting), change history (that's git), TODO/FIXME

```python
# Bad: "increment counter by 1"
# Bad: "fixed bug #123"
# Good: "Using median instead of mean to handle outliers in sensor data"
# Good: "Retry logic needed because API returns 503 during deployments"
```
