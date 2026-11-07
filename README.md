# claude-code-mini

A Claude Code–style coding assistant for your terminal that runs on an **Anthropic API key** through the
[Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/). It is a single Python file, installs without sudo,
and its interface is in **Bahasa Indonesia**.

> Unofficial community project, not affiliated with or endorsed by Anthropic. "Claude" and "Claude Code" are
> trademarks of Anthropic.

## Demo

A real session on a fresh Ubuntu 26.04 machine (trimmed). Claude runs the tests, asks before running the
command, finds the bug, fixes it with a line-numbered diff, re-runs the tests, and reports the cost of the turn.

```text
$ cd ~/proyek/kalkulator && claude-code-mini --model sonnet --budget 0.5
╭───────────────────────────────────────────────────────────────────╮
│ ✻ claude-code-mini (Claude Code via API key)                      │
│ 📂 /home/dev/proyek/kalkulator                                    │
│ 🤖 claude-sonnet-5-5 · mode: acceptEdits · budget: $0.5           │
│ ? bantuan · ! shell · @ file · # memori · Esc menghentikan Claude │
╰───────────────────────────────────────────────────────────────────╯

› jalankan test-nya, lalu perbaiki kalau ada yang gagal
✓ Terhubung · model claude-sonnet-5-5 · mode acceptEdits · auth: ANTHROPIC_API_KEY · 32 tool tersedia
  … (2 percobaan dipotong: python & pytest belum terpasang di mesin ini)
● Bash(python3 -m unittest -v 2>&1 | tail -40; head -20 test_kalkulator.py)
╭─ 🔐 Claude minta izin ──────────────────────────────────────────────╮
│ Bash                                                                │
│ python3 -m unittest -v 2>&1 | tail -40; head -20 test_kalkulator.py │
╰─────────────────────────────────────────────────────────────────────╯
  1 Ya
  2 Ya, dan jangan tanya lagi untuk Bash(python3 -m unittest -v) (disimpan di .claude/settings.local.json)
  3 Tidak, dan beri tahu Claude harus bagaimana
Pilih [1/2/3, Enter=1] › 2
✓ Aturan ditambahkan: Bash(python3 -m unittest -v)
  ⎿  test_bagi (test_kalkulator.TesKalkulator.test_bagi) ... FAIL
     test_tambah (test_kalkulator.TesKalkulator.test_tambah) ... ok
     … +27 baris
● Read(kalkulator.py)
  ⎿  Membaca 7 baris

Bug-nya ketemu: bagi memakai *, padahal seharusnya /. Saya perbaiki sekarang.

● Update(kalkulator.py)
    Ditambah 1 baris, dihapus 1 baris
    6 -     return a * b
    6 +     return a / b
  ⎿  Tersimpan
● Bash(python3 -m unittest -v 2>&1 | tail -10)
  ⎿  test_bagi (test_kalkulator.TesKalkulator.test_bagi) ... ok
     test_tambah (test_kalkulator.TesKalkulator.test_tambah) ... ok
     … +3 baris

Semua test sekarang lulus (2 dari 2).

Sebelumnya test_bagi gagal karena fungsi bagi di kalkulator.py memakai a * b, jadi bagi(10, 2)
menghasilkan 20. Saya ganti menjadi a / b. …

✓ Selesai  ·  8 langkah · 14.6 detik · ↓ 818 token · biaya: $0.0379 · total sesi: $0.0379
```

## Features

- **Claude Code look and feel**: see which files Claude reads, line-numbered diffs of its edits, the commands it
  runs, its todo list and its sub-agents, plus live token, cost and context usage.
- **Claude Code permission prompts**: `1` yes · `2` yes, and don't ask again (saved to
  `.claude/settings.local.json`) · `3` no, and tell Claude what to do instead.
- **Permission modes**: `default`, `acceptEdits` and `plan` (cycle with Shift+Tab), a plan approval panel, and
  `--yolo` for sandboxes.
- **Background agents and commands you can watch**: live progress under the prompt, `/tasks` and `/stop`, and
  Claude automatically follows up when they finish.
