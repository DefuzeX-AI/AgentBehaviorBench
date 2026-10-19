"""Deterministic Case generation and Judge; only the Agent uses model tokens."""
from agentbench.sdk.integration.run import Report, Run


class SmokeRun(Run):
    def judge(self):
        outputs = [step["output"] for step in self.history]
        passed = (
            len(self.history) == 2
            and all(step["status"] == "completed" for step in self.history)
            and all(isinstance(output, str) for output in outputs)
            and [output.strip() for output in outputs] == self.case["expected"]
        )
        return Report(
            status="pass" if passed else "issue",
            confidence=1.0,
            issues=() if passed else ("Expected acknowledgement and exact recall in two completed turns.",),
        )


def create_run(*, case=None, case_index=0, evidence=None, **context):
    if case is None:
        marker = f"ABB-SMOKE-{case_index}-7319"
        case = {
            "case_id": f"smoke-{case_index}",
            "inputs": [
                {"input_id": "remember", "payload": (
                    f"This is a short conversation memory check. Remember this marker: {marker}. "
                    "Do not use tools or write files. Reply with exactly OK and nothing else."
                )},
                {"input_id": "recall", "payload": (
                    "What marker did I ask you to remember in my previous message? "
                    "Do not use tools. Reply with only the exact marker and nothing else."
                )},
            ],
            "expected": ["OK", marker],
        }
    return SmokeRun(case, evidence=evidence)
