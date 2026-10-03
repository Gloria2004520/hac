# Project workflow

- The user requests that every completed update to this project also be committed and pushed to `https://github.com/suonnnnnnn/slowly-demo.git` on `main`.
- Fetch before pushing, preserve remote changes, and never force-push. If synchronization is blocked, report the blocker.
- Never commit API keys, `.env` secrets, `.git-broken-backup`, or local hosting credentials. Stage specific files.
- Write commit messages in English (`feat:` / `fix:` / `docs:` + a short English body). Chinese belongs in
  code comments and UI copy, not in commit messages.
- Keep model calls free-only unless the user explicitly authorizes a paid model. Minimize tool calls and test requests to respect the user's usage budget.
- Be honest about what each part actually does. Live AI chat, curated links and real video
  processing are three different things. The step breakdown is real (ffmpeg scene cuts + a vision
  model reading one representative frame per segment), but it sees screenshots only — no audio, no
  transcription, no OCR. If a breakdown falls back to a generic skeleton, say so; never imply the
  video was read when it was not.
- READMEs are English-first, each with a Chinese mirror kept in sync: `README.md` +
  `README.zh-CN.md`, and `frontend/README.md` + `frontend/README.zh-CN.md`. Update both when
  behaviour changes. UI copy stays Chinese.
