"""Offline acceptance: real installed KUMA, a real echo process, local Judge."""

import json
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from kuma import create_run
from kuma.serialization import to_json


def main():
    output = Path("/artifacts")
    repo = Path("/tmp/directory-sdk-agent")
    repo.mkdir()
    (repo / "agent.py").write_text("import sys\nprint(sys.argv[1])\n")
    profile = repo / "profile.md"
    profile.write_text(
        "---\nagent_description: Echo supplied text unchanged.\n"
        "input_type: text\n---\n## Production Use Scenario\n"
        "A user submits text and receives the same text.\n"
        "## Behaviors to Test\nEcho the input exactly.\n"
        "## Known Limitations or Prohibited Behaviors\n"
        "Do not modify the text or contact external services.\n"
    )

    def cases(context):
        return {
            "case_id": "directory-offline-case",
            "input_type": "text",
            "inputs": [
                {
                    "input_id": "one",
                    "payload_type": "text",
                    "payload": "directory adapter works",
                }
            ],
        }

    def judge(context):
        assert len(context.history) == 1
        assert context.history[0].submission.output == "directory adapter works"
        return {
            "status": "pass",
            "summary": "Offline custom Judge; not official service evaluation.",
            "issues": [],
        }

    run = create_run(
        repo_path=repo,
        agent_profile_path=profile,
        case_provider=cases,
        judge_provider=judge,
        max_steps=1,
        allow_local=False,
        track_files=False,
        save_local=True,
    )
    try:
        run.save_case(repo / "case.json")
        shutil.copyfile(repo / "case.json", output / "case.json")
        item = run.get_input(full=True)
        process = subprocess.run(
            [sys.executable, str(repo / "agent.py"), item.payload],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        answer = process.stdout.strip()
        (output / "agent-output.json").write_text(
            json.dumps({"output": answer, "exit_code": process.returncode})
        )
        run.submit(output=answer)
        assert run.report is not None and run.report.status == "pass"
        (output / "judge.json").write_text(json.dumps(to_json(run.report)))
        result = {
            "run_id": run.run_id,
            "state": run.state,
            "sdk_version": version("kuma-defuzex"),
            "provider_mode": "offline-custom",
            "network": "none",
            "input_id": item.input_id,
            "payload": item.payload,
            "output": answer,
            "report": to_json(run.report),
            "history_count": len(run.history),
        }
        (output / "run.json").write_text(json.dumps(result, indent=2))
        print(
            json.dumps(
                {
                    "run_id": run.run_id,
                    "status": "pass",
                    "sdk_version": result["sdk_version"],
                }
            )
        )
    finally:
        if run.state in ("ready", "input_delivered"):
            run.cancel()


if __name__ == "__main__":
    main()
