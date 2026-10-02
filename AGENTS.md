# Project workflow

- The user requests that every completed update to this project also be committed and pushed to `https://github.com/suonnnnnnn/slowly-demo.git` on `main`.
- Fetch before pushing, preserve remote changes, and never force-push. If synchronization is blocked, report the blocker.
- Never commit API keys, `.env` secrets, `.git-broken-backup`, or local hosting credentials. Stage specific files.
- Keep model calls free-only unless the user explicitly authorizes a paid model. Minimize tool calls and test requests to respect the user's usage budget.
- Clearly distinguish live AI text chat, curated video links, and simulated video parsing/checks.
