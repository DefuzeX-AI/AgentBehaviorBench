# Explicit per-unit CPU quota

An Agent may declare `cpus = 2` under `[runtime]` in agent.toml. The value is a
finite TOML number in (0, 4]. Omitted values preserve the supplied DockerPolicy
exactly, including its default one-CPU quota. An explicit value replaces only
`--cpus`; it does not change memory, PIDs, capabilities, privileges, network,
filesystems or mounts. The final Docker arguments are projected into the observed
execution environment, so official Case generation can use the actual quota.
This is a declared build/runtime input, not a live docker-update workaround.
