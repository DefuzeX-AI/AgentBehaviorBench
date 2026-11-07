// Host the unchanged native ACP command in its live HTTP runtime and Case scope.
// The pinned CLI otherwise leaves handlers in its separate CLI runtime context.
import { ACP } from "../agent/packages/acp/src/agent"
import { createAcpCommand } from "../agent/packages/acp/src/cli/acp"
import { withScopeContext } from "../agent/packages/local-runtime/src/cli/scope"
import { PresetRuntimeHandle } from "../agent/packages/presets/src/server/runtime-handle"

const runtime = await PresetRuntimeHandle.open({ mode: "oneshot", network: { hostname: "127.0.0.1", port: 0 } })
try {
  const methods = ["newSession", "loadSession", "setSessionConfigOption", "setSessionMode", "prompt"] as const
  for (const name of methods) {
    const original = ACP.Agent.prototype[name]
    if (typeof original !== "function") throw new Error(`Pinned ACP method is missing: ${name}`)
    Object.defineProperty(ACP.Agent.prototype, name, {
      configurable: true,
      writable: true,
      value: function (this: ACP.Agent, ...args: unknown[]) {
        return runtime.run(() => withScopeContext("/home/agent/workspace", () => Reflect.apply(original, this, args)))
      },
    })
  }
  const command = createAcpCommand(async () => runtime)
  await runtime.run(() => command.handler({ cwd: "/home/agent/workspace", hostname: "127.0.0.1", port: 0, mdns: false, cors: [], _: [], $0: "synergy" }))
} finally {
  await runtime.close()
}
process.exit(process.exitCode ?? 0)
