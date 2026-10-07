# Branch Protection Baseline

Use GitHub branch protection rules on `main` (and `develop` if used):

1. Require a pull request before merging.
2. Require status checks to pass before merging.
3. Mark `CI / Lint Type Test Contract Smoke` as a required status check.
4. Require branches to be up to date before merging.
5. Disable force pushes and branch deletion.

This ensures CI failures block merges, matching Checklist phase H.
