# Release Checklist

Use this checklist before publishing a GitHub release or sharing desktop builds publicly.

## Code and Tests

- [ ] Confirm the working tree only contains intended changes.
- [ ] Run backend tests: `python -m pytest -q`
- [ ] Run frontend lint: `cd frontend && npm run lint`
- [ ] Run frontend build: `cd frontend && npm run build`
- [ ] Run a clean install on a fresh checkout or temporary folder.

## Windows EXE Smoke Test

- [ ] Build with `pyinstaller jobsmith.spec --noconfirm`.
- [ ] Start `dist/Jobsmith.exe` on Windows 10 or Windows 11.
- [ ] Confirm first launch opens the native window.
- [ ] Confirm Settings can select a local CLI backend or BYOK backend.
- [ ] Upload a small PDF resume and confirm parsing succeeds.
- [ ] Run one low-frequency job search.
- [ ] Generate one application package and confirm it appears in My Packages.
- [ ] Export a Word `.docx`.
- [ ] Open mock interview from a package.
- [ ] Use Settings to clear personal data, then confirm history/searches are removed.
- [ ] Open the error-log folder from Settings.

## Unsigned macOS DMG

- [ ] Run **Actions -> Build unsigned macOS DMG**.
- [ ] Confirm both artifacts were produced:
  - `Jobsmith-macOS-arm64-unsigned.dmg`
  - `Jobsmith-macOS-x64-unsigned.dmg`
- [ ] On a real Mac, open the DMG, drag `Jobsmith.app` to Applications, then launch with right-click -> Open.
- [ ] Confirm first launch opens the native window and local data is created under `~/Library/Application Support/Jobsmith`.
- [ ] State clearly that the macOS build is unsigned and not notarized.

## Privacy and Packaging

- [ ] Remove local secrets from `.env`, logs, screenshots, and release notes.
- [ ] Do not ship local `data/`, `.pytest_cache/`, `.ruff_cache/`, or `frontend/node_modules/`.
- [ ] Include `LICENSE`, README, and privacy documentation in the release page.
- [ ] Optional: publish SHA-256 checksums if the release page should support manual integrity verification.
- [ ] State clearly whether the build is signed. Do not imply code signing if it is unsigned.

## GitHub Release

- [ ] Use a version tag, for example `v0.1.0`.
- [ ] Mention supported platforms and known limitations.
- [ ] Link to `docs/PRIVACY.md`.
- [ ] Include upgrade notes if local data paths or settings changed.
- [ ] Keep the previous release available until the new build has been smoke-tested by users.

## Public Launch

- [ ] Verify screenshots match the current UI.
- [ ] Confirm issue templates are enabled.
- [ ] Prepare a short troubleshooting note for Windows SmartScreen, macOS Gatekeeper, missing WebView2, and missing CLI login.
- [ ] Monitor GitHub issues after launch and be ready to patch source-site breakages.
