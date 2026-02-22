---
name: haskell
description: Haskell development patterns. Use when working on Haskell projects or writing Haskell code. Triggers on ".hs files", "cabal", "haskell project", "ghc", "hspec", working in a project with tech:[haskell].
author: amenocturne
---

# Haskell Development

Haskell with cabal and standard tooling.

## Stack

| Purpose | Tool |
|---------|------|
| Build | cabal |
| Formatter | fourmolu or ormolu |
| Linter | hlint |
| Testing | hspec or tasty |
| Language server | haskell-language-server |

## Commands

```bash
just run         # cabal run
just build       # cabal build
just test        # cabal test
just repl        # cabal repl
just lint        # hlint src/
just fmt         # fourmolu -i src/
just clean       # cabal clean
```

## Project Structure

```
project/
├── app/
│   └── Main.hs          # Entry point
├── src/
│   ├── Lib.hs           # Library root
│   ├── Types.hs         # Type definitions
│   └── Core/            # Business logic
├── test/
│   └── Spec.hs          # Test suite
├── project.cabal
└── justfile
```

## Type-Driven Design

```haskell
-- Define types first
newtype UserId = UserId Text
  deriving (Show, Eq)

data User = User
  { userId :: UserId
  , userName :: Text
  , userActive :: Bool
  }

-- Functions follow from types
findUser :: UserId -> [User] -> Maybe User
findUser uid = find ((== uid) . userId)
```

## Maybe and Either

```haskell
-- Use Maybe for optional values
parsePort :: Text -> Maybe Int
parsePort = readMaybe . unpack

-- Use Either for errors with context
data ParseError = InvalidFormat Text | OutOfRange Int

parseConfig :: Text -> Either ParseError Config
parseConfig input = do
  port <- parsePort' input
  validate port
  pure (Config port)
```

## Pattern Matching

```haskell
-- Exhaustive matching
describe :: Status -> Text
describe Pending = "waiting"
describe (Processing started) = "running since " <> show started
describe (Complete result) = "done: " <> show result
describe (Failed err) = "error: " <> err
```

## Function Composition

```haskell
-- Point-free when clear
processAll :: [Item] -> [Result]
processAll = map process . filter isValid

-- Named arguments when complex
processWithConfig :: Config -> [Item] -> [Result]
processWithConfig config items =
  items
    & filter (isValid config)
    & map (process config)
```

## Monadic Composition

```haskell
-- Do notation for sequential effects
fetchUser :: UserId -> IO (Maybe User)
fetchUser uid = do
  response <- httpGet ("/users/" <> show uid)
  case decode response of
    Left _ -> pure Nothing
    Right user -> pure (Just user)

-- Applicative when independent
data Form = Form Text Int Bool

parseForm :: Parser Form
parseForm = Form
  <$> field "name"
  <*> field "age"
  <*> field "active"
```

## Type Classes

```haskell
-- Derive what you can
data Item = Item
  { itemId :: Int
  , itemName :: Text
  }
  deriving (Show, Eq, Generic)
  deriving anyclass (FromJSON, ToJSON)

-- Custom instances when needed
instance Ord Item where
  compare = comparing itemName
```

## Testing with Hspec

```haskell
import Test.Hspec

main :: IO ()
main = hspec $ do
  describe "parsePort" $ do
    it "parses valid port" $
      parsePort "8080" `shouldBe` Just 8080

    it "returns Nothing for invalid" $
      parsePort "abc" `shouldBe` Nothing

  describe "findUser" $ do
    it "finds existing user" $ do
      let users = [User (UserId "1") "Alice" True]
      findUser (UserId "1") users `shouldSatisfy` isJust
```

## Cabal File

```cabal
cabal-version: 3.0
name:          project
version:       0.1.0.0

library
  exposed-modules: Lib, Types
  build-depends:   base ^>=4.17, text, containers
  hs-source-dirs:  src
  default-language: GHC2021

executable project
  main-is:        Main.hs
  build-depends:  base, project
  hs-source-dirs: app
  default-language: GHC2021

test-suite spec
  type:           exitcode-stdio-1.0
  main-is:        Spec.hs
  build-depends:  base, project, hspec
  hs-source-dirs: test
  default-language: GHC2021
```

## Language Extensions

Prefer `GHC2021` which includes common extensions. Add others in cabal:

```cabal
default-extensions:
  OverloadedStrings
  DeriveGeneric
  DerivingStrategies
```

## Naming Conventions

Prefer full names over operators for readability:

```haskell
-- Good: readable names
view userIdL user
set userNameL "Alice" user
over userScoreL (+1) user

-- Avoid: cryptic operators
user ^. userIdL
user & userNameL .~ "Alice"
user & userScoreL %~ (+1)
```

This applies especially to lens, optics, and similar libraries.

## Anti-patterns

- Partial functions (`head`, `tail`, `fromJust`) - use safe alternatives
- String instead of Text
- Lazy IO for large files - use streaming
- Orphan instances
- Overly clever point-free code
- Operator soup (lens `^.`, `.~`, `%~`) - use `view`, `set`, `over`
