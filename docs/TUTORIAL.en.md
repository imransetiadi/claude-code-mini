# claude-code-mini: The Complete Tutorial

**English** · [Bahasa Indonesia](TUTORIAL.md)

This guide takes you from zero to the advanced features: background agents, `/goal`, and one-shot mode for scripts
and CI. The examples come from real sessions on macOS and Ubuntu 26.04.

> **About the language:** the app's interface is in Bahasa Indonesia. Screen examples are shown exactly as they
> appear, and the important messages are translated in the text or in the tables.

> In a hurry? Sections 2–4 are enough to get started (about 10 minutes). Read the rest as you go.

## Contents

1. [Getting to know it](#1-getting-to-know-it)
2. [Prerequisites](#2-prerequisites)
3. [Installation](#3-installation)
4. [Your first session](#4-your-first-session)
5. [Reading the screen](#5-reading-the-screen)
6. [Permissions and permission modes](#6-permissions-and-permission-modes)
7. [Typing messages](#7-typing-messages)
8. [Controlling Claude while it works](#8-controlling-claude-while-it-works)
9. [Managing conversations](#9-managing-conversations)
10. [Models, effort, and cost](#10-models-effort-and-cost)
11. [Background agents and commands](#11-background-agents-and-commands)
12. [/goal: keep working until it's done](#12-goal-keep-working-until-its-done)
13. [One-shot mode (-p) for scripts and CI](#13-one-shot-mode--p-for-scripts-and-ci)
14. [Claude Code built-in and custom commands](#14-claude-code-built-in-and-custom-commands)
15. [Per-project configuration](#15-per-project-configuration)
16. [Using it on an Ubuntu server over SSH](#16-using-it-on-an-ubuntu-server-over-ssh)
17. [Updating and uninstalling](#17-updating-and-uninstalling)
18. [Troubleshooting](#18-troubleshooting)
19. [FAQ](#19-faq)
20. [Appendix](#20-appendix)

---

## 1. Getting to know it

**claude-code-mini** is a terminal coding assistant that runs the Claude Code engine (through the
[Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/)), with a few differences:

- **It always uses an API key** (`ANTHROPIC_API_KEY`), so you pay per use through the Claude Console. If the Claude
  engine turns out to be using another login (for example a Claude Pro/Max subscription), claude-code-mini stops
  immediately so the usage is never billed to a subscription.
- **The interface is in Bahasa Indonesia.**
- **It is a single Python file.** Its libraries go into a private virtualenv, with no sudo and no global pip.

Inside it, Claude can do what it does in Claude Code: read and edit files (with line-numbered diffs), run commands,
keep a todo list, use sub-agents, run agents and commands in the background, plan mode, `/goal`, `/rewind`, and
continue old conversations. Tokens, cost, and context usage are always visible.

How the pieces fit:

```text
you ─▶ claude-code-mini ─▶ Claude Agent SDK ─▶ Claude Code engine ─▶ Anthropic API
       (UI, permissions,   (Python library)    (bundled with the SDK)
        status, cost)
```

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| Operating system | macOS or Linux (tested on macOS and Ubuntu 26.04). On Windows, use WSL. |
| Python | 3.10 or newer |
| git | to get the code and to update |
| Anthropic API key | from the Claude Console (section 2.3) |
| Internet | to `api.anthropic.com`, and to PyPI during installation |

### 2.1 macOS

The Python that ships with macOS (`/usr/bin/python3`) is version 3.9, which is too old. Install a newer Python
with [Homebrew](https://brew.sh):

```bash
brew install python git
python3 --version   # must be 3.10 or newer
```

If `python3 --version` still reports 3.9, call Homebrew's Python directly: `/opt/homebrew/bin/python3` (Apple
Silicon) or `/usr/local/bin/python3` (Intel).

### 2.2 Ubuntu / Debian

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
```

`python3-venv` is required on Ubuntu; without it, creating the virtualenv fails. `tmux` is optional but useful on
servers (section 16).

### 2.3 Creating an API key

1. Open the [Claude Console](https://platform.claude.com) (the old address `console.anthropic.com` redirects
   there) and sign in or sign up.
2. Add credits or set up billing. The API is billed per token.
3. Open the [API keys](https://platform.claude.com/settings/keys) page, create a new key, and copy it (it starts
   with `sk-ant-`). The key is shown only once.

> Treat the API key like a password: never commit it to git, and never paste it into a chat, an issue, or a
> screenshot.

## 3. Installation

### 3.1 Get the code and install

```bash
git clone https://github.com/imransetiadi/claude-code-mini.git
cd claude-code-mini
python3 claude-code-mini.py --setup
```

`--setup` does everything in one go:

1. Creates a virtualenv in `~/.local/share/claude-code-mini/venv`.
2. Installs `claude-agent-sdk` (which bundles the Claude Code engine), `rich`, and `prompt_toolkit` (plus
   `gnureadline` on macOS).
3. Copies the script to `~/.local/share/claude-code-mini/claude-code-mini.py`.
4. Creates the `~/.local/bin/claude-code-mini` command.
5. Checks your PATH and API key. If something is still missing, it prints the command that fixes it.

Example output on a clean Ubuntu 26.04 machine:

```text
→ Membuat virtualenv di /home/dev/.local/share/claude-code-mini/venv …
→ Memasang claude-agent-sdk>=0.2.178, rich>=13, prompt_toolkit>=3.0.40, gnureadline; sys_platform == 'darwin' …
✓ Library terpasang (/home/dev/.local/share/claude-code-mini/venv)
✓ Perintah claude-code-mini dibuat (/home/dev/.local/bin/claude-code-mini → /home/dev/.local/share/claude-code-mini/claude-code-mini.py)
! ~/.local/bin belum ada di PATH. Jalankan ini (sekali saja):
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
! ANTHROPIC_API_KEY belum di-set. Tambahkan ke ~/.bashrc (key tidak tampil di layar):
    read -rsp "API key: " K; echo; echo "export ANTHROPIC_API_KEY=\"$K\"" >> ~/.bashrc; unset K; source ~/.bashrc

Coba: claude-code-mini /path/ke/repo
Versi baru (setelah git pull / edit claude-code-mini.py) dipasang dengan: python3 /home/dev/claude-code-mini/claude-code-mini.py --setup
```

In English: it created the virtualenv, installed the libraries, and created the `claude-code-mini` command. Then
it warns that `~/.local/bin` is not on your PATH yet and that `ANTHROPIC_API_KEY` is not set, and shows the command
to run for each ("run this once"; "the key is not shown on screen"). The last lines say "try:
`claude-code-mini /path/to/repo`" and that new versions (after `git pull` or editing the file) are installed by
running `--setup` again.

### 3.2 Add `~/.local/bin` to your PATH (if asked)

Run the command that `--setup` printed. For macOS (zsh):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

For Ubuntu (bash):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

### 3.3 Store your API key (once)

These commands read the key without echoing it to the screen, then save it to your shell configuration. For macOS
(zsh):

```bash
read -rs "K?API key: "; echo; echo "export ANTHROPIC_API_KEY=\"$K\"" >> ~/.zshrc; unset K; source ~/.zshrc
```

For Ubuntu (bash):

```bash
read -rsp "API key: " K; echo; echo "export ANTHROPIC_API_KEY=\"$K\"" >> ~/.bashrc; unset K; source ~/.bashrc
```

If you use bash on macOS, replace `~/.zshrc` with `~/.bash_profile`. To check it without revealing the whole key:

```bash
echo "${ANTHROPIC_API_KEY:0:7}…"   # should print: sk-ant-…
```

### 3.4 Check the installation

```bash
claude-code-mini --help
```

If you see `usage: claude-code-mini …`, the installation is done.

> **Without `--setup`?** You can also run `python3 claude-code-mini.py` directly. If the libraries are missing, it
> offers to install them (`Pasang otomatis ke …? [Y/n]`, "install automatically into …?"). Only `--setup` creates
> the `claude-code-mini` command, though.

> The `claude-code-mini` command runs a **copy** of the script in `~/.local/share/claude-code-mini/`. After a
> `git pull` or after editing the file in your clone, run `python3 claude-code-mini.py --setup` again (section 17).

## 4. Your first session

Go to a project folder and start it:

```bash
cd ~/proyek/kalkulator
claude-code-mini
```

You can also run `claude-code-mini ~/proyek/kalkulator` from anywhere. That folder becomes Claude's workspace:
Claude may read anything inside it, and it asks before touching anything outside it.

A real session on Ubuntu 26.04, in a small project with `kalkulator.py` and its test file (some lines trimmed). The
prompt asks Claude to "run the tests, then fix whatever fails":

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

What happened:

1. Claude ran the tests. Because that is a Bash command, it asked first (`Claude minta izin`, "Claude asks for
   permission"). Answering `2` means "yes, and don't ask again for this command"; the rule is saved in
   `.claude/settings.local.json`.
2. The tests failed. Claude read `kalkulator.py`, found the bug (`bagi`, "divide", used `*` instead of `/`), and
   edited the file. The starting mode is `acceptEdits`, so the edit was applied right away, but the diff is still
   shown.
3. Claude ran the tests again without asking (already allowed), and this time they passed.
4. The `✓ Selesai` ("done") line sums up the turn: number of steps, duration, tokens, the cost of this turn, and the
   total cost of the session.

To quit, press **Ctrl+D**, type `/exit`, or press **Ctrl+C twice**. claude-code-mini then shows the total cost and
the command to continue this conversation later ("continue later with"):

```text
Total biaya: $0.0379 · Lanjutkan nanti dengan:
  claude-code-mini /home/dev/proyek/kalkulator --resume 93d57805-c135-45ea-88ae-2744df32bf27
```

## 5. Reading the screen

### 5.1 Activity lines

| On screen | Meaning |
|---|---|
| `● Read(kalkulator.py)` | Claude reads a file |
| `● Bash(python3 -m unittest -v)` | Claude runs a command |
| `● Update(kalkulator.py)` + diff | Claude edits a file (`-` removed, `+` added, with line numbers) |
| `● Write(…)` | Claude creates or overwrites a file |
| `● Update Todos` + checklist | Claude updates its todo list |
| `⎿ …` | the result of the tool above; long results are trimmed (`… +27 baris`, "+27 lines") |
| an indented purple `●` | activity of a sub-agent |

### 5.2 The spinner while Claude works

```text
⠋ Mengulik… Bash (12s · ↓ 1.2k token · esc untuk berhenti)
```

The verb rotates (Berpikir, Mengulik, Meracik, Ngoding, …: thinking, tinkering, brewing, coding, …). The line shows
the tool that is running, how long the turn has taken, output tokens, and a reminder that **Esc** stops Claude
(`esc untuk berhenti`). When a sub-agent is working, its progress (tool count, tokens, latest activity) is shown
too.

### 5.3 The toolbar under the prompt

```text
  ⏵⏵ auto-terima edit (shift+tab)  ·  sonnet-5-5 · konteks 12% · $0.0379 · ? untuk bantuan
```

From left to right: the permission mode (switch with Shift+Tab; `auto-terima edit` means "auto-accept edits"), the
model, context usage (`konteks`), and the total cost of the session. `? untuk bantuan` means "? for help". When a
goal is active or tasks run in the background, you also see items like `🎯 goal · 2m 10s · 3 cek (/goal)` (`cek` =
checks) and `⧗ 1 background (/tasks)`, plus one progress line per background task. The toolbar refreshes every
second, even while you type.

### 5.4 End-of-turn status

| Line | Meaning |
|---|---|
| `✓ Selesai · 8 langkah · 14.6 detik · ↓ 818 token · biaya: $0.0379 · total sesi: $0.0379` | the turn finished normally (steps, seconds, tokens, cost, session total) |
| `⏹ Dihentikan oleh user · ketik instruksi baru, atau 'lanjutkan'` | you pressed Esc or Ctrl+C ("stopped by user; type a new instruction, or 'lanjutkan' to continue") |
| `✗ Berhenti: batas budget $5 tercapai.` | the `--budget` limit was reached |
| `✗ Berhenti (…)` | the turn ended with an error |
| `🔄 Menyambung ulang (1/3)…` | the Claude engine crashed or the connection dropped; it is reconnecting automatically |

## 6. Permissions and permission modes

### 6.1 What needs permission?

| Kind of tool | Behavior |
|---|---|
| Read-only and notes: `Read`, `Glob`, `Grep`, `TodoWrite`, `WebSearch`, `WebFetch` | always run without asking (including opening web pages) |
| File edits: `Edit`, `Write`, … | applied right away in `acceptEdits` mode (the starting mode); asked in `default` mode |
| `Bash` and other tools | asked, unless already allowed |
| `AskUserQuestion` | disabled; Claude asks in plain text instead |

### 6.2 The permission panel

```text
╭─ 🔐 Claude minta izin ──────────────────╮
│ Bash                                    │
│ python3 -m unittest -v 2>&1 | tail -40  │
╰─────────────────────────────────────────╯
  1 Ya
  2 Ya, dan jangan tanya lagi untuk Bash(python3 -m unittest -v) (disimpan di .claude/settings.local.json)
  3 Tidak, dan beri tahu Claude harus bagaimana
Pilih [1/2/3, Enter=1] ›
```

The options read: 1 "Yes", 2 "Yes, and don't ask again for … (saved in …)", 3 "No, and tell Claude what to do".

| Answer | Effect |
|---|---|
| `1` or Enter | allow this once |
| `2` | allow, and save the rule suggested by Claude Code to the project's `.claude/settings.local.json` (it keeps applying in that project). If there is no suggested rule, the tool stays allowed until you close claude-code-mini. |
| `3` | deny, then (optionally) type an instruction for Claude, e.g. "just use pytest -q" |
| Ctrl+C | cancel: the request is denied and the turn stops |

Careful: pressing Enter without a number means **Yes**.

When the request comes from a sub-agent or a background agent, the panel title names it, for example
`Agent #2 “cari pemakaian fungsi X” (background) · Claude minta izin`.

### 6.3 Permission modes

| Mode | Toolbar label | Behavior |
|---|---|---|
| `default` | `? tanya dulu sebelum edit & command` ("ask before edits & commands") | file edits and commands are asked |
| `acceptEdits` (**starting mode**) | `⏵⏵ auto-terima edit` ("auto-accept edits") | file edits are applied right away; commands are still asked |
| `plan` | `⏸ plan mode` | Claude only investigates and writes a plan; nothing changes until you approve it |
| `bypassPermissions` (`--yolo`) | `⚠ YOLO: tanpa izin` ("no permissions") | every tool runs without asking |
| `dontAsk` | `dontAsk` | never asks: anything not already allowed is denied |
| `auto` | `⏵ auto mode` | permission decisions go to Claude Code's automatic checker (a newer feature; depends on the Claude Code version) |

How to switch modes:

- **Shift+Tab** at the prompt cycles `default → acceptEdits → plan → default`. Whatever you are typing is kept.
- `/mode <name>`, for example `/mode plan`. `/mode` on its own shows the current mode.
- At startup: `--mode plan`, or `--yolo` (same as `--mode bypassPermissions`).

### 6.4 Plan mode

Plan mode suits bigger changes: Claude investigates first, then presents a plan for you to approve.

```text
╭─ 📋 Rencana dari Claude ───────────────╮
│ 1. Tambah fungsi ekspor_csv() …        │
│ 2. …                                   │
╰────────────────────────────────────────╯
  1 Ya, mulai dan auto-terima edit
  2 Ya, tapi tanya dulu setiap edit
  3 Tidak, lanjut merencanakan
Setujui rencana? [1/2/3, Enter=1] ›
```

`Rencana dari Claude` is "Claude's plan" and `Setujui rencana?` is "approve the plan?". `1` ("yes, start and
auto-accept edits") runs the plan in `acceptEdits` mode, `2` ("yes, but ask before every edit") in `default` mode.
`3` ("no, keep planning") asks what should change, and Claude revises the plan.

Example: `claude-code-mini ~/project --mode plan`, then type something like "design a feature that exports the
report to CSV".

### 6.5 YOLO mode

`--yolo` lets every tool run without asking, including `rm`, `git push`, and the like. Use it only in a disposable
container/VM, or in a repository that is safe to reset.

Claude Code refuses YOLO mode when run as root/sudo. Run it as a normal user. For disposable containers/VMs only,
there is a shortcut: `IS_SANDBOX=1 claude-code-mini . --yolo`.

### 6.6 Viewing and revoking permissions

- `/allow` lists the tools allowed automatically, the permissions granted this session, and the rules saved in
  `.claude/settings*.json`.
- `/allow reset` clears this session's permissions (the rule files are not changed).
- To revoke a permanent rule, edit the project's `.claude/settings.local.json` (the `permissions.allow` list).

## 7. Typing messages

| Type | What it does |
|---|---|
| Enter | send the message |
| `\` at the end of a line, then Enter, or Alt+Enter | new line (multi-line message) |
| ↑ / ↓ | message history (stored in `~/.claude-code-mini_history`) |
| Tab | complete `/commands` and `@paths` |
| `?` | same as `/help` |
| `!command` | run a shell command yourself |
| `@path` | attach a file or folder |
| `# note` | save a note to `CLAUDE.md` |

Pasted multi-line text becomes a single message automatically. In the macOS Terminal, Alt (Option)+Enter only works
after you enable "Use Option as Meta key" (in iTerm2: Option key → Esc+). Otherwise, use `\` and then Enter.

### 7.1 `!command`: run a command yourself

```text
› !git status --short
! git status --short
  ⎿ M kalkulator.py
  (output akan ikut dikirim ke Claude bersama pesan berikutnya)
› summarize these changes and suggest a commit message
```

- It runs in the project folder with your shell, with a 10-minute time limit.
- The screen shows at most 30 lines of output; Claude receives up to the last 30,000 characters, together with your
  next message (that is what the grey line says).
- No permission is needed, because you typed it yourself.

### 7.2 `@path`: attach a file or folder

```text
› explain the main flow in @src/app.py and @src/utils/
  ⎿ Melampirkan @src/app.py (120 baris)
  ⎿ Melampirkan isi folder @src/utils/ (5 item)
```

- A file's content is attached ("attaching … (120 lines)"), up to 200 KB; the rest is cut off. Binary files are
  skipped.
- For a folder, its listing is attached (without `.git`, `node_modules`, `__pycache__`).
- Tab completes paths. For paths with spaces, write `\ `, e.g. `@final\ report.md`.

### 7.3 `# note`: project memory

```text
› # always run the tests with python3 -m unittest
✓ Disimpan ke memori proyek (CLAUDE.md)
```

The note is appended as a `- …` bullet to `CLAUDE.md` (created if missing): "saved to project memory". Claude reads
this file in every session and is told about the new note right away. Lines starting with `##` are not treated as
notes.

### 7.4 Typing while Claude works

You can start typing your next message while Claude is still working. Nothing you type is lost: when the turn ends,
the text is already waiting at the prompt, and you just press Enter.

## 8. Controlling Claude while it works

| Key or command | Effect |
|---|---|
| Esc or Ctrl+C (while Claude works) | stop the current turn. The context is kept; type a new instruction or `lanjutkan` ("continue"). |
| Ctrl+C twice within 2 seconds (at the prompt) | quit |
| Ctrl+D (at the prompt) | quit |
| `/rewind` | restore files to how they were before an earlier prompt |

### 8.1 `/rewind`

```text
› /rewind
Kembalikan file ke kondisi sebelum prompt:
   1 add input validation
   2 run the tests, then fix whatever fails
Pilih nomor (Enter untuk batal) › 1
✓ File dikembalikan ke kondisi sebelum: add input validation
```

("Restore files to how they were before the prompt:" · "Pick a number (Enter to cancel)" · "Files restored to how
they were before: …")

- The list holds up to the last 10 prompts of this conversation; number 1 is the most recent.
- Only changes made through Claude's editing tools (`Edit`, `Write`, …) are restored. The effects of Bash commands
  (e.g. `rm`, `git commit`, `npm install`) are **not** undone; use git for those.
- Claude is told that you rewound, so it is not confused by your next message.

### 8.2 Automatic recovery

If the Claude engine crashes or the connection drops, claude-code-mini reconnects by itself (up to 3 times in a row)
and continues the same conversation:

```text
🔄 Menyambung ulang (1/3)… percakapan dilanjutkan, konteks tetap ada.
Tugas terakhir terhenti. Ketik 'lanjutkan' untuk meneruskan, atau beri instruksi lain.
```

("Reconnecting (1/3)… the conversation continues, the context is kept. The last task was interrupted. Type
'lanjutkan' to continue, or give another instruction.")

### 8.3 Keeping the Mac awake

On macOS, the Mac is kept from sleeping while claude-code-mini runs (like `caffeinate -i`), so long jobs are not
cut off. This stops automatically when you quit. To turn it off, start it with
`CCMINI_NO_CAFFEINATE=1 claude-code-mini`.

## 9. Managing conversations

Claude Code saves every conversation automatically, per folder, in `~/.claude/projects/`.

| How | What it does |
|---|---|
| `claude-code-mini -c` | continue the last conversation in this folder |
| `claude-code-mini -r` | pick from a list of older conversations |
| `claude-code-mini --resume <ID>` | continue a specific conversation (the ID is shown when you quit) |
| `/resume` | switch to an older conversation without quitting |
| `/clear` | start a new conversation (the old context is dropped) |
| `/compact [instructions]` | summarize the conversation to free up context (a Claude Code command) |
| `/context` | show context usage, broken down by category |

Example list from `/resume` or `-r` ("older conversations in this folder", with how long ago and the git branch):

```text
Percakapan lama di folder ini:
   1    5 menit lalu  run the tests, then fix whatever fails ⎇ main
   2      2 jam lalu  add a CSV export feature ⎇ feature/csv
Pilih nomor (Enter untuk batal) ›
```

When a conversation is continued, its last few messages are shown as a reminder. Claude Code's auto-compact stays
on: when the context is nearly full, the conversation is summarized automatically.

## 10. Models, effort, and cost

| Alias | Model |
|---|---|
| `opus` (default) | `claude-opus-5-5` |
| `sonnet` | `claude-sonnet-5-5` |
| `haiku` | `claude-haiku-5-5` |
| `fable` | `claude-fable-5-1` |

- At startup: `claude-code-mini --model sonnet` (or the full ID of any other model).
- During a session: `/model` shows the current model, `/model haiku` switches.
- `--effort low|medium|high|xhigh|max` sets how hard Claude thinks (default: the model's own setting).
- `--budget 5` caps this session's cost at $5. When it is reached, Claude stops with
  `✗ Berhenti: batas budget $5 tercapai.` ("stopped: budget limit of $5 reached").
- `/cost` shows the total cost. `/status` summarizes the session: folder, model, mode, auth source, session ID,
  Claude Code version, background tasks, goal, and cost.

Saving money:

- Use `haiku` for light tasks (short explanations, renames) and `sonnet`/`opus` for heavy work.
- `/clear` when you switch topics, `/compact` when a conversation gets long.
- Attach only the files you need.
- Always set `--budget` for long or unattended jobs.

## 11. Background agents and commands

Claude can run long commands (dev servers, builds, test suites) or sub-agents in the background while it keeps
helping you. Just ask, for example:

- "run npm run dev in the background, then check that the home page loads"
- "use a background agent to find every use of the calculate_tax function; meanwhile, explain the folder structure"

While tasks run, the toolbar looks roughly like this:

```text
  ⏵⏵ auto-terima edit (shift+tab)  ·  opus-5-5 · konteks 9% · $0.0412  ·  ⧗ 2 background (/tasks)
  ⧗ #1 Jalankan server dev · bash · 1m 05s · ⎿ ready on http://localhost:3000
  ⧗ #2 Cari pemakaian hitung_pajak · agent · 40s · 12 tool · 8.1k token · Grep(hitung_pajak)
```

- Progress is shown live under the prompt and refreshes every second, even while you type. For a command you see its
  last output line; for an agent, its latest activity.
- The agents' activity log is printed above the prompt. `/tasks log` turns it off or on.
- When a task finishes, claude-code-mini announces it and Claude **automatically follows up on the result**
  (`✓ Respons otomatis selesai`, "automatic response done"). Esc stops that automatic response.
- Permission requests from background agents appear above the prompt, with the agent's name.

| Command | What it does |
|---|---|
| `/tasks` | list all agents and background tasks (running and finished) |
| `/tasks 2` | details of task #2: the task, latest activity, and the last output (command) or report (agent) |
| `/tasks log` | turn the on-screen activity log on or off |
| `/stop 2` | stop task #2 (`/kill 2` works too) |
| `/stop all` | stop every background task |

Background tasks stop when the Claude process is closed (`/exit`, `/clear`, `/resume`); claude-code-mini asks you
first. In `-p` mode, claude-code-mini waits for all background tasks (and Claude's follow-up on their results) to
finish before it exits.

## 12. /goal: keep working until it's done

`/goal` makes Claude keep working until a condition you define is met. It uses Claude Code's own `/goal`: every time
Claude is about to stop, an evaluator (a small model) reads the conversation and judges whether the condition is
met. If it is not, Claude keeps working in the same turn.

Example (screen text is Indonesian; translations below):

```text
› /goal all tests pass (python3 -m unittest exits 0) and git status is clean, at most 20 turns
🎯 Goal ditetapkan: all tests pass (python3 -m unittest exits 0) and git status is clean, at most 20 turns
   Claude langsung mengerjakannya. Tiap kali ia mau berhenti, pemeriksa (model kecil, kena biaya per cek) …
   …
🎯 Cek goal #1 · belum terpenuhi · git status still shows uncommitted changes
   …
🎯 Goal berakhir: all tests pass (…) · 1 cek · 1m 12s · biaya $0.0831
   pemeriksa menilai kondisinya terpenuhi — atau mustahil dicapai; lihat jawaban terakhir Claude di atas.
```

`Goal ditetapkan` = "goal set" (followed by a short explanation the first time). `Cek goal #1 · belum terpenuhi` =
"goal check #1 · not met yet", followed by the evaluator's reason. `Goal berakhir` = "goal ended", with checks,
duration, and cost; the grey line says "the evaluator judged the condition met — or impossible to reach; see
Claude's last answer above".

| Command | What it does |
|---|---|
| `/goal <condition>` | set a goal (replacing the previous one) and start right away |
| `/goal` | status: condition, duration, number of checks, the last check's reason, cost since the goal was set |
| `/goal clear` | cancel the goal (also: `stop`, `off`, `reset`, `none`, `cancel`, `batal`, `hapus`) |

Good to know:

- While a goal is active, the toolbar shows `🎯 goal · 2m 10s · 3 cek` (with `⏸` when paused), and `/status` has a
  Goal row.
- The goal stays active across your next messages, until the evaluator judges it done or you cancel it.
- **Esc** only pauses the goal (`⏸ Goal dijeda · dihentikan user`, "goal paused · stopped by user"). Send any
  message (e.g. `lanjutkan`) to resume.
- If Claude is judged not done several times in a row without using any tool, the turn is ended forcibly and the
  goal is paused. This usually means the condition cannot be proven from the conversation, or Claude needs input
  from you. The limit is Claude Code's default (8) and can be changed with `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`.
- `🎯 Goal berakhir` is deliberately neutral: Claude Code does not say whether the condition was **met** or the
  evaluator judged it **impossible**. Read Claude's last answer to be sure.
- Continuing a conversation (`--resume`, `-c`) also restores an unfinished goal; `/clear` cancels it.
- In `plan` mode Claude cannot edit files, so a goal that needs file changes can never be met (claude-code-mini warns
  you). In `default`/`acceptEdits` mode, commands that are not allowed yet are still asked; answer `2` (don't ask
  again), or use `--yolo` in a sandbox if you want to leave it running unattended.
- Each check is one small API call: cheap, but counted. The number of checks appears in the turn statistics
  (`🎯 N cek`).

Writing good conditions:

| ✅ Good | ❌ Not so good |
|---|---|
| `pytest -q exits 0 and git status is clean, at most 20 turns` | `the code is tidy` |
| `curl -s localhost:8000/health returns {"ok":true}, at most 15 turns` | `the server runs fine` |
| `docs/API.md exists and covers every endpoint in app/routes.py` | `the docs are complete` |

Two principles: (1) the condition can be proven from output visible in the conversation, because the evaluator
does not run anything itself; (2) set a turn limit, because there is none by default.

## 13. One-shot mode (-p) for scripts and CI

```bash
claude-code-mini ~/project -p "explain this repo's architecture in 10 points" > summary.txt
claude-code-mini . --model haiku -p "find forgotten TODOs and list them"
claude-code-mini . --budget 3 -p "/goal all tests pass (pytest -q exits 0), at most 20 turns"
```

- The banner is not shown; Claude's activity and answer are printed as plain text.
- Prompts that start with `/` are sent as they are, e.g. `-p "/compact"` or `-p "/goal …"`.
- claude-code-mini waits for background tasks to finish before it exits.
- If a goal is unfinished, it prints the command to continue: `claude-code-mini <folder> --resume <ID>`. Continue
  interactively, or keep it unattended with `claude-code-mini <folder> --resume <ID> -p "lanjutkan"`.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | failure: an error, the budget ran out, a permission prompt with no terminal to answer it, a missing API key, or the Claude engine failed to start |
| `3` | a `/goal` is unfinished, was refused, or was dropped after an error |
| `130` | interrupted with Ctrl+C in a terminal |

In a script:

```bash
if claude-code-mini . --budget 2 -p "/goal pytest -q exits 0, at most 15 turns"; then
  echo "done"
else
  echo "not done (exit $?)"
fi
```

About permissions: in `-p` mode, permission prompts still appear when there is a terminal. In CI or cron (no
terminal), they are denied automatically (`✗ Izin Bash ditolak: tidak ada terminal untuk menjawab.`, "Bash
permission denied: no terminal to answer"), the turn stops, and the exit code is 1. Prepare permission rules in
`.claude/settings.json` (section 15), or run in a disposable container with `--yolo`.

## 14. Claude Code built-in and custom commands

The commands handled by claude-code-mini itself are listed in appendix B. Any other command Claude Code knows is
passed through as is, for example:

- `/compact [instructions]` to summarize the conversation.
- `/init` to create a `CLAUDE.md` based on the project.

The full list (it depends on your Claude Code version and your project) is in `/help`, under "Perintah Claude Code /
proyek" ("Claude Code / project commands"), and appears when you press Tab after `/`.

### Custom commands

Create a Markdown file in the project's `.claude/commands/`. The file name becomes the command name:

```bash
mkdir -p .claude/commands
cat > .claude/commands/release.md <<'EOF'
Prepare release $ARGUMENTS:
1. Update CHANGELOG.md from the commits since the last tag.
2. Bump the version in pyproject.toml.
3. Run the tests; stop if anything fails.
EOF
```

Then type `/release 1.4.0` in claude-code-mini. `$ARGUMENTS` is replaced with the text after the command name.

## 15. Per-project configuration

claude-code-mini reads **project-level** settings only:

| File | Purpose |
|---|---|
| `CLAUDE.md` | standing instructions for Claude: how to run tests, code style, things to avoid. Create it with `/init`, add to it with `# note`. |
| `.claude/settings.json` | shared permission rules (fine to commit) |
| `.claude/settings.local.json` | personal permission rules; answers of "2 (don't ask again)" are saved here. Best added to `.gitignore`. |
| `.claude/commands/*.md` | custom commands (section 14) |

User-level settings (`~/.claude/settings.json`, `~/.claude/CLAUDE.md`) are not used.

Example `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["Bash(npm test:*)", "Bash(npm run lint)", "Bash(git status)", "Bash(git diff:*)"],
    "deny": ["Bash(git push:*)", "Read(./.env)"]
  }
}
```

## 16. Using it on an Ubuntu server over SSH

```bash
ssh -i key.pem ubuntu@SERVER-ADDRESS
sudo apt update && sudo apt install -y python3 python3-venv git tmux
git clone https://github.com/imransetiadi/claude-code-mini.git
python3 claude-code-mini/claude-code-mini.py --setup
```

Then store your API key (section 3.3, bash version) and, if asked, add `~/.local/bin` to your PATH.

Use **tmux** so your work survives a dropped SSH connection:

```bash
tmux new -s ccm              # open a tmux session named ccm
claude-code-mini ~/project   # work as usual
# detach: press Ctrl+B, then D (claude-code-mini keeps running on the server)
tmux attach -t ccm           # reattach later
```

Tips:

- Don't run it as root. Claude Code refuses YOLO mode for root (except with `IS_SANDBOX=1` in a disposable
  container/VM).
- Want to run it straight from your laptop without opening a shell, like `ssh server 'claude-code-mini … -p …'`?
  Ubuntu's default `~/.bashrc` returns early for non-interactive shells, so an `ANTHROPIC_API_KEY` placed near the
  bottom is never read. Move the `export ANTHROPIC_API_KEY=…` and PATH lines to the very top of `~/.bashrc`, or run
  it through `bash -lic '…'`.

## 17. Updating and uninstalling

Update to the latest version:

```bash
cd ~/claude-code-mini     # the folder you cloned
git pull
python3 claude-code-mini.py --setup
```

To update only the libraries (e.g. `claude-agent-sdk`, which brings the latest Claude Code engine):

```bash
claude-code-mini --setup
```

Uninstall:

```bash
rm -f ~/.local/bin/claude-code-mini ~/.claude-code-mini_history
rm -rf ~/.local/share/claude-code-mini
```

Also delete the cloned folder and the `export ANTHROPIC_API_KEY=…`/PATH lines in `~/.zshrc` or `~/.bashrc` if you no
longer need them. Conversation history lives in `~/.claude/projects/` (shared with the official Claude Code); delete
it by hand if needed.

## 18. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ANTHROPIC_API_KEY belum di-set.` ("not set") | The key is not exported in this shell. Repeat section 3.3, or open a new terminal. |
| `✗ Dihentikan: Claude memakai auth '…', bukan ANTHROPIC_API_KEY.` ("stopped: Claude uses auth '…', not ANTHROPIC_API_KEY") | The Claude engine is using another login, so claude-code-mini stops on purpose to avoid drawing on a subscription. Make sure `ANTHROPIC_API_KEY` is exported in the same terminal. |
| `✗ Butuh Python 3.10 atau lebih baru` ("needs Python 3.10 or newer") | Install a newer Python (section 2.1/2.2), then run `--setup` with it. |
| `✗ Gagal membuat virtualenv` ("failed to create the virtualenv"), or an error about `ensurepip` | Ubuntu/Debian: `sudo apt install -y python3-venv`, then repeat `--setup`. |
| `✗ pip install gagal` ("pip install failed") | Check your internet/proxy access to PyPI, then repeat `--setup`. |
| `claude-code-mini: command not found` | `~/.local/bin` is not on your PATH (section 3.2), or open a new terminal. |
| `Binary Claude Code tidak ditemukan.` ("Claude Code binary not found") | The library install is incomplete. Run `python3 claude-code-mini.py --setup`. |
| `✗ Mesin Claude Code gagal start` ("the Claude Code engine failed to start") | Check internet/proxy access to `api.anthropic.com` and that the API key is valid, then update with `--setup`. Details from the engine appear above this message. |
| `Output tool terlalu besar untuk buffer (64 MB)` ("tool output too large for the buffer") | Start with `--buffer-mb 128`, or ask Claude to read files in parts. |
| `⚠ Rate limit: …` | Your account's API limit was reached. Wait a moment, or check your limits in the Claude Console. |
| `Claude Code menolak mode YOLO kalau dijalankan sebagai root/sudo` ("Claude Code refuses YOLO mode as root/sudo") | Run as a normal user. In disposable containers/VMs only: `IS_SANDBOX=1`. |
| Alt+Enter doesn't add a new line (macOS) | Enable "Use Option as Meta key" in Terminal, or end the line with `\`. |
| The toolbar or Esc key doesn't work on Windows | Run it in WSL. |

## 19. FAQ

**How much does it cost?**
It depends on the model and the length of the work; Anthropic bills per token. The cost per turn and the session
total are always visible (in the toolbar, on the `✓ Selesai` line, and via `/cost`). The example in section 4
(Sonnet, 8 steps) cost about $0.04. Cap it with `--budget`.

**Does it use my Claude Pro/Max subscription quota?**
No. claude-code-mini only runs with `ANTHROPIC_API_KEY`; if it detects any other login source, it stops.

**How is it different from the official Claude Code?**
The engine is the same. claude-code-mini adds an Indonesian interface, live cost and token info, background-task
monitoring in the toolbar, and the API key safeguard. On the other hand, a few things are not available: the
multiple-choice question tool (`AskUserQuestion`), IDE integration, subscription login, and user-level settings.

**Does it work on Windows?**
Through WSL (Ubuntu). On native Windows, the Esc key is not supported and the `claude-code-mini` command is not
created.

**Where are conversations stored?**
In `~/.claude/projects/`, in Claude Code's format. Your typing history is in `~/.claude-code-mini_history`.

## 20. Appendix

### A. Command-line options

```text
usage: claude-code-mini [-h] [--model MODEL]
                        [--mode {default,acceptEdits,plan,auto,bypassPermissions,dontAsk}]
                        [--effort {low,medium,high,xhigh,max}]
                        [--budget BUDGET] [--yolo] [-c] [-r [SESSION_ID]]
                        [-p PROMPT] [--buffer-mb BUFFER_MB] [--setup]
                        [repo]
```

| Option | What it does |
|---|---|
| `repo` | the project folder (default: the current folder) |
| `--model MODEL` | a model or the alias `opus`/`sonnet`/`haiku`/`fable` (default: `claude-opus-5-5`) |
| `--mode MODE` | the starting permission mode (default: `acceptEdits`) |
| `--effort LEVEL` | `low`, `medium`, `high`, `xhigh`, `max` |
| `--budget USD` | the session's cost limit, e.g. `5` |
| `--yolo` | every tool without asking (`bypassPermissions`) |
| `-c`, `--continue` | continue the last conversation |
| `-r`, `--resume [ID]` | continue an older conversation (without an ID: pick from a list) |
| `-p`, `--print PROMPT` | one-shot, then exit (exit codes in section 13) |
| `--buffer-mb MB` | the tool-output size limit (default: 64) |
| `--setup` | install/update the libraries and the `claude-code-mini` command |

### B. In-session commands

| Command | What it does |
|---|---|
| `/help` (or `?`) | help |
| `/status` | session info: model, mode, folder, session ID, auth, Claude Code version, background tasks, goal, cost |
| `/cost` | the session's total cost |
| `/context` | context window usage |
| `/model [alias or ID]` | show or switch the model |
| `/mode [name]` | show or switch the permission mode |
| `/allow` / `/allow reset` | show permissions / clear this session's permissions |
| `/tasks` / `/tasks <no>` / `/tasks log` | list background tasks / details / log on-off |
| `/stop <no>` / `/stop all` | stop background tasks (alias `/kill`) |
| `/goal [condition]` / `/goal clear` | set a goal or show its status / cancel the goal |
| `/resume` | continue an older conversation in this folder |
| `/rewind` | restore files to how they were before an earlier prompt |
| `/clear` | start a new conversation |
| `/exit` (or `/quit`) | quit |

### C. Keys

| Key | What it does |
|---|---|
| Enter | send the message |
| `\` + Enter, Alt+Enter | new line |
| Tab | complete `/commands` and `@paths` |
| ↑ / ↓ | message history |
| Shift+Tab | switch the permission mode |
| Esc | stop Claude, or close the completion menu |
| Ctrl+C | stop Claude; at the prompt press it twice to quit; in a question = cancel |
| Ctrl+D | quit |

### D. Files and folders

| Location | Contents |
|---|---|
| `~/.local/bin/claude-code-mini` | the launcher command |
| `~/.local/share/claude-code-mini/claude-code-mini.py` | the copy of the script that actually runs |
| `~/.local/share/claude-code-mini/venv/` | libraries: claude-agent-sdk (with the Claude Code engine), rich, prompt_toolkit |
| `~/.claude-code-mini_history` | your typing history |
| `~/.claude/projects/` | conversations (Claude Code format) |
| `<project>/CLAUDE.md`, `<project>/.claude/` | project settings (section 15) |

If `XDG_DATA_HOME` is set, the data folder moves to `$XDG_DATA_HOME/claude-code-mini`.

### E. Environment variables

| Variable | What it does |
|---|---|
| `ANTHROPIC_API_KEY` | the API key (required) |
| `CCMINI_NO_CAFFEINATE=1` | macOS: don't keep the Mac awake |
| `IS_SANDBOX=1` | allow YOLO mode as root (disposable containers/VMs only) |
| `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` | the limit on consecutive `/goal` rejections (Claude Code default: 8) |
| `XDG_DATA_HOME` | where the data folder lives (default: `~/.local/share`) |

## License

claude-code-mini is licensed under the [Apache License 2.0](../LICENSE).
