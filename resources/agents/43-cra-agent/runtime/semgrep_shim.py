#!/usr/bin/env python3
"""PATH shim for the semgrep binary inside the ABB image.

The upstream SAST scanner (agent/src/scanners/sast_scanner.py) invokes
``semgrep --config p/owasp-top-ten --config p/cwe-top-25 ...``. Registry ids
are resolved against https://semgrep.dev at invocation time, and the OSS
distribution keeps no on-disk rules cache, so under the evaluation runtime's
no-egress policy the fetch would always fail and SAST would silently report
zero findings.

The snapshots sit at the filesystem root rather than under /opt because
semgrep derives each finding's check_id prefix from the parent path of the
config file it loaded; a root-level config yields the same check_id a live
registry scan reports, which upstream puts into every finding's title and
evidence. See the comment above the download layer in the Dockerfile.
"""

from __future__ import annotations

import os
import sys

REAL_SEMGREP = "/usr/local/bin/semgrep"
REGISTRY_PREFIXES = ("p/", "r/", "s/")


def _snapshot_for(rule_id: str) -> str:
    """Resolve a registry id to its root-level snapshot path."""
    return "/" + rule_id.replace("/", "-") + ".yaml"


def main() -> None:
    args = sys.argv[1:]
    rewritten: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        # Both "--config <id>" and "--config=<id>" are accepted; upstream uses the
        # space form, the equals form is handled so a future change there does not
        # silently fall back to a live registry lookup.
        if arg.startswith("--config="):
            rule_id = arg[len("--config=") :]
            if rule_id.startswith(REGISTRY_PREFIXES):
                rewritten.append("--config=" + _snapshot_for(rule_id))
            else:
                rewritten.append(arg)
            i += 1
            continue
        if arg == "--config" and i + 1 < len(args):
            rule_id = args[i + 1]
            if rule_id.startswith(REGISTRY_PREFIXES):
                rewritten += ["--config", _snapshot_for(rule_id)]
                i += 2
                continue
        rewritten.append(arg)
        i += 1
    os.execv(REAL_SEMGREP, [REAL_SEMGREP] + rewritten)


if __name__ == "__main__":
    main()
