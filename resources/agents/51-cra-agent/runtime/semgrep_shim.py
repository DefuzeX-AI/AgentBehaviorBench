#!/usr/bin/env python3
"""PATH shim for the semgrep binary inside the ABB image.

The upstream SAST scanner (agent/src/scanners/sast_scanner.py) invokes
``semgrep --config p/owasp-top-ten --config p/cwe-top-25 ...``. Registry ids
are resolved against https://semgrep.dev at invocation time, and the OSS
distribution keeps no on-disk rules cache, so under the evaluation runtime's
no-egress policy the fetch would always fail and SAST would silently report
zero findings.

This deployment therefore downloads the two rulesets once at image build
time (see the Dockerfile) and installs this shim ahead of the real binary in
PATH. The shim rewrites every ``--config <registry-id>`` argument to the
corresponding snapshot file and then execs the real semgrep with all other
arguments untouched. Everything else -- rule evaluation, output, exit codes
-- is the real scanner; only the transport of the rules differs.
"""

from __future__ import annotations

import os
import sys

REAL_SEMGREP = "/usr/local/bin/semgrep"
SNAPSHOT_DIR = "/opt/semgrep-rules"
REGISTRY_PREFIXES = ("p/", "r/", "s/")


def main() -> None:
    args = sys.argv[1:]
    rewritten: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--config" and i + 1 < len(args):
            rule_id = args[i + 1]
            if rule_id.startswith(REGISTRY_PREFIXES):
                snapshot = os.path.join(
                    SNAPSHOT_DIR, rule_id.replace("/", "-") + ".yaml"
                )
                rewritten += ["--config", snapshot]
                i += 2
                continue
        rewritten.append(arg)
        i += 1
    os.execv(REAL_SEMGREP, [REAL_SEMGREP] + rewritten)


if __name__ == "__main__":
    main()
