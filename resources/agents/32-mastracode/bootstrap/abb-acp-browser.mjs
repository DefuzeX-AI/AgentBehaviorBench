// `mastracode --acp` plus the browser configured in settings.json.
// Upstream acpMain (@mastra/code-sdk 1.8.0 dist/acp/index.js:10-61) never passes a browser to
// createMastraCode; only the TUI entry does (mastracode 0.41.0 dist/cli.js:96-99,167-171). This file is
// acpMain verbatim plus `browser` (createMastraCode forwards config.browser to AgentController,
// @mastra/code-sdk dist/index.js:744). coAuthor = TUI_CO_AUTHOR (mastracode dist/tui-B1UNqped.js:62).
import { createMastraCode } from "@mastra/code-sdk";
import { createBrowserFromSettings, loadSettings } from "@mastra/code-sdk/onboarding/settings";
import { runAcpServer } from "@mastra/code-sdk/acp/server";
import { releaseAllThreadLocks } from "@mastra/code-sdk/utils/thread-lock";
import { isStreamDestroyedError } from "@mastra/code-sdk/error-classification";

// Same guards the mastracode CLI installs before dispatching --acp (dist/cli.js:83-90, 253-275), minus the TUI parts.
const fatal = (error) => {
	if (isStreamDestroyedError(error)) return;
	process.stderr.write(`Fatal error: ${error instanceof Error ? error.stack || error.message : String(error)}\n`);
	process.exit(1);
};
process.on("uncaughtException", fatal);
process.on("unhandledRejection", fatal);

const originalConsoleLog = console.log;
console.log = (...args) => {
	process.stderr.write(args.map(String).join(" ") + "\n");
};
let browser;
try {
	browser = await createBrowserFromSettings(loadSettings().browser);
	process.stderr.write(`[abb] browser: ${browser ? browser.name : "disabled"}\n`);
	const result = await createMastraCode({
		coAuthor: { name: "mastracode" },
		unixSocketPubSub: false,
		disableMcp: false,
		disableHooks: false,
		browser
	});
	const { controller, mcpManager, signalsPubSub } = result;
	const modes = [{ id: "build", name: "Build" }, { id: "plan", name: "Plan" }, { id: "fast", name: "Fast" }];
	const cleanup = async () => {
		releaseAllThreadLocks();
		const closeSignalsPubSub = signalsPubSub?.close;
		await Promise.allSettled([
			mcpManager?.disconnect(),
			controller?.getMastra()?.stopWorkers(),
			controller?.stopIntervals(),
			closeSignalsPubSub?.(),
			browser?.close()
		]);
		console.log = originalConsoleLog;
	};
	const handleSignal = async () => {
		await cleanup();
		process.exit(0);
	};
	process.on("SIGINT", handleSignal);
	process.on("SIGTERM", handleSignal);
	await runAcpServer(controller, modes, cleanup);
} catch (error) {
	process.stderr.write(`[acp] Fatal error: ${error}\n`);
	console.log = originalConsoleLog;
	process.exit(1);
}
