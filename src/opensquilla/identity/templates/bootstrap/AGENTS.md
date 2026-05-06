# AGENTS.md

Use this file for workspace-level operating guidance.

## Startup Context

- Read `SOUL.md` for stable persona and collaboration style.
- Read `USER.md` for stable user profile details when the session is private.
- Read `TOOLS.md` for workspace-specific tool notes.
- Follow `BOOTSTRAP.md` first when it exists, then remove it after setup is complete.

## Working Rules

- Higher-priority system, developer, runtime, safety, and direct user instructions
  override this file.
- Keep changes small, reversible, and tied to the user's request.
- Do not store secrets, credentials, or one-off task notes here.
- In shared, channel, cron, or subagent contexts, avoid exposing private user or
  long-term memory content unless runtime policy explicitly makes it available.
