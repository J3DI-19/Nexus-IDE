# Nexus Runtime Packs

Drop Nexus-managed language runtimes and toolchains into this directory so the IDE does not depend on host-installed compilers.

Expected layout:

```text
backend/runtimes/
  python/python.exe
  node/node.exe
  java/bin/java.exe
  gcc/bin/gcc.exe
  gcc/bin/g++.exe
  dotnet/sdk/csc.exe
  bash/bin/bash.exe
  powershell/bin/powershell.exe
```

Notes:

* The terminal runner only looks in this directory first.
* If a runtime is missing, Nexus shows a clear "not bundled" error.
* TypeScript execution is expected to run through a Nexus-bundled Node toolchain that also ships `tsx` or `ts-node` in `node_modules/.bin`.
