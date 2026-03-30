## sbt

**Always use `sbt --client`** for all sbt commands. This uses thin client mode which connects to an existing sbt server (or spawns one if needed).

Why: Metals runs its own sbt BSP server. Running plain `sbt` spawns a competing instance, causing lock conflicts and resource contention. The thin client shares the same server.

```bash
sbt --client compile      # instead of: sbt compile
sbt --client test         # instead of: sbt test
sbt --client "testOnly *MySpec"
```

To stop the server: `sbt --client shutdown`

Compilation is usually a long-running task, so you must not run it directly and set timeout, instead you should run it as async command without any timeouts

### Lock issue

`sbt --client` can silently hang waiting for `~/.sbt/boot/.../sbt.components.lock`. The workarounds below reduce the risk, but it can still happen — if a background compile produces no output after 30s, this is the likely cause.

Before running any sbt command, check for the lock:
```bash
lock=$(ls ~/.sbt/boot/scala-*/org.scala-sbt/sbt/*/sbt.components.lock 2>/dev/null)
[ -n "$lock" ] && echo "WARNING: sbt lock exists: $lock — remove before running sbt" && exit 1
```

Wrap background compiles with a timeout to avoid silent hangs:
```bash
timeout 600 sbt --client compile || {
  ec=$?
  [ $ec -eq 124 ] && echo "sbt timed out — check for stale lock: ~/.sbt/boot/.../sbt.components.lock"
  exit $ec
}
```

To clear a stale lock: `rm ~/.sbt/boot/scala-*/org.scala-sbt/sbt/*/sbt.components.lock`