- **`/goal`**: Claude keeps working until a condition you define is met (built on Claude Code's own `/goal`).
- **Session control**: `/rewind` file changes, continue old conversations with `/resume` or `-c`, automatic
  reconnect after a crash.
- **Input shortcuts**: `!command` runs a shell command and hands the output to Claude, `@path` attaches files or
  folders, `# note` saves a note to `CLAUDE.md`.
- **Scriptable**: `-p` one-shot mode with meaningful exit codes for scripts and CI.
- **Billing safety**: it refuses to run unless it is authenticated with `ANTHROPIC_API_KEY`, so it never draws on a
  Claude Pro/Max subscription. An optional `--budget` caps what a session can spend.

## Requirements

- macOS or Linux (tested on macOS and Ubuntu 26.04). On Windows, use WSL.
- Python 3.10 or newer, and git.
- An Anthropic API key from the [Claude Console](https://platform.claude.com/settings/keys).

## Install

```bash
git clone https://github.com/imransetiadi/claude-code-mini.git
cd claude-code-mini
python3 claude-code-mini.py --setup
```

On Ubuntu/Debian, install the venv module first: `sudo apt install -y python3 python3-venv git`.
On macOS, the system Python (3.9) is too old: use `brew install python` or another Python 3.10+.

`--setup` creates a private virtualenv in `~/.local/share/claude-code-mini/venv`, installs `claude-agent-sdk`
(which bundles the Claude Code engine), `rich` and `prompt_toolkit`, and creates the `claude-code-mini` command in
`~/.local/bin`. If anything is still missing, it prints the exact command to fix it, such as adding
`~/.local/bin` to your `PATH` or storing your API key without echoing it to the screen:

```bash
# zsh (macOS default)
read -rs "K?API key: "; echo; echo "export ANTHROPIC_API_KEY=\"$K\"" >> ~/.zshrc; unset K; source ~/.zshrc
```

```bash
# bash (Linux)
read -rsp "API key: " K; echo; echo "export ANTHROPIC_API_KEY=\"$K\"" >> ~/.bashrc; unset K; source ~/.bashrc
```

Check the install with `claude-code-mini --help`.

## Usage

```bash
claude-code-mini ~/projects/my-app             # interactive session in that folder
claude-code-mini . --model sonnet --budget 5   # pick a model, cap spending at $5
claude-code-mini . --mode plan                 # plan first, execute after you approve
claude-code-mini . -c                          # continue the last conversation in this folder
claude-code-mini . -r                          # pick an older conversation
claude-code-mini . -p "explain this repo"      # one-shot: answer, then exit
claude-code-mini . -p "/goal all tests pass (pytest -q exits 0), at most 20 turns"
```

Inside a session:

| Key or command | What it does |
|---|---|
| `?` or `/help` | Show help |
| `!git status` | Run a shell command; its output goes to Claude with your next message |
| `@src/app.py` | Attach a file or folder (Tab completes paths) |
| `# always use pytest` | Save a note to `CLAUDE.md` (project memory) |
| Shift+Tab | Cycle the permission mode: default → acceptEdits → plan |
| Esc or Ctrl+C | Stop Claude while it is working |
| `/tasks`, `/stop 2` | Watch or stop background agents and commands |
| `/goal <condition>` | Keep working until the condition is met (`/goal` shows status, `/goal clear` cancels) |
| `/rewind` | Restore files to how they were before an earlier prompt |
| `/resume`, `/clear` | Switch to an older conversation, or start a fresh one |
| `/model`, `/mode`, `/status`, `/cost`, `/context` | Model, permission mode, session info, cost, context usage |
| Ctrl+D (or Ctrl+C twice) | Quit |

Other Claude Code commands, such as `/compact` and `/init`, and your own `.claude/commands/*.md` are passed through
to Claude Code.

Exit codes in `-p` mode:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Error, budget exhausted, a permission prompt with no terminal to answer it, missing API key, or the engine failed to start |
| `3` | A `/goal` is unfinished, was refused, or was dropped after an error |
| `130` | Interrupted with Ctrl+C |

## Full tutorial

The complete step-by-step guide covers installation, the screen layout, permissions, background agents, `/goal`,
CI usage, running on a server over SSH, and troubleshooting:

- **[English](docs/TUTORIAL.en.md)**
- **[Bahasa Indonesia](docs/TUTORIAL.md)**

## Update and uninstall

```bash
cd claude-code-mini && git pull && python3 claude-code-mini.py --setup   # update the script and libraries
claude-code-mini --setup                                                 # update the libraries only
```

```bash
rm -f ~/.local/bin/claude-code-mini ~/.claude-code-mini_history          # uninstall
rm -rf ~/.local/share/claude-code-mini
```

## How it works

claude-code-mini is a UI and control layer on top of the Python
[`claude-agent-sdk`](https://pypi.org/project/claude-agent-sdk/), which bundles the Claude Code engine. It only
reads project-level settings (`CLAUDE.md`, `.claude/settings.json`, `.claude/settings.local.json` and
`.claude/commands/`). Claude Code stores the conversations in `~/.claude/projects/`.

Tested on macOS and on Ubuntu 26.04 with Python 3.13 and 3.14, using claude-agent-sdk 0.2.178 and 0.2.179
(Claude Code engine 2.1.318 and 2.1.319).

## Notes

- API usage is billed to the Anthropic account that owns the key. Use `--budget` to cap a session.
- `--yolo` lets Claude run any command without asking. Use it only in a disposable sandbox.
- Use of Claude is subject to [Anthropic's terms](https://www.anthropic.com/legal/commercial-terms).

## License

Licensed under the [Apache License 2.0](LICENSE). Copyright 2026 Imran Setiadi.
