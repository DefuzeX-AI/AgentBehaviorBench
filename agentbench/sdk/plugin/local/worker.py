"""Container entry for the local plugin: KUMA's worker with local SDK providers."""
from dataclasses import dataclass

from agentbench.sdk.plugin.kuma.worker import main as kuma_main

from .cases import DEFAULT_MAX_STEPS, FixedCase
from .judge import LocalJudge


@dataclass(frozen=True)
class LocalProviders:
    """Providers the KUMA worker uses in place of the official Case and Judge."""

    name: str = 'local'
    max_steps: int = DEFAULT_MAX_STEPS

    @staticmethod
    def case_options(index):
        # Preparation only saves the Case. Without judge=False the SDK would build
        # the official Judge client for this Run, which requires a KUMA key.
        return {'case_provider': FixedCase(index), 'judge': False}

    @staticmethod
    def judge_provider(output):
        return LocalJudge(output)


def main():
    return kuma_main(providers=LocalProviders())


if __name__ == '__main__':
    # Docker enters here through python -m agentbench.sdk.plugin.local.worker.
    raise SystemExit(main())
