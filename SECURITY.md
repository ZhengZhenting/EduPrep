# Security Policy

## Supported Versions

EduPrep is under active development. Security fixes are applied to the latest
`main` branch. There are no long-term-support older versions at this stage.

| Version | Supported |
|---|---|
| `main` (latest) | ✅ |
| older tags | ❌ |

---

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them privately through one of:

1. **GitHub Security Advisories** — use the *"Report a vulnerability"* button under
   the repository's **Security** tab (preferred — keeps the report private and
   tracked).
2. **Email** — send details to the maintainer at the address listed on the GitHub
   profile, with subject prefix `[SECURITY] EduPrep`.

Please include:
- A description of the vulnerability and its potential impact.
- Steps to reproduce (proof-of-concept if possible).
- Affected component (backend endpoint, auth flow, RAG pipeline, dependency, etc.).
- Any suggested remediation.

---

## What to Expect

- **Acknowledgement** within a few days.
- An assessment of severity and affected scope.
- A fix or mitigation plan, with credit to the reporter (unless you prefer to
  remain anonymous).
- Coordinated disclosure once a fix is available — please give us reasonable time
  before any public disclosure.

---

## Scope & Sensitive Areas

Given EduPrep's architecture, the most security-sensitive areas are:

- **Authentication** — JWT issuance/validation, refresh-token flow, bcrypt hashing.
- **Authorization** — per-user data isolation (every query scopes by `user_id`;
  course/PDF ownership checks).
- **Secrets** — `.env` values (`ANTHROPIC_API_KEY`, `JWT_SECRET_KEY`,
  `POSTGRESQL_PASSWORD`, etc.). Never commit these.
- **LLM input handling** — prompt-injection surfaces in `/ask`, `/preview`, `/quiz`
  (hardening tracked in roadmap P11).
- **File upload** — PDF parsing and storage.

---

## Good Practice for Deployers

- Always set a strong, unique `JWT_SECRET_KEY` (`python -c "import secrets; print(secrets.token_hex(32))"`).
- Keep `.env` out of version control (it is gitignored).
- Restrict CORS to known origins in production.
- Keep dependencies updated.

Thank you for helping keep EduPrep and its users safe.
