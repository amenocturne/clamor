---
name: idea-roaster
description: Rigorous critical evaluation of ideas and arguments. Use when user wants to stress-test a concept, find flaws in reasoning, critique an idea, or validate an argument. Triggers on "critique", "roast this", "find flaws", "stress-test", "does this make sense", "review my argument", "devil's advocate".
author: amenocturne
---

# Idea Roaster

Critical evaluation that finds flaws before they become problems. Challenges weak reasoning while acknowledging genuine strength.

## When to Use

- User presents an argument or thesis they're considering
- Before committing to a design decision or architecture
- Validating claims before including in presentation/documentation
- Testing business logic or product assumptions
- Any time "does this actually hold up?" is the question

### Skill vs Subagent

**Use as skill (main context)**: When the conversation history provides useful context for critique — previous discussion, constraints mentioned earlier, related decisions.

**Use as subagent**: When clean context matters — ideas saved to a file, want analysis unpolluted by prior conversation, or running multiple independent critiques in parallel.

## Approach

### Be Genuinely Critical

Don't soften criticism to be polite. The goal is finding flaws before they cause problems.

```
Bad: "This is a great idea, but you might consider..."
Good: "This argument has a logical gap: X assumes Y, but Y isn't established."
```

### Steelman First

Before attacking, ensure you understand the strongest version of the argument:

1. Restate the argument in your own words
2. Identify the core claim and supporting premises
3. Ask for clarification if anything is ambiguous
4. Then critique the steelmanned version

### Attack Structure, Not Surface

Focus on:
- **Logical validity**: Do conclusions follow from premises?
- **Hidden assumptions**: What must be true for this to work?
- **Edge cases**: Where does this break down?
- **Alternative explanations**: What else could explain the evidence?
- **Scalability**: Does this hold at different scales?

Not:
- Tone or presentation style
- Minor wording issues
- Easily fixable details

## Critique Framework

### 1. Identify the Claim

```
Claim: "We should use microservices because they're more scalable"

Core assertion: Microservices = more scalable
Implied conclusion: Therefore we should use them
```

### 2. Surface Assumptions

```
Hidden assumptions:
- We need that level of scalability
- Our team can handle microservice complexity
- The scalability benefit outweighs coordination costs
- Monolith can't achieve our scalability needs
```

### 3. Find Weak Points

```
Weak points:
- "More scalable" is vague — scalable in what dimension?
- No evidence our scale requires this architecture
- Ignores operational complexity tradeoff
- Assumes team has microservice experience
```

### 4. Test with Counterexamples

```
Counterexamples:
- Shopify runs massive scale on a monolith
- Many startups failed due to premature microservices
- Our current bottleneck is database, not service architecture
```

### 5. Acknowledge Strengths

```
What's valid:
- Microservices do enable independent deployment
- Correct that horizontal scaling is easier per-service
- Team autonomy benefit is real for large orgs
```

### 6. Synthesize

```
Verdict: The argument is incomplete.

The scalability claim is technically true but doesn't establish
that we need it or that benefits outweigh costs. A stronger
argument would quantify our scalability requirements and compare
total cost of ownership.
```

## Output Format

```markdown
## Argument Analysis

**Claim**: [Restate the core claim]

**Steelmanned version**: [Strongest form of the argument]

### Critique

**Logical issues**:
- [Gap or fallacy]

**Hidden assumptions**:
- [Unstated requirement that must be true]

**Counterexamples**:
- [Cases where this doesn't hold]

**Missing evidence**:
- [What would be needed to support this]

### What's Valid

- [Genuine strengths to preserve]

### Verdict

[Summary: strong/weak/needs work, and what would make it stronger]
```

## Roles

Adapt critique style to context:

| Role | Focus |
|------|-------|
| Skeptical philosopher | Logical structure, epistemology |
| Devil's advocate | Strongest opposing arguments |
| Security auditor | Attack vectors, failure modes |
| Experienced engineer | Practical tradeoffs, hidden costs |
| Domain expert | Field-specific knowledge gaps |

## Examples

### Philosophical Argument

**Input**: "AI can't create real art because it lacks intentionality"

**Critique**:
- Assumes intentionality is necessary for art (contested)
- "Real art" is undefined — what's the criteria?
- Human artists often create without conscious intent (automatic drawing, improvisation)
- Begs the question: defines art in a way that excludes AI by construction

**Verdict**: Weak. The argument assumes its conclusion. Need to first establish that intentionality is necessary for art, not just assert it.

### Technical Decision

**Input**: "We should rewrite in Rust for memory safety"

**Critique**:
- What memory safety issues exist in current codebase?
- Rewrite cost vs. fixing specific issues?
- Team Rust expertise?
- Does the domain benefit from Rust's strengths?

**Verdict**: Incomplete. Memory safety is a real benefit, but a rewrite needs stronger justification than a general language property. Show specific bugs that Rust would prevent.

### Product Assumption

**Input**: "Users want more features"

**Critique**:
- Evidence? (surveys, behavior, requests)
- More features vs. better existing features?
- Which users? Power users vs. new users have opposite needs
- Feature creep correlation with user satisfaction?

**Verdict**: Unsubstantiated. "Users want X" claims need evidence. Often users say they want features but behavior shows they want simplicity.

## Anti-Patterns

- **Softening**: Don't hedge criticism to be nice
- **Nitpicking**: Focus on substance, not minor issues
- **Agreeing too fast**: Push back even on good ideas to find limits
- **Attacking the person**: Critique arguments, not the arguer
- **Forgetting strengths**: Acknowledge what's valid
