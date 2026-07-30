# Security Policy

## Supported versions

Tracklistify is a CLI tool; only the latest release on `main` receives
security fixes. There are no backport branches.

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private vulnerability reporting:

1. Go to <https://github.com/betmoar/tracklistify/security/advisories/new>
2. Click **"Report a vulnerability"**

This opens a private advisory that only the maintainer can see, so the
details stay confidential until a fix is released. Please include:

- a description of the issue and its impact,
- the steps or input needed to reproduce it,
- the Tracklistify version, OS, and Python version, and
- any relevant references (CVE, advisory, PoC).

You should hear back within a few days. Security reports are prioritized
over feature work.

## Scope

In scope:

- the Python code in [`src/tracklistify/`](src/tracklistify),
- handling of untrusted input — audio files, URLs, downloaded metadata,
  and provider API responses,
- subprocess usage (ffmpeg, yt-dlp, Deno), and
- secret handling (API keys / tokens loaded from `.env`).

Out of scope:

- vulnerabilities in dependencies themselves — report those upstream;
  this repo tracks them via Dependabot,
- issues that require already having code execution on the user's machine,
- anything in `dev_cli/`, `tests/`, or `scripts/` — not shipped.

## What is already covered

- **Dependabot** alerts are enabled and monitored; vulnerable deps get a
  PR or patch.
- **CodeQL** code scanning runs on `main`.
- **Secret scanning** and **push protection** are enabled, so committed
  credentials are flagged and blocked at push time.

## Disclosure

Fixes are released as promptly as possible in a normal release, with credit
to the reporter unless they prefer otherwise. Once a fix is released, the
private advisory may be published as a GitHub Security Advisory.
