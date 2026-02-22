---
name: scala
description: Scala development patterns. Use when working on Scala projects or writing Scala code. Triggers on ".scala files", "sbt", "scala project", "build.sbt", working in a project with tech:[scala].
author: amenocturne
---

# Scala Development

Scala with sbt and functional style.

## Version

Check `build.sbt` or `build.properties` for Scala version before writing code. Syntax differs between Scala 2.x and 3.x.

## Stack

| Purpose | Tool |
|---------|------|
| Build | sbt |
| Formatter | scalafmt |
| Linter | scalafix |
| Testing | zio-test or scalatest |
| Effects | ZIO |
| FP types/syntax | cats |

## Commands

```bash
just run         # sbt run
just build       # sbt compile
just test        # sbt test
just lint        # sbt "scalafix --check"
just fmt         # sbt scalafmtAll
just fix         # sbt "scalafix" && sbt scalafmtAll
just repl        # sbt console
just clean       # sbt clean
```

## Project Structure

```
project/
├── src/
│   ├── main/scala/
│   │   └── com/example/
│   │       ├── Main.scala
│   │       ├── domain/       # Types and business logic
│   │       └── infra/        # IO, external services
│   └── test/scala/
│       └── com/example/
├── project/
│   ├── build.properties
│   └── plugins.sbt
├── build.sbt
└── justfile
```

## Patterns

### Case Classes

```scala
// Both Scala 2 and 3
case class User(id: UserId, name: String, active: Boolean)
```

### ADTs

```scala
// Scala 3
enum Status:
  case Pending
  case Processing(started: Instant)
  case Complete(result: Output)
  case Failed(error: String)

// Scala 2
sealed trait Status
object Status {
  case object Pending extends Status
  case class Processing(started: Instant) extends Status
  case class Complete(result: Output) extends Status
  case class Failed(error: String) extends Status
}
```

### Pattern Matching

```scala
// Scala 3 (braceless)
def describe(status: Status): String = status match
  case Status.Pending => "waiting"
  case Status.Processing(started) => s"running since $started"
  case Status.Complete(result) => s"done: $result"
  case Status.Failed(error) => s"error: $error"

// Scala 2 (braces)
def describe(status: Status): String = status match {
  case Status.Pending => "waiting"
  case Status.Processing(started) => s"running since $started"
  case Status.Complete(result) => s"done: $result"
  case Status.Failed(error) => s"error: $error"
}
```

### Implicits / Givens

```scala
// Scala 3
def process(items: List[Item])(using logger: Logger): List[Result] =
  logger.info(s"Processing ${items.size} items")
  items.map(transform)

given Logger = ConsoleLogger()

// Scala 2
def process(items: List[Item])(implicit logger: Logger): List[Result] = {
  logger.info(s"Processing ${items.size} items")
  items.map(transform)
}

implicit val logger: Logger = ConsoleLogger()
```

## Functional Patterns

### Cats for Types and Syntax

```scala
import cats.syntax.all._

def parsePort(s: String): Option[Int] =
  s.toIntOption.filter(p => p > 0 && p < 65536)

def parseConfig(input: String): Either[String, Config] =
  for {
    port <- parsePort(input).toRight("Invalid port")
    _ <- Either.cond(port > 1024, (), "Port must be > 1024")
  } yield Config(port)
```

### Validated for Error Accumulation

```scala
import cats.data.ValidatedNel
import cats.syntax.all._

def validateName(s: String): ValidatedNel[String, String] =
  if (s.nonEmpty) s.validNel else "Name required".invalidNel

def validateAge(n: Int): ValidatedNel[String, Int] =
  if (n > 0) n.validNel else "Age must be positive".invalidNel

def validateUser(name: String, age: Int): ValidatedNel[String, User] =
  (validateName(name), validateAge(age)).mapN(User.apply)
```

### ZIO for Effects

```scala
import zio._

def fetchUser(id: UserId): Task[Option[User]] =
  ZIO.attemptBlocking {
    // HTTP call
  }

def processUsers(ids: List[UserId]): Task[List[User]] =
  ZIO.foreach(ids)(fetchUser).map(_.flatten)

object Main extends ZIOAppDefault {
  def run =
    processUsers(List(UserId("1"), UserId("2")))
      .flatMap(users => Console.printLine(s"Found ${users.size} users"))
}
```

## Testing

### ZIO Test

```scala
import zio.test._

object UserSpec extends ZIOSpecDefault {
  def spec = suite("User")(
    test("parsePort valid") {
      assertTrue(parsePort("8080") == Some(8080))
    },
    test("parsePort invalid") {
      assertTrue(parsePort("abc") == None)
    },
    test("validateUser accumulates errors") {
      val result = validateUser("", -1)
      assertTrue(result.isInvalid) &&
      assertTrue(result.fold(_.size, _ => 0) == 2)
    }
  )
}
```

### ScalaTest

```scala
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class UserSpec extends AnyFlatSpec with Matchers {
  "parsePort" should "parse valid port" in {
    parsePort("8080") shouldBe Some(8080)
  }

  it should "return None for invalid" in {
    parsePort("abc") shouldBe None
  }
}
```

## build.sbt

```scala
// Check existing project for scalaVersion - don't assume
ThisBuild / scalaVersion := "2.13.x" // or "3.x.x"

lazy val root = project
  .in(file("."))
  .settings(
    name := "project",
    libraryDependencies ++= Seq(
      "org.typelevel" %% "cats-core" % "x.x.x",
      "dev.zio" %% "zio" % "x.x.x",
    ),
  )
```

Check compatible library versions for your Scala version.

## Anti-patterns

- `null` - use Option
- `var` - use val and immutable structures
- `throw` - use Either or ZIO.fail
- Java collections - use Scala collections
- Inheritance for code reuse - use composition and type classes
- Blocking in ZIO - wrap with ZIO.attemptBlocking
