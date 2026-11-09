#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Imran Setiadi
"""
claude-code-mini - Claude Code versi mini yang jalan pakai API key (Claude Agent SDK).
https://github.com/imransetiadi/claude-code-mini

Tampilannya dibuat mirip Claude Code: kelihatan Claude lagi baca file apa,
ngedit apa (lengkap dengan diff bernomor baris), jalanin command apa, todo list,
hasil tool, lama kerja, token, biaya, dan pemakaian konteks. Command Bash dan tool
berisiko lain minta izin dulu, dan "jangan tanya lagi" bisa disimpan permanen
ke .claude/settings.local.json persis seperti Claude Code.

Instalasi (sekali) - Ubuntu 26.04 / Linux / macOS:
    git clone https://github.com/imransetiadi/claude-code-mini.git
    python3 claude-code-mini/claude-code-mini.py --setup
        # -> pasang library ke ~/.local/share/claude-code-mini/venv
        #    + bikin perintah `claude-code-mini` di ~/.local/bin
    echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc && source ~/.bashrc   # macOS: ~/.zshrc
    (Ubuntu: kalau muncul error venv/ensurepip, jalankan dulu: sudo apt install -y python3-venv)
    Library juga otomatis ditawarkan untuk dipasang kalau belum ada. Tidak perlu sudo / pip global.

Instalasi (sekali) - Windows 11, di PowerShell (Windows Terminal):
    winget install -e --id Python.Python.3.13      # Python 3.10+ (python.org / winget)
    winget install -e --id Git.Git                 # disarankan: Claude menjalankan command lewat Git Bash
    git clone https://github.com/imransetiadi/claude-code-mini.git   # atau download ZIP dari GitHub
    py claude-code-mini\\claude-code-mini.py --setup
        # -> library ke %USERPROFILE%\\.local\\share\\claude-code-mini\\venv
        #    + perintah claude-code-mini.exe di %USERPROFILE%\\.local\\bin
        #    + menampilkan perintah PowerShell untuk PATH dan API key (key tidak tampil di layar)
    Tanpa Git for Windows, Claude memakai PowerShell untuk menjalankan command.

Pakai:
    claude-code-mini /path/ke/repo        # atau: python3 claude-code-mini.py /path/ke/repo
    claude-code-mini /path/ke/repo --model sonnet --budget 5
    claude-code-mini /path/ke/repo --mode plan   # rencana dulu, eksekusi setelah disetujui
    claude-code-mini /path/ke/repo -c            # lanjutkan percakapan terakhir
    claude-code-mini /path/ke/repo -r            # pilih percakapan lama untuk dilanjutkan
    claude-code-mini /path/ke/repo -p "jelaskan repo ini"   # sekali jalan, lalu keluar
    claude-code-mini /path/ke/repo -p "/goal semua test di tests/ lulus"   # kerja terus sampai
                                                 # kondisi terpenuhi (exit code 3 kalau belum)
    claude-code-mini /path/ke/repo --yolo        # semua tool tanpa tanya (hati-hati!)
    claude-code-mini /path/ke/repo --gui         # tampilan GUI di browser (server lokal 127.0.0.1 + token)
    claude-code-mini /path/ke/repo --gui --no-browser   # di server: buka URL-nya lewat ssh -L 8765:127.0.0.1:8765
    claude-code-mini --setup                     # update library (claude-agent-sdk dkk.)
    git pull && python3 claude-code-mini.py --setup   # di folder clone: update script-nya juga

Di dalam sesi (ketik ? atau /help):
    !ls -la          jalankan command shell langsung, output-nya masuk konteks Claude
    @src/main.py     lampirkan file/folder ke pesan (Tab untuk melengkapi path)
    # selalu pakai pytest   simpan catatan ke CLAUDE.md (memori proyek)
    /tasks           pantau agent & command yang jalan di background (progres, log, output)
    /stop 2          hentikan tugas background nomor 2 (/stop all = semuanya)
    /goal kondisi    Claude kerja terus sampai kondisi terpenuhi (/goal = status, /goal clear = batal)
    Shift+Tab        ganti mode izin: default -> acceptEdits -> plan
    Esc / Ctrl+C     hentikan Claude saat sedang bekerja
    Ctrl+C 2x / Ctrl+D di prompt  -> keluar

Kolom chat tetap bisa dipakai saat Claude sedang bekerja (seperti Claude Code): pesan yang
dikirim saat itu langsung diteruskan dan dibaca Claude begitu langkah (tool) yang sedang jalan
selesai - tidak perlu menunggu giliran berakhir. /perintah, !command, dan # catatan yang diketik
saat Claude bekerja antre sampai giliran selesai; /tasks, /help, /status, /cost, /stop, /mode
langsung dijalankan.

Agent / command background tetap terpantau walau Claude sudah selesai menjawab:
progresnya (tool terakhir, jumlah tool, token, durasi, baris output terakhir) tampil
live di bawah prompt, log aktivitasnya muncul di layar, dan begitu selesai Claude
otomatis menanggapi hasilnya - persis seperti Claude Code.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import base64
import contextlib
import difflib
import html as htmllib
import inspect
import io
import json
import logging
import os
import random
import re
import secrets
import select
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import warnings
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Prompt utama memakai prompt_toolkit (riwayat, Tab completion, Shift+Tab, paste, status live).
# readline cuma dipakai untuk pertanyaan singkat (izin, pilih nomor) lewat input() biasa.
# Python dari Homebrew / python.org di macOS memakai libedit; `gnureadline` (dipasang --setup
# di macOS) memberi GNU readline asli, jadi dipakai duluan kalau ada.
try:
    import gnureadline as readline  # type: ignore[import-not-found]
except ImportError:
    try:
        import readline
    except ImportError:  # mis. Windows tanpa pyreadline
        readline = None  # type: ignore[assignment]

try:
    import termios
    import tty
except ImportError:  # Windows: tidak ada termios; tombol Esc dibaca lewat msvcrt
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]
try:
    import msvcrt
except ImportError:  # selain Windows
    msvcrt = None  # type: ignore[assignment]

WINDOWS = os.name == "nt"

# ---------- bootstrap: pasang dependency sendiri ----------
# Ubuntu 23.04+ (termasuk 26.04) menolak `pip install` ke Python sistem (PEP 668:
# "externally-managed-environment"). Jadi script ini memasang library-nya sendiri ke
# virtualenv khusus di ~/.local/share/claude-code-mini/venv lalu menjalankan ulang dirinya di sana.
# (Windows juga di %USERPROFILE%\.local\share, bukan %LOCALAPPDATA%: Python dari Microsoft Store
#  mengalihkan tulisan ke AppData ke folder pribadinya, sehingga venv-nya tidak ditemukan dari luar.)
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "claude-code-mini"
VENV_DIR = DATA_DIR / "venv"
VENV_PY = VENV_DIR / ("Scripts/python.exe" if WINDOWS else "bin/python")
BIN_DIR = Path.home() / ".local" / "bin"
# Windows: launcher .exe (dibuat pip), bukan .cmd: Ctrl+C di file .cmd memunculkan "Terminate batch job (Y/N)?".
LAUNCHER = BIN_DIR / ("claude-code-mini.exe" if WINDOWS else "claude-code-mini")
PY_CMD = "py" if WINDOWS else "python3"  # cara memanggil Python di petunjuk yang dicetak
REQUIREMENTS = ["claude-agent-sdk>=0.2.178", "rich>=13", "prompt_toolkit>=3.0.40",
                "gnureadline; sys_platform == 'darwin'"]
# Dipakai untuk cek apakah venv claude-code-mini sudah lengkap & cukup baru.
DEPS_CHECK = ("import rich.console, prompt_toolkit; "
              "from claude_agent_sdk import PermissionUpdate, list_sessions, TaskStartedMessage")


def quote_arg(s: str) -> str:
    """Kutip argumen supaya perintah yang dicetak bisa langsung disalin (PowerShell/cmd di Windows, sh selain itu)."""
    if WINDOWS:
        return f'"{s}"' if not s or any(c in s for c in " \t&()[]{}^=;!'+,`~$%@#") else s
    return shlex.quote(s)


_VT_ON = False  # Windows: escape sequence ANSI (warna, kursor) sudah diaktifkan di console


def enable_windows_vt() -> None:
    """Windows: aktifkan pemrosesan escape sequence ANSI di console (warna rich, spinner, output yang dicetak di atas
    prompt). Python tidak mengaktifkannya sendiri; tanpa ini kode warna tampil sebagai teks ←[32m. Dikembalikan
    seperti semula saat keluar."""
    global _VT_ON
    if not WINDOWS or _VT_ON:
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetStdHandle.restype = wintypes.HANDLE
        k32.GetStdHandle.argtypes = [wintypes.DWORD]
        k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        restore = []
        for std in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            h = k32.GetStdHandle(wintypes.DWORD(std & 0xFFFFFFFF))
            mode = wintypes.DWORD()
            if not h or not k32.GetConsoleMode(h, ctypes.byref(mode)):
                continue  # bukan console (diarahkan ke file / pipe)
            # ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            if k32.SetConsoleMode(h, mode.value | 0x0001 | 0x0004):
                _VT_ON = True
                restore.append((h, mode.value))
        if restore:
            atexit.register(lambda: [k32.SetConsoleMode(h, m) for h, m in restore])
    except Exception:
        pass


def is_terminal(stream: Any) -> bool:
    """isatty() yang juga benar di Windows: di sana perangkat NUL (`< NUL`, stdin kosong di CI) ikut dianggap
    terminal oleh isatty(), jadi dicek lagi apakah benar-benar console (GetConsoleMode berhasil)."""
    try:
        if not stream.isatty():
            return False
    except (AttributeError, ValueError, OSError):
        return False
    if not WINDOWS or msvcrt is None:
        return True
    try:
        import ctypes
        from ctypes import wintypes

        handle = msvcrt.get_osfhandle(stream.fileno())
        mode = wintypes.DWORD()
        return bool(ctypes.windll.kernel32.GetConsoleMode(wintypes.HANDLE(handle), ctypes.byref(mode)))
    except Exception:
        return False


def setup_windows_console() -> None:
    """Windows: warna & kursor ANSI aktif di console, dan output yang diarahkan ke file / pipe memakai UTF-8
    (bawaannya cp1252, yang gagal menulis → ✓ / emoji). Hanya library bawaan: dipanggil juga oleh --setup."""
    if not WINDOWS:
        return
    enable_windows_vt()
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            if is_terminal(stream):
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")


def win_user_env(name: str) -> str:
    """Windows: environment variable milik user yang tersimpan permanen (registry HKCU\\Environment)."""
    if not WINDOWS:
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, name)[0] or "")
    except OSError:
        return ""


def same_dir(a: str, b: Path) -> bool:
    a = os.path.expandvars(a.strip().strip('"'))
    return bool(a) and os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(str(b)))


def path_hint() -> str:
    """Perintah (sekali saja) supaya ~/.local/bin ada di PATH."""
    if WINDOWS:
        return ('$p = [Environment]::GetEnvironmentVariable("Path", "User"); '
                '[Environment]::SetEnvironmentVariable("Path", "$p;$HOME\\.local\\bin", "User"); '
                '$env:Path += ";$HOME\\.local\\bin"')
    rc = shell_rc()
    return f"echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> {rc} && source {rc}"


def key_hint() -> str:
    """Perintah untuk menyimpan ANTHROPIC_API_KEY secara permanen tanpa menampilkan key-nya di layar."""
    if WINDOWS:  # Read-Host -AsSecureString: tidak tampil di layar dan tidak masuk riwayat PowerShell
        return ('$s = Read-Host "API key" -AsSecureString; $k = [Net.NetworkCredential]::new("", $s).Password; '
                '[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", $k, "User"); '
                '$env:ANTHROPIC_API_KEY = $k; Remove-Variable s, k')
    rc = shell_rc()
    return f"{read_secret_cmd()}; echo; echo \"export ANTHROPIC_API_KEY=\\\"$K\\\"\" >> {rc}; unset K; source {rc}"


def shell_rc() -> str:
    """File konfigurasi shell user: ~/.zshrc (macOS default), ~/.bash_profile (bash di macOS), ~/.bashrc."""
    shell = os.path.basename(os.environ.get("SHELL", ""))
    if shell == "zsh":
        return "~/.zshrc"
    if shell == "bash" and sys.platform == "darwin":
        return "~/.bash_profile"
    return "~/.bashrc"


def read_secret_cmd() -> str:
    """Perintah shell untuk membaca API key ke variabel K tanpa menampilkannya (zsh & bash beda sintaks)."""
    if os.path.basename(os.environ.get("SHELL", "")) == "zsh":
        return 'read -rs "K?API key: "'
    return 'read -rsp "API key: " K'


def _deps_ok() -> bool:
    """True kalau rich + prompt_toolkit + claude-agent-sdk (versi yang cukup baru) bisa dipakai di Python ini."""
    import importlib

    try:
        con = importlib.import_module("rich.console")
        importlib.import_module("prompt_toolkit")
        sdk = importlib.import_module("claude_agent_sdk")
    except ImportError:  # belum terpasang (mis. cuma ada python3-rich dari apt)
        return False
    # Versi terlalu lama juga dianggap belum terpasang -> pakai venv sendiri.
    needed = ("PermissionUpdate", "list_sessions", "TaskStartedMessage", "TaskProgressMessage")
    return hasattr(con, "Console") and all(hasattr(sdk, n) for n in needed)


def _reexec_in_venv() -> None:
    os.environ["CCMINI_BOOTSTRAPPED"] = "1"
    sys.stdout.flush()
    argv = [str(VENV_PY), os.path.abspath(__file__), *sys.argv[1:]]
    if WINDOWS:
        # os.execv di Windows tidak mengganti proses ini (shell mengira programnya sudah selesai), jadi jalankan
        # sebagai proses anak dan tunggu. Ctrl+C diurus proses anak; di sini diabaikan supaya anaknya tidak ikut
        # dimatikan (subprocess.call membunuh proses anak kalau KeyboardInterrupt muncul saat menunggu).
        signal.signal(signal.SIGINT, lambda *_: None)
        sys.exit(subprocess.call(argv))
    os.execv(str(VENV_PY), argv)


def install_deps() -> bool:
    """Buat/perbarui virtualenv claude-code-mini dan pasang library yang dibutuhkan."""
    if VENV_PY.exists():
        # venv lama yang rusak / dibuat dengan Python < 3.10 (mis. /usr/bin/python3 macOS = 3.9) -> buat ulang
        ok = subprocess.run([str(VENV_PY), "-c", "import sys; sys.exit(sys.version_info < (3, 10))"],
                            capture_output=True).returncode == 0
        if not ok:
            import shutil

            print("→ Virtualenv lama tidak bisa dipakai (Python terlalu lama / rusak), dibuat ulang …", flush=True)
            shutil.rmtree(VENV_DIR, ignore_errors=True)
    if not VENV_PY.exists():
        print(f"→ Membuat virtualenv di {VENV_DIR} …", flush=True)
        r = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], capture_output=True, text=True)
        if r.returncode != 0 or not VENV_PY.exists():
            import shutil

            shutil.rmtree(VENV_DIR, ignore_errors=True)
            detail = (r.stdout + r.stderr).strip()
            if detail:
                print(detail[-600:])
            if WINDOWS:
                print("✗ Gagal membuat virtualenv. Pakai Python dari python.org atau:\n"
                      "    winget install -e --id Python.Python.3.13\nlalu jalankan script ini lagi dengan Python itu.")
            else:
                print("✗ Gagal membuat virtualenv. Di Ubuntu/Debian pasang dulu paket venv:\n"
                      "    sudo apt install -y python3-venv\nlalu jalankan script ini lagi.")
            return False
    print(f"→ Memasang {', '.join(REQUIREMENTS)} …", flush=True)
    r = subprocess.run([str(VENV_PY), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-U",
                        *REQUIREMENTS])
    if r.returncode != 0:
        print("✗ pip install gagal (lihat pesan di atas). Cek koneksi internet / proxy lalu coba lagi.")
        if WINDOWS:
            print("  Kalau pesannya 'Access is denied' / WinError 5 / 32: tutup dulu semua jendela claude-code-mini "
                  "yang masih jalan (file library-nya sedang dipakai), lalu ulangi.")
        return False
    return True


def _say(mark: str, text: str, color: str = "") -> None:
    """Satu baris output --setup. Sengaja tanpa rich (library belum tentu terpasang di Python ini)."""
    code = {"green": "32", "yellow": "33", "red": "31"}.get(color)
    if code and is_terminal(sys.stdout) and (_VT_ON or not WINDOWS):
        mark = f"\x1b[{code}m{mark}\x1b[0m"
    print(f"{mark} {text}", flush=True)


def build_windows_launcher(script: Path) -> Path:
    """Windows: buat claude-code-mini.exe lewat pip (launcher .exe standar, seperti pip.exe) dari paket kecil berisi
    satu entry point yang menjalankan `script`. Hasilnya di venv\\Scripts; setup() menyalinnya ke ~/.local/bin."""
    import hashlib
    import tempfile
    import zipfile

    name, ver = "ccmini_launch", "1.0"
    info = f"{name}-{ver}.dist-info"
    files = {
        f"{name}.py": ("import os, runpy, sys\n"
                       f"SCRIPT = {str(script)!r}\n\n\n"
                       "def main():\n"
                       "    os.environ['CCMINI_LAUNCHER'] = '1'\n"
                       "    sys.argv[0] = SCRIPT\n"
                       "    runpy.run_path(SCRIPT, run_name='__main__')\n"),
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: ccmini-launch\nVersion: {ver}\n"
                            "Summary: perintah claude-code-mini (dibuat oleh --setup)\n",
        f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: claude-code-mini\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{info}/entry_points.txt": "[console_scripts]\nclaude-code-mini = ccmini_launch:main\n",
    }
    record = []
    for path, text in files.items():
        data = text.encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        record.append(f"{path},sha256={digest},{len(data)}")
    files[f"{info}/RECORD"] = "\n".join(record + [f"{info}/RECORD,,"]) + "\n"
    with tempfile.TemporaryDirectory() as tmp:
        whl = Path(tmp) / f"{name}-{ver}-py3-none-any.whl"
        with zipfile.ZipFile(whl, "w", zipfile.ZIP_DEFLATED) as z:
            for path, text in files.items():
                z.writestr(path, text)
        r = subprocess.run([str(VENV_PY), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                            "--force-reinstall", "--no-deps", "--no-index", str(whl)], capture_output=True, text=True)
    exe = VENV_DIR / "Scripts" / "claude-code-mini.exe"
    if r.returncode != 0 or not exe.is_file():
        raise OSError((r.stdout + r.stderr).strip()[-500:] or f"{exe} tidak terbentuk")
    return exe


def replace_file(src: Path, dst: Path) -> None:
    """Salin src ke dst. Windows tidak bisa menimpa .exe yang sedang jalan (mis. saat `claude-code-mini --setup`),
    tapi bisa mengganti namanya: file lama disingkirkan dulu dan dihapus pada setup berikutnya."""
    for old in dst.parent.glob(dst.name + ".old*"):
        with contextlib.suppress(OSError):
            old.unlink()
    if dst.exists():
        try:
            dst.unlink()
        except OSError:
            dst.replace(dst.with_name(f"{dst.name}.old{os.getpid()}"))
    shutil.copy2(src, dst)


def git_bash() -> str | None:
    """Windows: bash.exe dari Git for Windows (dicari seperti Claude Code mencarinya)."""
    cands = [os.environ.get("CLAUDE_CODE_GIT_BASH_PATH", "")]
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", ""),
                 str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs")):
        if base:
            cands.append(str(Path(base) / "Git" / "bin" / "bash.exe"))
    git = shutil.which("git")
    if git:  # ...\Git\cmd\git.exe -> ...\Git\bin\bash.exe
        cands.append(str(Path(git).resolve().parent.parent / "bin" / "bash.exe"))
    return next((c for c in cands if c and Path(c).is_file()), None)


def windows_engine_notes() -> None:
    """Windows: cek mesin Claude Code (claude.exe) dan shell yang akan dipakai Claude untuk menjalankan command."""
    r = subprocess.run([str(VENV_PY), "-c", "import claude_agent_sdk, pathlib; print((pathlib.Path("
                        "claude_agent_sdk.__file__).parent / '_bundled' / 'claude.exe').is_file())"],
                       capture_output=True, text=True)
    native = shutil.which("claude.exe") or (BIN_DIR / "claude.exe").is_file()
    if r.stdout.strip() == "True":
        _say("✓", "Mesin Claude Code: claude.exe bawaan claude-agent-sdk", "green")
    elif native:
        _say("✓", "Mesin Claude Code: claude.exe yang terpasang di komputer ini", "green")
    else:
        _say("!", "Mesin Claude Code (claude.exe) tidak ikut terpasang: paket claude-agent-sdk untuk komputer ini "
                  "(mis. Windows ARM64) tidak membawanya. Pasang sekali di PowerShell:", "yellow")
        print("    irm https://claude.ai/install.ps1 | iex\n  atau pakai Python versi x64, lalu ulangi --setup.")
    bash = git_bash()
    if bash:
        _say("✓", f"Git Bash: {bash} (Claude menjalankan command lewat Bash)", "green")
    else:
        _say("!", "Git for Windows belum terpasang: Claude akan menjalankan command lewat PowerShell.\n"
                  "  Disarankan pasang Git (Claude Code paling lancar dengan Bash), lalu buka terminal baru:", "yellow")
        print("    winget install -e --id Git.Git")


def setup() -> None:
    """--setup: pasang/update library ke venv sendiri, salin script ke DATA_DIR, buat perintah `claude-code-mini`.
    Sengaja cuma memakai library bawaan Python dan dijalankan sebelum rich/claude-agent-sdk di-import: di Windows,
    file library yang sedang dipakai proses ini tidak bisa ditimpa pip."""
    setup_windows_console()
    if not install_deps():
        sys.exit(1)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    src, dst = Path(__file__).resolve(), DATA_DIR / "claude-code-mini.py"
    if src != dst:
        shutil.copy2(src, dst)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if WINDOWS:
            replace_file(build_windows_launcher(dst), LAUNCHER)
        else:
            LAUNCHER.write_text(f'#!/bin/sh\nexport CCMINI_LAUNCHER=1\nexec "{VENV_PY}" "{dst}" "$@"\n')
            LAUNCHER.chmod(0o755)
    except OSError as e:
        _say("✗", f"Gagal membuat perintah claude-code-mini: {e}", "red")
        print(f"  Tetap bisa dijalankan dengan: {quote_arg(str(VENV_PY))} {quote_arg(str(dst))} <folder-repo>")
        sys.exit(1)
    _say("✓", f"Library terpasang ({VENV_DIR})", "green")
    _say("✓", f"Perintah claude-code-mini dibuat ({LAUNCHER} → {dst})", "green")
    if WINDOWS:
        windows_engine_notes()
    paths = os.environ.get("PATH", "").split(os.pathsep)
    if not any(same_dir(p, BIN_DIR) for p in paths):
        if WINDOWS and any(same_dir(p, BIN_DIR) for p in win_user_env("Path").split(";")):
            _say("!", f"{BIN_DIR} sudah ada di PATH user, tapi belum terbaca di terminal ini: buka terminal baru.",
                 "yellow")
        elif WINDOWS:
            _say("!", f"{BIN_DIR} belum ada di PATH. Jalankan ini di PowerShell (sekali saja):", "yellow")
            print(f"    {path_hint()}")
        else:
            _say("!", "~/.local/bin belum ada di PATH. Jalankan ini (sekali saja):", "yellow")
            print(f"    {path_hint()}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        if WINDOWS and win_user_env("ANTHROPIC_API_KEY"):
            _say("!", "ANTHROPIC_API_KEY sudah tersimpan, tapi belum terbaca di terminal ini: buka terminal baru.",
                 "yellow")
        elif WINDOWS:
            _say("!", "ANTHROPIC_API_KEY belum di-set. Simpan lewat PowerShell (key tidak tampil di layar):", "yellow")
            print(f"    {key_hint()}")
        else:
            _say("!", f"ANTHROPIC_API_KEY belum di-set. Tambahkan ke {shell_rc()} (key tidak tampil di layar):",
                 "yellow")
            print(f"    {key_hint()}")
    example = r"C:\path\ke\repo" if WINDOWS else "/path/ke/repo"
    if src != dst:
        print(f"\nCoba: claude-code-mini {example}\n"
              f"Versi baru (setelah git pull / edit {src.name}) dipasang dengan: {PY_CMD} {quote_arg(str(src))} --setup")
    else:
        print(f"\nCoba: claude-code-mini {example}  ·  library sudah diperbarui")


def bootstrap() -> None:
    setup_windows_console()
    if sys.version_info < (3, 10):
        sys.exit(f"✗ Butuh Python 3.10 atau lebih baru (sekarang {sys.version.split()[0]}).")
    if "--setup" in sys.argv[1:]:  # dikerjakan sebelum library berat di-import (lihat setup())
        setup()
        sys.exit(0)
    if _deps_ok():
        return
    reqs = " ".join(quote_arg(r) for r in REQUIREMENTS)
    if os.environ.get("CCMINI_BOOTSTRAPPED"):
        sys.exit(f"✗ Library masih belum bisa di-import setelah instalasi.\n"
                 f"  Coba manual: {quote_arg(str(VENV_PY))} -m pip install -U {reqs}")
    if VENV_PY.exists() and Path(sys.prefix).resolve() != VENV_DIR.resolve():
        check = subprocess.run([str(VENV_PY), "-c", DEPS_CHECK], capture_output=True)
        if check.returncode == 0:
            _reexec_in_venv()  # sudah terpasang sebelumnya -> langsung pakai
    print("Library yang dibutuhkan (claude-agent-sdk, rich, prompt_toolkit) belum terpasang / perlu diperbarui.",
          flush=True)
    if not is_terminal(sys.stdin):
        sys.exit(f"Jalankan sekali: {PY_CMD} {quote_arg(sys.argv[0])} --setup\n"
                 f"atau pasang manual: {PY_CMD} -m venv {quote_arg(str(VENV_DIR))} && "
                 f"{quote_arg(str(VENV_PY))} -m pip install -U {reqs}")
    try:
        ans = input(f"Pasang otomatis ke {VENV_DIR}? (tidak butuh {'admin' if WINDOWS else 'sudo'}) [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        sys.exit(1)
    if ans not in ("", "y", "ya", "yes"):
        sys.exit("Dibatalkan.")
    if not install_deps():
        sys.exit(1)
    _reexec_in_venv()


if __name__ == "__main__":
    bootstrap()

try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.markup import escape as rich_escape
    from rich.padding import Padding
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.text import Text
except ImportError:
    sys.exit(f"Library 'rich' belum terpasang. Jalankan: {PY_CMD} claude-code-mini.py --setup")

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.application import in_terminal, run_in_terminal
    from prompt_toolkit.application.current import get_app, set_app
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style
except ImportError:
    sys.exit(f"Library 'prompt_toolkit' belum terpasang. Jalankan: {PY_CMD} claude-code-mini.py --setup")

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ClaudeSDKError,
        CLINotFoundError,
        PermissionResultAllow,
        PermissionResultDeny,
        PermissionUpdate,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ThinkingBlock,
        ToolPermissionContext,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
    )
except ImportError:
    sys.exit(f"Library 'claude-agent-sdk' belum terpasang / terlalu lama. Jalankan: {PY_CMD} claude-code-mini.py --setup")

# Fitur dari SDK versi baru. Kalau SDK-nya lama, fitur ini dimatikan tanpa bikin crash.
try:
    from claude_agent_sdk import get_session_messages, list_sessions
except ImportError:
    get_session_messages = list_sessions = None  # type: ignore[assignment]
try:
    from claude_agent_sdk import ConversationResetMessage, RateLimitEvent
except ImportError:  # isinstance(x, ()) selalu False
    ConversationResetMessage = RateLimitEvent = ()  # type: ignore[assignment,misc]
try:  # event tugas background (agent / command / monitor)
    from claude_agent_sdk import (
        TaskNotificationMessage,
        TaskProgressMessage,
        TaskStartedMessage,
        TaskUpdatedMessage,
    )
except ImportError:
    TaskNotificationMessage = TaskProgressMessage = TaskStartedMessage = TaskUpdatedMessage = ()  # type: ignore[assignment,misc]
TASK_EVENTS = tuple(c for c in (TaskStartedMessage, TaskProgressMessage, TaskUpdatedMessage, TaskNotificationMessage)
                    if isinstance(c, type))


def isolate_cli_from_ctrl_c() -> None:
    """Ctrl+C di terminal dikirim ke SELURUH process group - termasuk mesin Claude Code (proses anak),
    yang lalu mematikan semua tugas background-nya dan keluar. Jalankan mesin itu di session sendiri,
    jadi Ctrl+C cuma diterima script ini, yang meneruskannya sebagai 'interrupt' biasa.
    Windows: Ctrl+C dikirim ke semua proses di console yang sama; proses di process group baru tidak menerimanya."""
    try:
        import anyio
    except ImportError:
        return
    orig = getattr(anyio, "open_process", None)
    if orig is None or getattr(orig, "_ccmini", False):
        return

    async def open_process(*args: Any, **kwargs: Any) -> Any:
        if WINDOWS:
            kwargs["creationflags"] = (kwargs.get("creationflags") or 0) | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs.setdefault("start_new_session", True)
        return await orig(*args, **kwargs)

    open_process._ccmini = True  # type: ignore[attr-defined]
    anyio.open_process = open_process


isolate_cli_from_ctrl_c()


setup_windows_console()
console = Console(highlight=False)

# Log internal SDK disembunyikan; error-nya ditampilkan sendiri dengan pesan yang lebih jelas.
logging.getLogger("claude_agent_sdk").setLevel(logging.CRITICAL)
# Sengaja: tool baca-saja (AUTO_TOOLS) memang tidak perlu lewat can_use_tool.
warnings.filterwarnings("ignore", message="can_use_tool will not be invoked")

# Pesan stderr CLI yang cuma bikin berisik (bukan error).
STDERR_NOISE = ("claude.ai connectors are disabled",)


def on_cli_stderr(line: str) -> None:
    line = line.rstrip()
    if line and not any(n in line for n in STDERR_NOISE):
        console.print(Text(line, style="dim"))

DEFAULT_MODEL = "claude-opus-5-5"
MODEL_ALIASES = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
    "fable": "claude-fable-5-1",
}
# Batas ukuran satu pesan dari mesin Claude ke script. Bawaan SDK cuma 1 MB, jadi output
# tool yang besar (file panjang, log, gambar) bikin error "exceeded maximum buffer size".
DEFAULT_BUFFER_MB = 64
MAX_RECOVERY = 3  # berapa kali boleh auto-recovery berturut-turut sebelum menyerah
MODES = ["default", "acceptEdits", "plan", "auto", "bypassPermissions", "dontAsk"]
MODE_CYCLE = ["default", "acceptEdits", "plan"]  # urutan Shift+Tab, sama seperti Claude Code
MODE_LABEL = {
    "default": "? tanya dulu sebelum edit & command",
    "acceptEdits": "⏵⏵ auto-terima edit",
    "plan": "⏸ plan mode",
    "auto": "⏵ auto mode",
    "bypassPermissions": "⚠ YOLO: tanpa izin",
    "dontAsk": "dontAsk",
}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]

# Tool yang aman (cuma baca / catatan) -> langsung jalan tanpa tanya.
# Edit file otomatis diizinkan oleh mode "acceptEdits". Sisanya (Bash, dll) ditanya dulu.
AUTO_TOOLS = ["Read", "Glob", "Grep", "TodoWrite", "WebSearch", "WebFetch"]

# Tool ini butuh UI tanya-jawab khusus yang tidak ada di script ini.
BLOCKED_TOOLS = ["AskUserQuestion"]

# Riwayat prompt (format prompt_toolkit). Riwayat lama dari versi readline dipindahkan sekali.
HISTORY_FILE = Path.home() / ".claude-code-mini_history"
# Riwayat dari versi lama script ini (dulu bernama "ngoding") ikut dipindahkan sekali.
LEGACY_HISTORY_FILE = Path.home() / ".ngoding_history_v2"  # sudah format prompt_toolkit -> cukup disalin
OLD_HISTORY_FILES = (Path.home() / ".ngoding_history", Path.home() / ".ngoding_history_libedit")  # format readline
MAX_MENTION_BYTES = 200_000  # batas isi satu file yang dilampirkan lewat @mention
MAX_SHELL_CONTEXT = 30_000  # batas output "!command" yang dikirim ke Claude
SPINNER_VERBS = ["Berpikir", "Mengulik", "Meracik", "Menimbang", "Ngoding", "Merenung", "Menelusuri", "Menyusun"]
TOOL_LABEL = {"TodoWrite": "Update Todos", "Edit": "Update", "MultiEdit": "Update"}
MAX_TASK_LINES = 4  # baris tugas background yang tampil live di bawah prompt / spinner
TERMINAL_STATUSES = {"completed", "failed", "stopped", "killed"}
PROMPT_TEXT = "\x1b[1;36m› \x1b[0m"
PT_STYLE = Style.from_dict({"bottom-toolbar": "noreverse"})

LOCAL_COMMANDS = {
    "/help": "tampilkan bantuan ini",
    "/status": "info sesi: model, mode, folder, session id",
    "/cost": "total biaya sesi ini",
    "/context": "pemakaian context window",
    "/model": "ganti model: opus, sonnet, haiku, fable, atau id lengkap",
    "/mode": "ganti mode izin (atau tekan Shift+Tab)",
    "/allow": "lihat tool yang diizinkan ( /allow reset = hapus izin sesi )",
    "/tasks": "pantau agent/command background ( /tasks 2 = detail & log, /tasks log = on/off log )",
    "/stop": "hentikan tugas background ( /stop 2, /stop all )",
    "/goal": "kerja terus sampai kondisi terpenuhi (/goal = status, clear = batal)",
    "/resume": "lanjutkan percakapan lama di folder ini",
    "/rewind": "kembalikan file ke kondisi sebelum prompt tertentu",
    "/clear": "mulai percakapan baru (konteks lama dibuang)",
    "/exit": "keluar",
}

SHORTCUTS_TEXT = """\
[bold]Shortcut:[/]
  [cyan]![/][dim]command[/]        jalankan command shell langsung (output masuk konteks Claude)
  [cyan]@[/][dim]path[/]           lampirkan file/folder ke pesan (Tab untuk melengkapi)
  [cyan]#[/][dim] catatan[/]       simpan catatan ke CLAUDE.md (memori proyek)
  [cyan]Tab[/]             lengkapi /perintah dan @path
  [cyan]Shift+Tab[/]       ganti mode izin: default → acceptEdits → plan
  [cyan]Esc[/] / [cyan]Ctrl+C[/]    hentikan Claude saat sedang bekerja (juga saat menanggapi tugas background)
  [cyan]Ctrl+C 2x[/] / [cyan]Ctrl+D[/]  keluar
  akhiri baris dengan [cyan]\\\\[/] atau [cyan]Alt+Enter[/]  pesan multi-baris (paste multi-baris otomatis jadi satu pesan)
[bold]Saat Claude bekerja:[/] kolom chat tetap bisa dipakai.
  [cyan]Enter[/]  pesan langsung dikirim; Claude membacanya begitu langkah (tool) yang sedang jalan selesai
  /perintah, !command, # catatan  antre sampai giliran selesai ([cyan]↑[/] di kolom kosong = ambil kembali)
  /tasks /help /status /cost /stop /mode  langsung dijalankan
[bold]Tugas background:[/] progres agent/command background tampil live di bawah prompt.
  [cyan]/tasks[/] daftar & progres · [cyan]/tasks 2[/] detail, log & output · [cyan]/stop 2[/] hentikan
[bold]Goal:[/] [cyan]/goal[/] [dim]kondisi[/]   Claude kerja terus sampai pemeriksa menilai kondisinya terpenuhi · [cyan]/goal[/] status · [cyan]/goal clear[/] batal
  tulis kondisi yang bisa dibuktikan dari output Claude (mis. "`pytest` exit 0 dan `git status` bersih") dan batasi,
  mis. "atau berhenti setelah 20 giliran" · Esc = jeda (goal tetap aktif, kirim pesan untuk lanjut) · tiap cek = 1
  panggilan API kecil · command yang belum diizinkan tetap ditanya: jawab 2 (jangan tanya lagi) atau pakai --yolo
"""

if WINDOWS:  # Alt+Enter dipakai Windows Terminal untuk layar penuh: tawarkan \ saja
    SHORTCUTS_TEXT = SHORTCUTS_TEXT.replace(" atau [cyan]Alt+Enter[/]", "")

# Kata yang diterima Claude Code untuk membatalkan goal (+ padanan Indonesia yang kita ubah ke "clear").
GOAL_CLEAR_WORDS = {"clear", "stop", "off", "reset", "none", "cancel"}
GOAL_CLEAR_ALIASES = {"batal", "hapus"}

# Perintah lokal yang aman dijalankan saat Claude sedang bekerja (cuma membaca status / tidak menyentuh percakapan).
IMMEDIATE_COMMANDS = {"/help", "/tasks", "/status", "/cost", "/allow", "/stop", "/mode"}
DRAIN = object()  # hasil khusus prompt: ditutup sementara untuk memproses antrean (bukan ketikan user)
BUSY_HINT = "ketik pesan susulan… Enter = kirim (dibaca Claude setelah langkah ini) · Esc = hentikan"


class WrongAuthSource(Exception):
    """Dilempar kalau ternyata yang dipakai bukan ANTHROPIC_API_KEY (mis. login subscription)."""


class StartFailed(Exception):
    """Mesin Claude Code gagal start (crash, timeout, dll)."""


def clip(s: str, width: int = 200) -> str:
    s = s.replace("\t", "    ")
    return s if len(s) <= width else s[: width - 1] + "…"


def oneline(s: str) -> str:
    return " ".join(s.split())


def ago(ts: Any) -> str:
    """Ubah timestamp (epoch detik/milidetik, ISO string, datetime) jadi '5 menit lalu'."""
    try:
        if isinstance(ts, datetime):
            t = ts.timestamp()
        elif isinstance(ts, (int, float)):
            t = ts / 1000 if ts > 1e11 else float(ts)
        elif isinstance(ts, str):
            t = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        else:
            return ""
    except (ValueError, OSError, OverflowError):
        return ""
    d = max(time.time() - t, 0)
    if d < 60:
        return "baru saja"
    if d < 3600:
        return f"{int(d // 60)} menit lalu"
    if d < 86400:
        return f"{int(d // 3600)} jam lalu"
    return f"{int(d // 86400)} hari lalu"


def fmt_tokens(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def fmt_dur(sec: float) -> str:
    sec = int(max(sec, 0))
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60:02d}s"
    return f"{sec // 3600}j {sec % 3600 // 60:02d}m"


def is_ours(origin: Any) -> bool:
    """True kalau pesan/hasil berasal dari prompt yang kita kirim (bukan giliran otomatis dari CLI)."""
    return origin is None or (isinstance(origin, dict) and origin.get("kind") == "human")


# ---------- goal (/goal): kerja terus sampai kondisi terpenuhi ----------
# Dikerjakan oleh Claude Code sendiri (Stop hook berbasis prompt: tiap kali Claude mau berhenti,
# model kecil menilai kondisinya). Script ini cuma menerjemahkan jawabannya dan memantau statusnya.
@dataclass
class Goal:
    condition: str
    set_at: float = field(default_factory=time.monotonic)
    cost_at_set: float = 0.0
    checks: int = 0  # penolakan pemeriksa yang terlihat di layar (hitungan lokal)
    cli_turns: int | None = None  # "(N turns)" menurut Claude Code (reset saat --resume), dipisah
    last_reason: str = ""
    paused: bool = False
    pause_cause: str = ""  # "cap" | "dihentikan user" | "error" | "pemeriksa tidak menilai"
    ended_at: float = 0.0  # epoch, diisi saat goal berakhir
    ended_mono: float = 0.0
    cost_at_end: float = 0.0

    def end(self, cost_now: float) -> None:
        self.ended_at, self.ended_mono, self.cost_at_end = time.time(), time.monotonic(), cost_now

    def stats(self, cost_now: float) -> str:
        end = self.ended_mono or time.monotonic()
        cost = (self.cost_at_end if self.ended_mono else cost_now) - self.cost_at_set
        return f"{self.checks} cek · {fmt_dur(end - self.set_at)} · biaya ${max(cost, 0.0):.4f}"


def same_goal(a: str, b: str) -> bool:
    """Dua teks kondisi dianggap goal yang sama (Claude Code memotong kondisi panjang jadi 500 karakter + '…')."""
    a, b = oneline(a).rstrip("…").strip(), oneline(b).rstrip("…").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 40 and long_.startswith(short)


def parse_goal_active(text: str) -> tuple[str, int | None, str]:
    """'Goal active: <kondisi> (N turns|not yet evaluated)\\nLast check: <alasan>' -> (kondisi, N, alasan)."""
    body = text[len("Goal active:"):].strip()
    head, _, reason = body.partition("\nLast check: ")
    cond, turns = head.strip(), None
    left, sep, tail = head.rstrip().rpartition(" (")
    if sep:
        m = re.fullmatch(r"(\d+) turns?\)", tail)
        if m:
            cond, turns = left.strip(), int(m.group(1))
        elif tail == "not yet evaluated)":
            cond = left.strip()
    return cond, turns, reason.strip()


def tail_lines(path: str, n: int = 15, max_bytes: int = 16384) -> list[str]:
    """Baris-baris terakhir dari file output tugas background (tanpa membaca seluruh file)."""
    if not path:
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(size - max_bytes, 0))
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = [ln.rstrip() for ln in data.replace("\r", "\n").splitlines()]
    if size > max_bytes and lines:
        lines = lines[1:]  # baris pertama mungkin terpotong
    lines = [ln for ln in lines if ln.strip()]
    return lines[-n:]


def agent_report(path: str) -> str:
    """Teks jawaban terakhir sebuah agent, dibaca dari transkripnya (output_file agent = transkrip JSONL)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(f.tell() - 262144, 0))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        msg = d.get("message") if isinstance(d, dict) and d.get("type") == "assistant" else None
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
            if text.strip():
                return text.strip()
    return ""


_ANSI_CONSOLES: dict[int, Console] = {}


def to_ansi(renderable: Any, width: int) -> str:
    """Render objek rich jadi string ANSI (untuk toolbar prompt_toolkit)."""
    c = _ANSI_CONSOLES.get(width)
    if c is None:
        c = _ANSI_CONSOLES[width] = Console(file=io.StringIO(), force_terminal=True, width=width, highlight=False,
                                            color_system=console.color_system or "standard")
    c.file = io.StringIO()
    c.print(renderable, end="")
    return c.file.getvalue()


def write_raw(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def migrate_history() -> None:
    """Pindahkan riwayat input dari versi lama (ngoding / readline / libedit), sekali saja."""
    if HISTORY_FILE.exists():
        return
    if LEGACY_HISTORY_FILE.exists():
        try:
            shutil.copyfile(LEGACY_HISTORY_FILE, HISTORY_FILE)
            return
        except OSError:
            pass
    entries: list[str] = []
    for f in OLD_HISTORY_FILES:
        try:
            lines = f.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if line.startswith("_HiStOrY_V2_"):
                continue
            if f.name.endswith("libedit"):  # libedit menyimpan spasi sebagai \040
                line = re.sub(r"\\(\d{3})", lambda m: chr(int(m.group(1), 8)), line)
            if line.strip():
                entries.append(line)
    try:
        with HISTORY_FILE.open("w", encoding="utf-8") as out:
            for e in entries[-1000:]:
                out.write(f"\n# riwayat lama\n+{e}\n")
    except OSError:
        pass


# ---------- tugas background (agent / command / monitor) ----------
TASK_KIND = {"local_agent": "agent", "local_bash": "bash", "monitor": "monitor", "local_workflow": "workflow"}
KIND_LABEL = {"agent": "Agent", "bash": "Command", "monitor": "Monitor", "workflow": "Workflow"}
STATUS_VIEW = {  # status -> (ikon, warna, kata)
    "running": ("⧗", "yellow", "berjalan"),
    "completed": ("✓", "green", "selesai"),
    "failed": ("✗", "red", "gagal"),
    "stopped": ("⏹", "yellow", "dihentikan"),
}


@dataclass
class BgTask:
    id: str
    num: int
    kind: str  # agent / bash / monitor / ...
    desc: str
    agent_type: str = ""
    tool_use_id: str | None = None
    background: bool = False  # False = sub-agent biasa yang ditunggu Claude (foreground)
    detached: bool = False  # benar-benar dijalankan di background oleh CLI (bukan cuma anak dari agent background)
    parent: str | None = None
    prompt: str = ""
    status: str = "running"
    started: float = field(default_factory=time.monotonic)
    ended: float | None = None
    tokens: int = 0
    tool_uses: int = 0
    last_tool: str = ""
    activity: str = ""  # aktivitas terakhir, mis. "Bash(npm test)"
    output_file: str = ""
    summary: str = ""
    announced: bool = False
    log: deque = field(default_factory=lambda: deque(maxlen=60))

    @property
    def label(self) -> str:
        return KIND_LABEL.get(self.kind, "Tugas")

    def elapsed(self) -> float:
        return (self.ended or time.monotonic()) - self.started

    def note(self, entry: str) -> None:
        self.log.append((time.time(), entry))

    def finish(self, status: str) -> None:
        if self.status == "running":
            self.status = "stopped" if status == "killed" else status
            self.ended = time.monotonic()

    def stats(self) -> list[str]:
        bits = [fmt_dur(self.elapsed())]
        if self.tool_uses:
            bits.append(f"{self.tool_uses} tool")
        if self.tokens:
            bits.append(f"{fmt_tokens(self.tokens)} token")
        return bits

    def latest(self) -> str:
        """Satu baris 'sedang apa': baris output terakhir (command) atau aktivitas terakhir (agent)."""
        if self.kind != "agent" and self.output_file:
            out = tail_lines(self.output_file, 1, 4096)
            if out:
                return "⎿ " + out[-1].strip()
        return self.activity or (f"{self.last_tool}…" if self.last_tool else "")


CANCEL = "\x03"  # jawaban ask() kalau user menekan Ctrl+C / Ctrl+D (BUKAN "Enter = ya")


def shell_command(cmd: str) -> list[str]:
    """argv untuk '!command'. Windows: PowerShell (pwsh kalau ada, kalau tidak Windows PowerShell bawaan) dengan
    output UTF-8; script dikirim sebagai -EncodedCommand supaya tanda kutip di dalamnya tidak rusak.
    Selain Windows: $SHELL -c."""
    if WINDOWS:
        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        script = ("[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
                  "$OutputEncoding = [Console]::OutputEncoding\n" + cmd)
        encoded = base64.b64encode(script.encode("utf-16-le")).decode()
        return [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    return [os.environ.get("SHELL") or "/bin/sh", "-c", cmd]


def ask(question: str) -> str:
    """Pertanyaan singkat (izin, pilihan nomor). Jawabannya tidak masuk riwayat input."""
    if readline:
        readline.set_auto_history(False)
    try:
        console.print(question, end="")
        return input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return CANCEL
    finally:
        if readline:
            readline.set_auto_history(True)


# ---------- tombol Esc saat Claude bekerja ----------
class KeyWatcher:
    """Selama Claude bekerja tanpa prompt aktif (mode -p, cek goal saat start), tombol Esc ditangkap di sini.
    POSIX: terminal dipasang ke mode cbreak. Windows: console dibaca lewat msvcrt tiap 50 ms.

    Ketikan lain selama Claude bekerja ditampung (type-ahead) dan otomatis
    diisikan ke prompt berikutnya, mirip Claude Code.
    """

    def __init__(self) -> None:
        self.fd: int | None = None
        self.saved: list[Any] | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.on_esc: Any = None
        self.active = False
        self.typed = ""
        self.timer: asyncio.TimerHandle | None = None  # Windows: jadwal baca console berikutnya
        atexit.register(self.stop)

    def start(self, loop: asyncio.AbstractEventLoop, on_esc: Any) -> None:
        if not is_terminal(sys.stdin):
            return
        if termios is None:  # Windows
            if msvcrt is not None:
                self.loop, self.on_esc, self.saved = loop, on_esc, []
                self.resume()
            return
        self.loop, self.on_esc = loop, on_esc
        self.fd = sys.stdin.fileno()
        try:
            self.saved = termios.tcgetattr(self.fd)
        except termios.error:
            self.saved = None
            return
        self.resume()

    def _feed(self, ch: str) -> None:
        if ch in ("\x7f", "\b"):
            self.typed = self.typed[:-1]
        elif ch == "\x15":  # Ctrl+U
            self.typed = ""
        elif ch in ("\r", "\n"):
            self.typed += " " if self.typed and not self.typed.endswith(" ") else ""
        elif ch.isprintable():
            self.typed += ch

    def _read(self) -> None:
        try:
            data = os.read(self.fd, 256)  # type: ignore[arg-type]
        except OSError:
            return
        if data == b"\x1b":
            # Lewat SSH, tombol panah (\x1b[A) bisa datang terpecah. Tunggu sebentar:
            # kalau ada lanjutan berarti escape sequence, bukan tombol Esc.
            try:
                more = select.select([self.fd], [], [], 0.06)[0]
            except (ValueError, OSError):
                more = []
            if not more:
                self.on_esc()
                return
            try:
                data += os.read(self.fd, 256)  # type: ignore[arg-type]
            except OSError:
                return
        if data.startswith(b"\x1b"):
            return
        for ch in data.decode("utf-8", "ignore"):
            self._feed(ch)

    def _poll_windows(self) -> None:
        self.timer = None
        try:
            while msvcrt.kbhit():  # type: ignore[union-attr]
                ch = msvcrt.getwch()  # type: ignore[union-attr]
                if ch in ("\x00", "\xe0"):  # tombol khusus (panah, F1, …): kode keduanya dibuang
                    msvcrt.getwch()  # type: ignore[union-attr]
                elif ch == "\x1b":
                    self.on_esc()
                else:
                    self._feed(ch)
        except OSError:
            pass
        if self.active and self.loop is not None:
            self.timer = self.loop.call_later(0.05, self._poll_windows)

    def pause(self) -> None:
        """Kembalikan terminal ke mode normal (mis. untuk menanyakan izin)."""
        if not self.active:
            return
        self.active = False
        if termios is None:  # Windows
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None
            return
        try:
            self.loop.remove_reader(self.fd)  # type: ignore[union-attr,arg-type]
        except (ValueError, RuntimeError):
            pass
        try:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)  # type: ignore[union-attr,arg-type]
        except termios.error:  # type: ignore[union-attr]
            pass

    def resume(self) -> None:
        if self.active or self.saved is None or self.loop is None:
            return
        if termios is None:  # Windows
            self.active = True
            self.timer = self.loop.call_later(0.05, self._poll_windows)
            return
        try:
            tty.setcbreak(self.fd)  # type: ignore[union-attr]
            self.loop.add_reader(self.fd, self._read)  # type: ignore[arg-type]
            self.active = True
        except (termios.error, ValueError, RuntimeError):  # type: ignore[union-attr]
            pass

    def stop(self) -> None:
        self.pause()
        self.saved = None
        self.loop = None

    def take_typeahead(self) -> str:
        text, self.typed = self.typed.strip(), ""
        return text


# ---------- input prompt (prompt_toolkit: riwayat, completion, Shift+Tab, paste, status live) ----------
class Completions(Completer):
    """/perintah di awal baris dan @path di mana saja (muncul saat mengetik, Tab untuk memilih)."""

    def __init__(self, prompt: "PromptInput"):
        self.prompt = prompt

    def get_completions(self, document: Any, complete_event: Any) -> Any:
        before = document.text_before_cursor
        word = re.search(r"\S*$", before).group(0)  # type: ignore[union-attr]
        if word.startswith("/") and before.lstrip() == word:
            for c in sorted(self.prompt.commands):
                if c.startswith(word):
                    yield Completion(c + " ", start_position=-len(word), display=c,
                                     display_meta=clip(self.prompt.commands.get(c) or "", 70))
        elif word.startswith("@"):
            try:
                matches = self.prompt.path_matches(word)
            except OSError:
                return
            for m in matches:
                yield Completion(m, start_position=-len(word), display=m.rstrip())


class PromptInput:
    """Prompt utama. Prompt ini tetap aktif saat Claude bekerja (seperti Claude Code): pesan dari mesin
    Claude (output tool, progres agent background, dll) dicetak DI ATAS prompt tanpa merusak ketikan,
    status kerja + tugas background tampil live di toolbar bawah, dan Enter saat Claude bekerja langsung
    mengirim pesan susulan / mengantrekan perintah (lihat UI.submit_while_busy)."""

    def __init__(self, ui: "UI"):
        self.ui = ui
        self.repo = ui.repo
        self.commands: dict[str, str] = dict(LOCAL_COMMANDS)
        self.session: PromptSession | None = None
        self.interactive = is_terminal(sys.stdin) and is_terminal(sys.stdout)
        self.queue: deque[str] = deque()  # ketikan saat Claude bekerja yang menunggu giliran selesai (/perintah, !command, …)
        self.draft = ""  # ketikan yang belum dikirim saat prompt ditutup sementara (drain), dikembalikan ke prompt berikutnya
        self.ticker: asyncio.Task | None = None  # gambar ulang toolbar (spinner) saat Claude bekerja
        self.gap = False  # cetak baris kosong sebelum prompt (tidak untuk prompt pertama, header sudah berjarak)

    def path_matches(self, text: str) -> list[str]:
        frag = text[1:]
        base = Path(frag).expanduser() if frag.startswith(("/", "~")) else self.repo / frag
        ends_sep = frag.endswith(("/", "\\") if WINDOWS else "/")  # Windows: @src\ juga berarti "isi folder src"
        folder, prefix = (base, "") if ends_sep or not frag else (base.parent, base.name)
        out = []
        for p in sorted(folder.iterdir()):
            if not p.name.startswith(prefix) or p.name in (".git", "node_modules", "__pycache__"):
                continue
            if p.name.startswith(".") and not prefix.startswith("."):
                continue
            shown = frag[: len(frag) - len(prefix)] + p.name
            out.append("@" + shown + ("/" if p.is_dir() else " "))
            if len(out) >= 200:
                break
        return out

    def active(self) -> bool:
        return self.session is not None and self.session.app.is_running

    def _build(self) -> PromptSession:
        migrate_history()
        ui = self.ui
        kb = KeyBindings()

        def buffer_empty() -> bool:
            return not get_app().current_buffer.text

        @kb.add("s-tab")
        def _cycle(event: Any) -> None:  # ganti mode izin di tempat, ketikan tidak hilang
            ui.cycle_mode()
            event.app.invalidate()

        @kb.add("enter")
        def _enter(event: Any) -> None:
            buf = event.current_buffer
            state = buf.complete_state
            is_cmd = buf.text.lstrip().startswith("/") and " " not in buf.text.strip()
            if state and state.current_completion is not None and not is_cmd:
                buf.complete_state = None  # pilih @path dari menu, pesan belum dikirim
                return
            if buf.text.endswith("\\"):  # lanjut baris
                buf.delete_before_cursor(1)
                buf.insert_text("\n")
                return
            if state and is_cmd and state.current_completion is None and state.completions:
                buf.apply_completion(state.completions[0])  # "/cont" + Enter -> /context
            if ui.busy():  # Claude sedang bekerja: prompt tetap aktif, pesan dikirim / diantrekan dari sini
                text = buf.text.strip()
                if text:
                    buf.reset(append_to_history=True)
                    ui.submit_while_busy(text)
                event.app.invalidate()
                return
            buf.validate_and_handle()

        @kb.add("escape", "enter")
        def _newline(event: Any) -> None:  # Alt/Option+Enter = baris baru
            event.current_buffer.insert_text("\n")

        @kb.add("escape")
        def _esc(event: Any) -> None:
            buf = event.current_buffer
            if buf.complete_state:
                buf.cancel_completion()
            else:
                ui.interrupt_turn()  # Claude sedang bekerja (giliran kita / otomatis) -> hentikan

        @kb.add("c-c")
        def _ctrl_c(event: Any) -> None:
            if ui.interrupt_turn():  # Claude sedang bekerja -> hentikan dulu; Ctrl+C berikutnya baru ke "keluar"
                return
            event.app.exit(exception=KeyboardInterrupt(), style="class:aborting")

        @kb.add("c-d", filter=Condition(buffer_empty))
        def _ctrl_d(event: Any) -> None:
            if ui.busy() or ui.auto_running():  # tanya dulu di atas prompt, giliran yang jalan ikut mati
                asyncio.ensure_future(ui.confirm_exit_above())
            else:
                event.app.exit(exception=EOFError(), style="class:exiting")

        @kb.add("up", filter=Condition(lambda: bool(self.queue) and buffer_empty()))
        def _unqueue(event: Any) -> None:  # ↑ di kolom kosong: ambil kembali ketikan terakhir yang masih antre
            event.current_buffer.insert_text(self.queue.pop())

        session = PromptSession(
            history=FileHistory(str(HISTORY_FILE)),
            completer=Completions(self),
            complete_while_typing=True,
            reserve_space_for_menu=4,
            key_bindings=kb,
            bottom_toolbar=ui.toolbar,
            placeholder=self.placeholder,
            refresh_interval=1.0,  # toolbar diperbarui tiap detik saat idle (saat Claude bekerja: lihat _tick)
            prompt_continuation=ANSI("\x1b[1;36m… \x1b[0m"),
            style=PT_STYLE,
        )
        session.app.ttimeoutlen = 0.2  # Esc dikenali lebih cepat (bawaan 0.5 detik)
        session.app.timeoutlen = 0.4  # Esc tidak menunggu 1 detik penuh untuk kemungkinan Alt+Enter (Esc, Enter)
        return session

    def placeholder(self) -> Any:
        """Petunjuk di kolom kosong saat Claude bekerja."""
        return ANSI(f"\x1b[2m{BUSY_HINT}\x1b[0m") if self.ui.busy() else ""

    async def _tick(self) -> None:
        """Gambar ulang toolbar lebih sering saat Claude bekerja (spinner), tiap detik saat idle."""
        while True:
            await asyncio.sleep(0.12 if self.ui.busy() or self.ui.auto_running() else 1.0)
            app = self.session.app if self.session else None
            if app is not None and app.is_running:
                app.invalidate()

    async def read(self, prefill: str = "") -> str:
        if not self.interactive:  # stdin/stdout bukan terminal (pipe): input() biasa
            console.print()
            line = await asyncio.get_running_loop().run_in_executor(None, input, "› ")
            return line.strip()
        if self.session is None:
            self.session = self._build()
        if self.ticker is None:
            self.ticker = asyncio.ensure_future(self._tick())
        while True:
            err, self.ui.turn_error = self.ui.turn_error, None
            if err is not None:  # giliran (task) gagal saat prompt sedang tidak aktif
                raise err
            if self.queue and not self.ui.busy():  # antrean dari saat Claude bekerja: diproses seperti diketik sekarang
                text = self.queue.popleft()
                console.print()
                console.print(Text.assemble(("› ", "bold cyan"), (text, "")))
                self.gap = True
                return text
            default, self.draft = prefill or self.draft, ""  # ketikan yang disimpan drain() kembali ke prompt
            self.session.app.erase_when_done = False
            if self.gap:  # jarak antara ketikan sebelumnya dan output Claude yang akan dicetak di atas prompt ini
                console.print()
            self.gap = True
            # Baris kosong ikut jadi bagian prompt: tetap ada di atas "› …" walau output Claude dicetak di atas prompt.
            result = await self.session.prompt_async(ANSI("\n" + PROMPT_TEXT), default=default, handle_sigint=False)
            if result is DRAIN:  # prompt ditutup sementara oleh drain(): proses antrean dulu
                continue
            return result.strip()

    def drain(self) -> None:
        """Giliran selesai dan ada antrean: tutup prompt sementara (ketikan disimpan) supaya loop utama
        memproses antrean seperti ketikan biasa; read() membuka prompt lagi dengan ketikan tadi."""
        app = self.session.app if self.session else None
        if app is None or not app.is_running:
            return
        if not self.queue or self.ui.busy():
            app.invalidate()
            return
        self.draft = app.current_buffer.text
        app.erase_when_done = True  # baris prompt dihapus supaya tidak terlihat seperti pesan yang terkirim
        with contextlib.suppress(Exception):
            app.exit(result=DRAIN)

    async def run_above(self, func: Any) -> Any:
        """Jalankan func (cetak output / tanya izin) di atas prompt yang sedang aktif, lalu gambar ulang prompt."""
        app = self.session.app if self.session else None
        if app is None or not app.is_running:
            return func()
        with set_app(app):
            return await run_in_terminal(func)

    async def above(self, func: Any) -> Any:
        """Seperti run_above, tapi func boleh async. Selama func jalan, prompt disembunyikan dan terminal
        dalam mode normal (input() bisa dipakai); setelah itu prompt digambar ulang."""

        async def call() -> Any:
            r = func()
            return await r if inspect.isawaitable(r) else r

        app = self.session.app if self.session else None
        if app is None or not app.is_running:
            return await call()
        with set_app(app):
            async with in_terminal():
                return await call()

    def abort(self, err: BaseException) -> None:
        """Hentikan prompt yang sedang aktif dengan error (mis. mesin Claude mati). Kalau prompt sedang
        tidak aktif, error disimpan dan dilempar oleh read() berikutnya."""
        app = self.session.app if self.session else None
        if app is not None and app.is_running and app.future is not None and not app.future.done():
            with contextlib.suppress(Exception):
                app.exit(exception=err)
                return
        self.ui.turn_error = err

    def stop(self) -> None:
        if self.ticker is not None:
            self.ticker.cancel()
            self.ticker = None


class UI:
    def __init__(self, repo: Path, args: argparse.Namespace):
        self.repo = repo
        self.args = args
        self.client: ClaudeSDKClient | None = None
        self.spinner = Spinner("dots", style="cyan")
        self.live: Live | None = None  # spinner + baris progres tugas background di bawahnya
        self.spinning = False
        self.session_allow: set[str] = set()
        self.keys = KeyWatcher()
        self.prompt = PromptInput(self)
        self.pending_context: list[str] = []
        self.last_ctrl_c = 0.0
        self.auth_source = "(muncul setelah pesan pertama)"
        self.cli_version = ""
        self.bg_log = True  # tampilkan log aktivitas agent background di layar (/tasks log)
        self.goal_explained = False  # penjelasan panjang /goal cuma untuk goal pertama di run ini
        self.exit_code = 0
        self.perm_unanswerable = False  # izin ditolak otomatis karena tidak ada terminal (mis. -p di CI)
        self.exit_confirmed = False  # Ctrl+D saat Claude bekerja sudah dikonfirmasi (jangan tanya lagi di loop utama)
        self.begin_turn(None)
        self.reset()
        self.attach(None)

    def attach(self, client: ClaudeSDKClient | None) -> None:
        """Proses Claude baru (awal, /clear, /resume, auto-recovery): status giliran & tugas mulai dari nol."""
        self.client = client
        self.fg_active = False  # giliran yang kita kirim sedang berjalan (spinner + Esc aktif)
        self.cli_busy = False  # mesin Claude sedang memproses giliran apa pun (punya kita / otomatis)
        self.turn_future: asyncio.Future | None = None
        self.echo_seen = False
        self.result_ours = False
        self.auto_start = 0.0
        self.auto_interrupted = False
        self.auto_header = False
        self.bg_finished = False
        self.pump_error: BaseException | None = None
        self.tasks: dict[str, BgTask] = {}
        self.task_by_tool: dict[str, BgTask] = {}
        self.task_seq = 0
        self.goal_cmd: str | None = None  # jawaban /goal yang sedang ditunggu: "set" | "status" | "clear"
        self.goal_why: str | None = None  # None = diketik user; "after_turn" | "after_error" | "startup" | "recovered" | "print"
        self.goal_late = False  # cek status goal kehabisan waktu; jawabannya mungkin datang terlambat
        self.goal_err = ""  # subtype hasil giliran yang gagal, untuk pesan "dihapus otomatis setelah error"
        self.goal_auto_err = ""  # giliran otomatis berakhir error saat goal aktif -> cek ke Claude Code sebelum prompt berikutnya
        self.goal_dirty = False  # ada umpan balik Stop hook berkurung yang tidak cocok dengan goal lokal -> cek statusnya
        self.goal_refused = False  # /goal <kondisi> ditolak Claude Code (untuk exit code -p)
        self.goal_failed = False  # goal dihapus Claude Code setelah error (untuk exit code -p)
        self.quiet_turn = False  # giliran yang sedang jalan = cek status goal (bukan prompt user)
        self.auto_during_quiet = False  # giliran otomatis ternyata jalan saat cek status goal dikirim
        self.turn_prompt = ""
        self.turn_task: asyncio.Task | None = None  # giliran user yang jalan sebagai task (prompt tetap aktif)
        self.turn_error: BaseException | None = None  # error dari task giliran, dilempar oleh prompt.read()
        self.sent_pending: deque[list[Any]] = deque()  # [isi terkirim, label] pesan susulan yang belum dibaca Claude
        self.tui_turn = False  # giliran kita jalan dengan prompt aktif: spinner & Esc lewat prompt, bukan Live/KeyWatcher
        self.cont_seq = 0  # nomor urut giliran lanjutan (continue_turn), untuk pengaman waktunya
        # Biaya yang dipulihkan mesin untuk percakapan lanjutan (--resume, -c, /resume, sambung ulang): total_cost_usd
        # proses baru langsung membawa biaya lama percakapan itu. Angka itu titik nol, bukan pengeluaran run ini.
        self.cost_offset = 0.0
        self.cost_seen = False  # hasil pertama proses ini sudah diterima

    def reset(self) -> None:
        """Mulai percakapan baru dari nol (awal script, /clear, /resume)."""
        self.tool_names: dict[str, str] = {}
        self.cost_base = 0.0  # biaya dari proses sebelumnya (sebelum auto-recovery / /resume)
        self.cost_proc = 0.0  # pengeluaran proses yang sedang jalan (total_cost_usd - cost_offset, kumulatif)
        self.header_shown = False
        self.session_id: str | None = None
        self.failures = 0
        self.checkpoints: list[tuple[str, str]] = []  # (uuid pesan user, isi prompt) untuk /rewind
        self.ctx_pct: float | None = None
        self.goal: Goal | None = None  # goal aktif (/goal); hilang saat /clear & /resume, tetap saat sambung ulang
        self.last_goal: Goal | None = None
        self.plan_file: str | None = None  # file rencana yang terakhir ditulis Claude di plan mode (~/.claude/plans/…)

    def on_reconnect(self) -> None:
        """Proses baru setelah error (atau CLI me-reset hitungannya): biaya proses lama disimpan, hitungan baru dari 0."""
        self.cost_base += self.cost_proc
        self.cost_proc = 0.0
        self.cost_offset = 0.0
        self.cost_seen = False

    @property
    def cost_total(self) -> float:
        return self.cost_base + self.cost_proc

    # ---------- spinner + status kerja ----------
    def begin_turn(self, label: str | None) -> None:
        self.turn_start = time.monotonic()
        self.verb = random.choice(SPINNER_VERBS)
        self.current_tool: str | None = None
        self.out_tokens: dict[str, int] = {}
        self.printed_text = False
        self.checkpoint_label = label
        self.interrupted = False
        self.stopping = False  # Esc / Ctrl+C sudah ditekan untuk giliran ini
        self.waiting_bg = False
        self.turn_checks = 0  # cek goal (penolakan pemeriksa) di giliran ini
        self.turn_capped = False  # batas Stop hook tercapai di giliran ini
        self.goal_note = ""  # teks spinner sementara, mis. "pemeriksa menilai goal…"
        self.last_result: ResultMessage | None = None
        # (goal.paused sengaja TIDAK di-reset di sini: giliran "/goal" (status) harus tetap melihatnya;
        #  jeda dicabut di classify() begitu prompt user benar-benar diproses Claude)

    def status_text(self) -> Text:
        bits = [fmt_dur(time.monotonic() - self.turn_start)]
        tokens = sum(list(self.out_tokens.values()))
        if tokens:
            bits.append(f"↓ {fmt_tokens(tokens)} token")
        if self.goal:
            bits.append(self.goal_note or f"🎯 goal · {self.goal.checks} cek")
        bits.append("esc untuk berhenti")
        t = Text()
        if self.waiting_bg:
            n = len(self.running_bg())
            t.append(f"Menunggu {n} tugas background selesai…" if n else "Menunggu Claude menanggapi…", style="cyan")
        else:
            t.append(f"{self.verb}…", style="cyan")
            agent = self.active_fg_agent()
            if agent:  # sub-agent foreground sedang bekerja -> tampilkan progresnya
                t.append(f" Agent: {clip(agent.desc, 40)}", style="bold")
                prog = [f"{agent.tool_uses} tool"] if agent.tool_uses else []
                if agent.tokens:
                    prog.append(f"{fmt_tokens(agent.tokens)} token")
                if agent.activity:
                    prog.append(clip(agent.activity, 50))
                if prog:
                    t.append(" · " + " · ".join(prog))
            elif self.current_tool:
                t.append(f" {self.current_tool}", style="bold")
        t.append(f" ({' · '.join(bits)})", style="dim")
        return t

    def live_view(self) -> Any:
        """Isi area live saat Claude bekerja: spinner + progres tugas background (dipanggil tiap refresh)."""
        try:
            self.spinner.update(text=self.status_text())
            rows: list[Any] = [self.spinner]
            rows += self.task_rows(max(console.width - 1, 20))
            return Group(*rows)
        except Exception:  # jangan sampai thread refresh mati gara-gara data sedang berubah
            return self.spinner

    def spin_start(self, tool: str | None = None) -> None:
        self.current_tool = tool
        if not self.fg_active or self.tui_turn:  # Live cuma saat giliran jalan tanpa prompt (-p); selain itu spinner ada di toolbar
            return
        if not self.spinning:
            # Live baru tiap kali: Live lama "ingat" tinggi areanya dan akan menghapus baris yang baru dicetak.
            self.live = Live(console=console, get_renderable=self.live_view, refresh_per_second=8, transient=True)
            self.live.start()
            self.spinning = True

    def spin_stop(self) -> None:
        if self.spinning and self.live is not None:
            self.live.stop()
        self.spinning = False

    # ---------- status tugas background ----------
    def running_bg(self) -> list[BgTask]:
        return [t for t in list(self.tasks.values()) if t.detached and t.status == "running"]

    def active_fg_agent(self) -> BgTask | None:
        for t in reversed(list(self.tasks.values())):
            if t.kind == "agent" and not t.background and t.status == "running":
                return t
        return None

    def auto_running(self) -> bool:
        """Claude sedang menjalankan giliran otomatis (mis. menanggapi tugas background yang selesai)."""
        return self.cli_busy and not self.fg_active and self.turn_future is None

    def task_line(self, t: BgTask, width: int) -> Text:
        icon, style, _ = STATUS_VIEW.get(t.status, ("•", "dim", t.status))
        line = Text("  ")
        line.append(f"{icon} ", style=style)
        line.append(f"#{t.num} ", style="bold")
        line.append(clip(oneline(t.desc), 40) or t.label, style="bold")
        line.append(" · " + " · ".join([t.kind] + t.stats()), style="dim")
        latest = t.latest()
        if latest:
            line.append(" · " + oneline(latest), style="dim italic")
        line.truncate(width, overflow="ellipsis")
        return line

    def task_rows(self, width: int) -> list[Text]:
        running = self.running_bg()
        rows = [self.task_line(t, width) for t in running[:MAX_TASK_LINES]]
        if len(running) > MAX_TASK_LINES:
            rows.append(Text(f"    … +{len(running) - MAX_TASK_LINES} tugas background lagi · /tasks", style="dim"))
        return rows

    def footer(self) -> Text:
        mode = self.args.mode
        t = Text("  ")
        t.append(MODE_LABEL.get(mode, mode), style="bold red" if mode == "bypassPermissions" else "magenta")
        if mode in MODE_CYCLE:
            t.append(" (shift+tab)", style="dim")
        extra = [self.args.model.replace("claude-", "")]
        if self.ctx_pct is not None:
            extra.append(f"konteks {self.ctx_pct:.0f}%")
        extra.append(f"${self.cost_total:.4f}")
        t.append("  ·  " + " · ".join(extra), style="dim")
        g = self.goal
        if g:
            t.append(f"  ·  🎯 goal · {fmt_dur(time.monotonic() - g.set_at)} · {g.checks} cek" + (" ⏸" if g.paused else ""),
                     style="yellow" if g.paused else "cyan")
            t.append(" (/goal)", style="dim")
        n = len(self.running_bg())
        if n:
            t.append(f"  ·  ⧗ {n} background", style="yellow")
            t.append(" (/tasks)", style="dim")
        elif not g:
            t.append(" · ? untuk bantuan", style="dim")
        return t

    def queue_rows(self) -> list[Text]:
        """Pesan susulan yang belum dibaca Claude + ketikan yang antre sampai giliran selesai (toolbar)."""
        rows: list[Text] = []
        pending = [label for _, label in list(self.sent_pending)]
        queued = list(self.prompt.queue)
        for what, items in (("dibaca Claude setelah langkah ini", pending), ("setelah giliran selesai", queued)):
            for text in items[:2]:
                rows.append(Text.assemble(("  ⏳ ", "yellow"), (f"{what}: ", "dim"), (clip(oneline(text), 70), "")))
            if len(items) > 2:
                rows.append(Text(f"     … +{len(items) - 2} lagi", style="dim"))
        if queued:
            rows[-1].append("  (↑ di kolom kosong = ambil kembali)", style="dim")
        return rows

    def toolbar(self) -> Any:
        """Toolbar di bawah prompt: mode/model/biaya, spinner saat Claude bekerja, pesan yang antre,
        progres live tugas background."""
        try:
            width = max(shutil.get_terminal_size().columns - 1, 20)
            lines = [self.footer()]
            if self.fg_active:  # giliran kita jalan dengan prompt aktif: spinner di sini (bukan Live)
                self.spinner.update(text=self.status_text())
                lines.append(self.spinner.render(time.monotonic()))  # type: ignore[arg-type]
            elif self.auto_running():
                lines.append(Text(f"  ✻ Claude menanggapi tugas background… ({fmt_dur(time.monotonic() - self.auto_start)}"
                                  " · esc untuk berhenti)", style="cyan"))
            lines += self.queue_rows()
            lines += self.task_rows(width)
            for line in lines:
                line.truncate(width, overflow="ellipsis")
            return ANSI(to_ansi(Text("\n").join(lines), width + 1))
        except Exception:
            return ""

    def cycle_mode(self) -> None:
        """Shift+Tab: default -> acceptEdits -> plan (dari mode lain balik ke default)."""
        cur = self.args.mode
        new = MODE_CYCLE[(MODE_CYCLE.index(cur) + 1) % len(MODE_CYCLE)] if cur in MODE_CYCLE else "default"
        self.args.mode = new
        if self.client:
            asyncio.ensure_future(self._call(self.client.set_permission_mode(new)))

    @staticmethod
    async def _call(coro: Any) -> None:
        with contextlib.suppress(Exception):
            await coro

    def interrupt_auto(self) -> None:
        if not self.client or not self.cli_busy or self.auto_interrupted:
            return
        self.auto_interrupted = True
        asyncio.ensure_future(self._call(self.client.interrupt()))
        asyncio.ensure_future(self.say("[yellow]⏹ Menghentikan respons otomatis Claude…[/]"))

    async def say(self, *objs: Any, **kw: Any) -> None:
        """console.print yang aman dipakai kapan saja (kalau prompt aktif, dicetak di atas prompt)."""
        if self.prompt.active():
            with console.capture() as cap:
                console.print(*objs, **kw)
            out = cap.get()
            await self.prompt.run_above(lambda: write_raw(out))
        else:
            console.print(*objs, **kw)

    def note(self, *objs: Any, **kw: Any) -> None:
        """Versi sinkron say(): aman dipanggil dari key binding / callback."""
        if self.prompt.active():
            asyncio.ensure_future(self.say(*objs, **kw))
        else:
            console.print(*objs, **kw)

    # ---------- kolom chat saat Claude bekerja ----------
    def busy(self) -> bool:
        """Giliran user (yang kita kirim) sedang jalan -> Enter di prompt = pesan susulan / antrean."""
        return self.turn_task is not None or self.fg_active

    def can_steer(self) -> bool:
        """Pesan susulan bisa langsung dikirim: giliran kita jalan dengan prompt aktif (bukan cek status goal)."""
        return (self.fg_active and self.tui_turn and not self.quiet_turn and not self.waiting_bg
                and self.client is not None and self.pump_error is None)

    def submit_while_busy(self, text: str) -> None:
        """Enter saat Claude bekerja. Pesan biasa langsung dikirim - Claude Code menyisipkannya begitu tool call
        yang sedang jalan selesai ("steering", persis Claude Code). Perintah ringan (/tasks, /help, …) dijalankan
        saat itu juga; sisanya (/clear, !command, # catatan, …) antre sampai giliran selesai. Begitu ada yang antre,
        ketikan berikutnya ikut antre supaya urutannya tetap seperti yang diketik."""
        if text == "?":
            text = "/help"
        word = text.split()[0] if text.startswith("/") else ""
        plain = not text.startswith(("/", "!", "#")) or text.startswith("##")
        if not self.prompt.queue and word in IMMEDIATE_COMMANDS:
            asyncio.ensure_future(self.run_local(text))
        elif plain and not self.prompt.queue and self.can_steer():
            asyncio.ensure_future(self.steer(text))
        else:
            self.prompt.queue.append(text)

    async def run_local(self, text: str) -> None:
        """Perintah ringan saat Claude bekerja: dijalankan di atas prompt saat itu juga. Panggilan ke mesin Claude
        (/stop, /mode) dijadwalkan terpisah supaya pembaca pesan tidak ikut menunggu di balik prompt."""
        name, _, arg = text.partition(" ")
        arg = arg.strip()
        client = self.client

        async def job() -> None:
            self.show_user(text, gap=False)
            if name == "/stop":
                targets = stop_targets(self, arg)
                for t in targets:
                    console.print(f"[yellow]⏹ Menghentikan #{t.num} {clip(oneline(t.desc), 60)}…[/]")
                if targets and client is not None:
                    asyncio.ensure_future(stop_bg(client, self, targets))
            elif name == "/mode" and arg in MODES:
                self.args.mode = arg
                if client is not None:
                    asyncio.ensure_future(self._call(client.set_permission_mode(arg)))
                console.print(f"[green]✓ Mode izin diganti ke {arg}[/]")
            elif client is not None:
                await handle_command(text, client, self)

        try:
            await self.prompt.above(job)
        except Exception as e:
            self.note(f"[red]✗ {name} gagal: {e}[/]")

    async def steer(self, text: str) -> None:
        """Pesan susulan: dikirim sekarang juga. Claude Code menyisipkannya setelah tool call yang sedang jalan
        selesai; kalau giliran keburu selesai (atau dihentikan), pesan ini otomatis jadi giliran berikutnya
        (lihat continue_turn). Gemanya ("› …") dicetak begitu Claude benar-benar membacanya."""
        entry: list[Any] = [None, text]  # dicatat dulu: kalau hasil giliran datang duluan, giliran dianggap berlanjut
        self.sent_pending.append(entry)
        try:
            to_send = await self.prompt.above(lambda: compose(self, text))
            entry[0] = to_send
            if self.client is None:
                raise ClaudeSDKError("mesin Claude tidak aktif")
            await self.client.query(to_send)
        except Exception as e:
            with contextlib.suppress(ValueError):
                self.sent_pending.remove(entry)
            self.note(f"[red]✗ Gagal mengirim pesan susulan: {e}[/]")

    def take_sent(self, content: str) -> str | None:
        """Gema pesan user dari mesin Claude: cocokkan dengan pesan susulan yang menunggu -> labelnya."""
        for entry in list(self.sent_pending):
            sent, label = entry
            if sent is not None and sent.strip() == content.strip():
                self.sent_pending.remove(entry)
                return label
        return None

    def interrupt_turn(self) -> bool:
        """Esc / Ctrl+C saat Claude bekerja: hentikan giliran kita (atau giliran otomatis).
        True kalau ada yang dihentikan."""
        if self.fg_active:
            if self.stopping:
                return False
            self.stopping = True
            fut = self.turn_future
            lead = "" if self.tui_turn else "\n"  # tanpa prompt: spinner Live baru saja dihapus, mulai di baris baru
            if self.quiet_turn:  # cek status goal: cukup berhenti menunggu; jangan hentikan giliran Claude yang mungkin jalan
                self.goal_late = True
                self.spin_stop()
                self.note(f"{lead}[dim]cek status goal dilewati[/]")
                if fut is not None and not fut.done():
                    fut.set_result(None)
                return True
            self.interrupted = True
            self.spin_stop()
            self.note(f"{lead}[yellow]⏹ Menghentikan Claude…[/]")
            if self.client:
                asyncio.ensure_future(self._call(self.client.interrupt()))
            return True
        if self.auto_running() and not self.auto_interrupted:
            self.interrupt_auto()
            return True
        return False

    async def confirm_exit_above(self) -> None:
        """Ctrl+D saat Claude bekerja: tanya dulu di atas prompt; kalau ya, prompt ditutup (loop utama keluar)."""
        if await self.prompt.above(lambda: confirm_drop_tasks(self, "keluar")):
            self.exit_confirmed = True
            self.prompt.abort(EOFError())

    def on_turn_finished(self) -> None:
        """Task giliran selesai: proses antrean (kalau ada) lewat prompt, atau cukup segarkan toolbar."""
        self.turn_task = None
        self.prompt.drain()

    def continue_turn(self) -> None:
        """Hasil giliran datang padahal masih ada pesan susulan yang belum dibaca Claude: Claude Code langsung
        memulai giliran baru untuk pesan itu, jadi giliran kita (spinner, Esc, antrean) tetap dianggap jalan."""
        sent, label = self.sent_pending[0]
        self.begin_turn(label)
        self.quiet_turn, self.turn_prompt = False, sent or ""
        self.cont_seq += 1
        asyncio.get_running_loop().call_later(10, self._continuation_check, self.turn_future, self.cont_seq)

    def _continuation_check(self, fut: asyncio.Future, seq: int) -> None:
        if seq != self.cont_seq or fut is not self.turn_future or fut.done() or self.cli_busy:
            return
        for _, label in list(self.sent_pending):  # mesin tidak memulai giliran untuk pesan ini: jangan menunggu selamanya
            self.note(f"[yellow]⚠ Pesan susulan tidak diproses Claude:[/] {rich_escape(clip(oneline(label), 80))}")
        self.sent_pending.clear()
        fut.set_result(self.last_result)

    # ---------- format tampilan tool ----------
    def rel(self, p: str) -> str:
        if not p:
            return ""
        try:
            return str(Path(p).resolve().relative_to(self.repo))
        except (ValueError, OSError):
            return p

    def abs_path(self, p: str) -> Path:
        path = Path(p).expanduser()
        return path if path.is_absolute() else self.repo / path

    def find_line(self, path: str, old: str, new: str) -> int:
        """Cari nomor baris tempat edit terjadi (sebelum atau sesudah edit diterapkan)."""
        try:
            f = self.abs_path(path)
            if f.stat().st_size > 5_000_000:
                return 1
            text = f.read_text(errors="replace")
        except OSError:
            return 1
        for needle in (old, new):
            if needle:
                idx = text.find(needle)
                if idx >= 0:
                    return text.count("\n", 0, idx) + 1
        return 1

    def edit_view(self, path: str, old: str, new: str, max_lines: int = 14) -> Group:
        start = self.find_line(path, old, new)
        old_l, new_l = old.splitlines(), new.splitlines()
        rows: list[tuple[int | None, str, str]] = []
        adds = dels = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_l, new_l, autojunk=False).get_opcodes():
            if tag == "equal":
                seg: list[tuple[int | None, str, str]] = [(start + j1 + k, " ", new_l[j1 + k]) for k in range(j2 - j1)]
                if len(seg) > 4:
                    seg = seg[:2] + [(None, "⋮", "")] + seg[-2:]
                rows += seg
                continue
            rows += [(start + i, "-", old_l[i]) for i in range(i1, i2)]
            rows += [(start + j, "+", new_l[j]) for j in range(j1, j2)]
            dels += i2 - i1
            adds += j2 - j1
        width = len(str(max((r[0] or 0) for r in rows))) if rows else 1
        body = Text()
        for ln, sign, line in rows[:max_lines]:
            if sign == "⋮":
                body.append(" " * width + "  ⋮\n", style="dim")
                continue
            style = {"+": "green", "-": "red"}.get(sign, "dim")
            body.append(f"{ln:>{width}} {sign} ", style="dim" if sign == " " else style)
            body.append(clip(line, 150) + "\n", style=style)
        if len(rows) > max_lines:
            body.append(f"… +{len(rows) - max_lines} baris diff lagi\n", style="dim")
        body.rstrip()
        parts = []
        if adds:
            parts.append(f"ditambah {adds} baris")
        if dels:
            parts.append(f"dihapus {dels} baris")
        summary = Text(", ".join(parts).capitalize() or "Tanpa perubahan", style="dim")
        return Group(summary, body)

    @staticmethod
    def write_view(content: str, max_lines: int = 6) -> Text:
        lines = content.splitlines()
        width = len(str(min(len(lines), max_lines))) if lines else 1
        t = Text(f"Menulis {len(lines)} baris\n", style="dim")
        for i, line in enumerate(lines[:max_lines], 1):
            t.append(f"{i:>{width}}  ", style="dim")
            t.append(clip(line, 150) + "\n")
        if len(lines) > max_lines:
            t.append(f"… +{len(lines) - max_lines} baris\n", style="dim")
        t.rstrip()
        return t

    @staticmethod
    def todo_view(todos: list[dict[str, Any]]) -> Text:
        t = Text()
        for item in todos:
            status = item.get("status")
            content = item.get("content", "")
            if status == "completed":
                t.append("☒ " + content + "\n", style="green dim strike")
            elif status == "in_progress":
                t.append("◐ " + item.get("activeForm", content) + "\n", style="bold yellow")
            else:
                t.append("☐ " + content + "\n")
        t.rstrip()
        return t

    def describe_tool(self, name: str, inp: dict[str, Any], full: bool = False) -> tuple[str, Any]:
        """Kembalikan (ringkasan satu baris, detail tambahan atau None). full=True untuk prompt izin."""
        if name == "Read":
            s = self.rel(inp.get("file_path", ""))
            if inp.get("offset") or inp.get("limit"):
                s += f", baris {inp.get('offset', 1)}" + (f"+{inp['limit']}" if inp.get("limit") else "")
            return s, None
        if name == "Write":
            return self.rel(inp.get("file_path", "")), self.write_view(inp.get("content", ""), 20 if full else 6)
        if name == "Edit":
            return self.rel(inp.get("file_path", "")), self.edit_view(
                inp.get("file_path", ""), inp.get("old_string", ""), inp.get("new_string", ""), 40 if full else 14
            )
        if name == "MultiEdit":
            edits = inp.get("edits", [])
            path = inp.get("file_path", "")
            views: list[Any] = [
                self.edit_view(path, e.get("old_string", ""), e.get("new_string", ""), 12 if full else 8)
                for e in edits[:3]
            ]
            if len(edits) > 3:
                views.append(Text(f"… +{len(edits) - 3} edit lagi", style="dim"))
            return f"{self.rel(path)}, {len(edits)} edit", Group(*views)
        if name == "NotebookEdit":
            return self.rel(inp.get("notebook_path", "")), None
        if name in ("Bash", "PowerShell"):  # PowerShell: tool shell Claude Code di Windows tanpa Git Bash
            desc = inp.get("description")
            cmd = inp.get("command", "")
            if full:
                return "", Group(Text(cmd, style="bold"), *([Text(desc, style="dim")] if desc else []))
            extra = " (latar belakang)" if inp.get("run_in_background") else ""
            return clip(cmd, 300) + extra, (Text(desc, style="dim") if desc else None)
        if name in ("Glob", "Grep"):
            s = f'"{inp.get("pattern", "")}"'
            if inp.get("path"):
                s += f" di {self.rel(inp['path'])}"
            if inp.get("glob"):
                s += f" ({inp['glob']})"
            return s, None
        if name == "WebSearch":
            return inp.get("query", ""), None
        if name == "WebFetch":
            return inp.get("url", ""), None
        if name in ("Task", "Agent"):
            bg = " · background" if inp.get("run_in_background") else ""
            return f"{inp.get('subagent_type', 'agent')}: {inp.get('description', '')}{bg}", None
        if name in ("TaskStop", "TaskOutput", "BashOutput", "KillShell"):
            tid = str(inp.get("task_id") or inp.get("shell_id") or inp.get("bash_id") or "")
            t = self.tasks.get(tid)
            return (f"#{t.num} {t.desc}" if t else tid), None
        if name == "Monitor":
            return clip(oneline(str(inp.get("description") or inp.get("command") or "")), 200), None
        if name == "SendMessage":
            return f"→ {inp.get('to', '')}: {clip(oneline(str(inp.get('summary') or inp.get('message') or '')), 100)}", None
        if name == "ScheduleWakeup":
            return f"{inp.get('delaySeconds', '?')} detik · {clip(str(inp.get('reason', '')), 100)}", None
        if name == "TodoWrite":
            return "", self.todo_view(inp.get("todos", []))
        if name == "Skill":
            return inp.get("skill", inp.get("command", "")), None
        if name == "ToolSearch":
            return inp.get("query", ""), None
        if name == "ExitPlanMode":
            return "", None  # rencananya ditampilkan di panel persetujuan
        return clip(json.dumps(inp, ensure_ascii=False), 400 if full else 160), None

    # ---------- tampilan pesan (versi GUI: WebUI) ----------
    def show_text(self, text: str) -> None:
        """Jawaban Claude (markdown)."""
        console.print()
        console.print(Markdown(text))
        console.print()

    def show_thinking(self, text: str) -> None:
        lines = text.splitlines()
        body = "\n".join(lines[:6]) + (f"\n… +{len(lines) - 6} baris" if len(lines) > 6 else "")
        console.print(Text("✻ Berpikir…", style="dim italic"))
        console.print(Padding(Text(body, style="dim italic"), (0, 0, 0, 2)))

    def show_user(self, text: str, gap: bool = True) -> None:
        """Pesan user yang baru diproses (pesan susulan yang dibaca Claude, perintah yang dijalankan saat Claude bekerja)."""
        if gap:
            console.print()
        console.print(Text.assemble(("› ", "bold cyan"), (text, "")))

    def print_tool_use(self, block: ToolUseBlock, nested: bool) -> None:
        summary, detail = self.describe_tool(block.name, block.input or {})
        label = TOOL_LABEL.get(block.name, block.name)
        indent = 4 if nested else 0
        line = Text.assemble(("● ", "magenta" if nested else "green"), (label, "bold"))
        if summary:
            line.append(f"({summary})")
        console.print(Padding(line, (0, 0, 0, indent)))
        if detail is not None:
            console.print(Padding(detail, (0, 0, 0, indent + 4)))

    @staticmethod
    def result_text(block: ToolResultBlock) -> str:
        c = block.content
        if c is None:
            return ""
        if isinstance(c, str):
            return c
        parts = []
        for item in c:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, dict) and item.get("type") == "image":
                parts.append("[gambar]")
        return "\n".join(parts)

    def print_tool_result(self, block: ToolResultBlock, nested: bool) -> None:
        msg = self.result_summary(block)
        if msg is not None:
            console.print(Padding(Text(f"⎿  {msg}", style="red" if block.is_error else "dim"), (0, 0, 0, 6 if nested else 2)))

    def result_summary(self, block: ToolResultBlock) -> str | None:
        """Ringkasan hasil tool (baris "⎿ …"); None = tidak perlu ditampilkan."""
        name = self.tool_names.get(block.tool_use_id, "")
        text = self.result_text(block).strip("\n")
        if block.is_error:
            return "Error: " + clip(text.splitlines()[0] if text else "gagal", 300)
        if name == "TodoWrite":
            return None
        task = self.task_by_tool.get(block.tool_use_id)
        if name == "Read":
            msg = f"Membaca {len(text.splitlines())} baris"
        elif name in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
            msg = "Tersimpan"
        elif name in ("Task", "Agent"):
            msg = self.agent_result(text, task)
        elif task is not None and task.background:  # Bash / Monitor yang dijalankan di background
            m = re.search(r"written to: (\S+)", text)
            if m and not task.output_file:
                task.output_file = m.group(1).rstrip(".")
            msg = f"Berjalan di background sebagai #{task.num} · progres tampil live, detail: /tasks {task.num}"
        else:
            lines = text.splitlines() or ["(tidak ada output)"]
            shown = [clip(x, 180) for x in lines[:4]]
            if len(lines) > 4:
                shown.append(f"… +{len(lines) - 4} baris")
            msg = "\n   ".join(shown)
        return msg

    @staticmethod
    def agent_result(text: str, task: BgTask | None) -> str:
        """Hasil tool Agent: 'Selesai (3 tool · 12.3k token · 8s)' + awal laporannya (tanpa metadata internal)."""
        if text.startswith("Async agent launched"):
            num = f" sebagai #{task.num}" if task else ""
            return f"Berjalan di background{num} · progres tampil live di bawah prompt, detail: /tasks"
        usage: dict[str, int] = {}
        m = re.search(r"<usage>(.*?)</usage>", text, re.S)
        if m:
            usage = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", m.group(1))}
        tokens = usage.get("subagent_tokens") or usage.get("total_tokens") or (task.tokens if task else 0)
        tools = usage.get("tool_uses", task.tool_uses if task else 0)
        dur = usage.get("duration_ms", 0) / 1000 or (task.elapsed() if task else 0)
        report = text.split("The report follows:", 1)[-1]
        report = re.split(r"\nagentId: ", report)[0]
        report = re.sub(r"<(tools-used-before-summary|usage)>.*?</\1>", "", report, flags=re.S)
        lines = [ln.strip() for ln in report.strip().splitlines() if ln.strip()]
        head = f"Selesai ({tools} tool · {fmt_tokens(tokens)} token · {fmt_dur(dur)})"
        shown = [clip(x, 180) for x in lines[:3]] + ([f"… +{len(lines) - 3} baris"] if len(lines) > 3 else [])
        return "\n   ".join([head, *shown])

    # ---------- event tugas background ----------
    def on_task_event(self, msg: Any) -> None:
        d = msg.data if isinstance(getattr(msg, "data", None), dict) else {}
        if isinstance(msg, TaskStartedMessage):
            ttype = msg.task_type or d.get("task_type") or ""
            detached = bool(d.get("is_backgrounded"))
            parent = self.tasks.get(d.get("parent_task_id") or "")
            if ttype != "local_agent" and not detached:
                return  # command biasa milik sebuah agent (ditunggu), cukup tercatat sebagai aktivitas agent
            t = self.tasks.get(msg.task_id)
            if t is None:
                self.task_seq += 1
                t = self.tasks[msg.task_id] = BgTask(id=msg.task_id, num=self.task_seq,
                                                      kind=TASK_KIND.get(ttype, ttype or "tugas"),
                                                      desc=msg.description or "")
                if parent:
                    parent.note(f"▸ memulai #{t.num} {t.label.lower()}: {clip(t.desc, 80)}")
            # (daftar background dari CLI kadang datang duluan -> lengkapi datanya di sini)
            t.desc = msg.description or t.desc
            t.agent_type = str(d.get("subagent_type") or t.agent_type)
            t.tool_use_id = msg.tool_use_id or t.tool_use_id
            t.prompt = str(d.get("prompt") or t.prompt)
            t.parent = d.get("parent_task_id") or t.parent
            t.detached = t.detached or detached
            t.background = t.detached or bool(parent and parent.background)
            if t.tool_use_id:
                self.task_by_tool[t.tool_use_id] = t
            return
        t = self.tasks.get(msg.task_id)
        if t is None:
            return
        if isinstance(msg, TaskProgressMessage):
            u = msg.usage or {}
            t.tokens = int(u.get("total_tokens") or t.tokens)
            t.tool_uses = int(u.get("tool_uses") or t.tool_uses)
            t.last_tool = msg.last_tool_name or t.last_tool
            if msg.description and msg.description != t.desc and not t.activity:
                t.activity = msg.description
        elif isinstance(msg, TaskUpdatedMessage):
            patch = msg.patch or {}
            if patch.get("is_backgrounded"):
                t.background = t.detached = True
            status = msg.status or patch.get("status")
            if status in TERMINAL_STATUSES:
                t.finish(status)  # diumumkan saat notifikasi / daftar background berubah (ada ringkasannya)
        elif isinstance(msg, TaskNotificationMessage):
            t.summary = msg.summary or t.summary
            t.output_file = msg.output_file or t.output_file
            if msg.usage:
                t.tokens = int(msg.usage.get("total_tokens") or t.tokens)
                t.tool_uses = int(msg.usage.get("tool_uses") or t.tool_uses)
            t.finish(msg.status)
            self.announce(t)

    def on_bg_changed(self, tasks: list[dict[str, Any]]) -> None:
        """Daftar resmi tugas background yang masih jalan (dari CLI)."""
        alive = set()
        for info in tasks or []:
            tid = str(info.get("task_id") or "")
            if not tid:
                continue
            alive.add(tid)
            if tid not in self.tasks:  # biasanya datang sebelum task_started
                self.task_seq += 1
                ttype = str(info.get("task_type") or "")
                self.tasks[tid] = BgTask(id=tid, num=self.task_seq, kind=TASK_KIND.get(ttype, ttype or "tugas"),
                                         desc=str(info.get("description") or ""),
                                         agent_type=str(info.get("subagent_type") or ""))
            self.tasks[tid].background = self.tasks[tid].detached = True
        for t in list(self.tasks.values()):
            if t.detached and t.id not in alive and t.status == "running":
                t.finish("completed")
            self.announce(t)

    def announce(self, t: BgTask) -> None:
        """Satu baris saat tugas background selesai / gagal / dihentikan."""
        if t.announced or not t.background or t.status == "running":
            return
        if not t.detached:  # agent di dalam agent background: cukup dicatat di log induknya
            t.announced = True
            parent = self.tasks.get(t.parent or "")
            if parent:
                parent.note(f"▸ #{t.num} {STATUS_VIEW.get(t.status, ('', '', t.status))[2]}: {clip(t.desc, 80)}")
            return
        t.announced = True
        self.bg_finished = True
        icon, style, word = STATUS_VIEW.get(t.status, ("•", "dim", t.status))
        self.spin_stop()
        line = Text.assemble((f"{icon} ", style), (f"#{t.num} ", "bold"), (f"{t.label} background {word}: ", style),
                             (clip(oneline(t.desc), 80), "bold"), (" · " + " · ".join(t.stats()), "dim"))
        console.print(line)
        summary = t.summary if t.summary and t.summary != t.desc else ""
        if summary:
            console.print(Padding(Text(clip(oneline(summary), 300), style="dim"), (0, 0, 0, 2)))
        self.spin_start(self.current_tool)

    def render_bg(self, task: BgTask, msg: Any) -> None:
        """Pesan dari agent background: dicatat ke log-nya (/tasks N) + satu baris ringkas di layar."""
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, ToolUseBlock):
                    self.tool_names[b.id] = b.name
                    summary, _ = self.describe_tool(b.name, b.input or {})
                    entry = TOOL_LABEL.get(b.name, b.name) + (f"({clip(oneline(summary), 120)})" if summary else "")
                    task.note(entry)
                    task.activity = entry
                    if self.bg_log:
                        self.print_bg(task, entry)
                elif isinstance(b, TextBlock) and b.text.strip():
                    task.note("💬 " + clip(oneline(b.text), 300))
        elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
            for b in msg.content:
                if isinstance(b, ToolResultBlock) and b.is_error:
                    first = (self.result_text(b).strip().splitlines() or ["gagal"])[0]
                    task.note("✗ " + clip(first, 200))
                    if self.bg_log:
                        self.print_bg(task, "✗ " + first, "red")

    def print_bg(self, task: BgTask, entry: str, style: str = "dim") -> None:
        self.spin_stop()
        line = Text.assemble(("  ⧗ ", "yellow"), (f"#{task.num} {clip(oneline(task.desc), 30)}", "bold dim"),
                             (" › ", "dim"), (oneline(entry), style))
        line.truncate(max(console.width - 1, 20), overflow="ellipsis")
        console.print(line)
        self.spin_start(self.current_tool)

    # ---------- pesan dari SDK ----------
    def render(self, msg: Any) -> None:
        if isinstance(msg, RateLimitEvent):
            info = msg.rate_limit_info
            status = getattr(info, "status", "")
            if status and status != "allowed":
                console.print(f"[yellow]⚠ Rate limit: {status}[/]")
            return
        if isinstance(msg, ConversationResetMessage):
            self.on_reconnect()  # total biaya proses di-reset oleh CLI; simpan yang lama
            return
        if TASK_EVENTS and isinstance(msg, TASK_EVENTS):
            self.on_task_event(msg)
            return
        if isinstance(msg, SystemMessage):
            if msg.subtype == "init":
                self.on_init(msg.data)
                if self.auto_header:  # CLI memulai giliran sendiri (mis. tugas background selesai)
                    self.print_auto_header()
            elif msg.subtype == "background_tasks_changed":
                self.on_bg_changed(msg.data.get("tasks") or [])
            elif msg.subtype == "compact_boundary":
                console.print("[dim]✻ Konteks percakapan dipadatkan (compact)[/]")
            elif msg.subtype == "notification":
                self.on_notification(msg.data)
            return

        parent_id = getattr(msg, "parent_tool_use_id", None)
        nested = bool(parent_id)
        task = self.task_by_tool.get(parent_id) if parent_id else None
        if task is not None and task.background:  # pesan dari agent background
            self.render_bg(task, msg)
            return

        if isinstance(msg, AssistantMessage):
            if msg.error:
                console.print(f"[red]⚠ Error dari API: {msg.error}[/]")
            usage = getattr(msg, "usage", None) or {}
            if usage.get("output_tokens"):
                key = getattr(msg, "message_id", None) or str(id(msg))
                self.out_tokens[key] = usage["output_tokens"]
            if self.goal and not nested and getattr(msg, "stop_reason", None) == "end_turn":
                self.goal_note = "🎯 pemeriksa menilai goal…"  # Claude selesai bicara -> Stop hook (pemeriksa) jalan
            for b in msg.content:
                if isinstance(b, TextBlock) and b.text.strip():
                    self.spin_stop()
                    if nested:
                        console.print(Padding(Text(clip(b.text, 400), style="dim"), (0, 0, 0, 4)))
                    elif self.on_goal_reply(b.text):
                        self.printed_text = True  # jawaban lokal /goal dari Claude Code -> versi Indonesia
                    else:
                        self.printed_text = True
                        self.show_text(b.text)
                elif isinstance(b, ThinkingBlock) and b.thinking.strip():
                    self.spin_stop()
                    self.show_thinking(b.thinking.strip())
                elif isinstance(b, ToolUseBlock):
                    self.spin_stop()
                    self.tool_names[b.id] = b.name
                    path = (b.input or {}).get("file_path") if b.name in ("Write", "Edit", "MultiEdit") else None
                    if path and Path(str(path)).parent.name == "plans" and str(path).endswith(".md"):
                        self.plan_file = str(path)
                    self.print_tool_use(b, nested)
                    self.current_tool = b.name
                    if task is not None:  # sub-agent foreground: catat untuk spinner & /tasks
                        summary, _ = self.describe_tool(b.name, b.input or {})
                        task.activity = TOOL_LABEL.get(b.name, b.name) + (f"({clip(oneline(summary), 80)})" if summary else "")
                        task.note(task.activity)
            self.spin_start(self.current_tool)
        elif isinstance(msg, UserMessage):
            self.goal_note = ""
            if self.auto_header and not nested:  # giliran otomatis yang baru terdeteksi (lihat classify)
                self.print_auto_header()
            blocks = msg.content if isinstance(msg.content, list) else []
            results = [b for b in blocks if isinstance(b, ToolResultBlock)]
            if results:
                self.spin_stop()
                for b in results:
                    self.print_tool_result(b, nested)
                self.spin_start()
            elif (not nested and blocks and isinstance(blocks[0], TextBlock)
                  and blocks[0].text.startswith("Stop hook feedback:")):
                self.on_stop_feedback(blocks[0].text)  # pemeriksa goal: "belum terpenuhi" + alasannya
            elif not nested and isinstance(msg.content, str) and is_ours(getattr(msg, "origin", None)):
                label = self.take_sent(msg.content)
                if label is not None:  # pesan susulan baru dibaca Claude -> tampilkan di titik ini
                    self.spin_stop()
                    self.show_user(label)
                    self.checkpoint_label = label
                    self.spin_start(self.current_tool)
                if msg.uuid and self.checkpoint_label is not None:
                    # Gema dari prompt user sendiri (bukan notifikasi otomatis) -> titik untuk /rewind
                    self.checkpoints.append((msg.uuid, self.checkpoint_label))
                    self.checkpoint_label = None
        elif isinstance(msg, ResultMessage):
            self.on_result(msg)

    def print_auto_header(self) -> None:
        self.auto_header = False
        console.print()
        if self.bg_finished:
            console.print("[cyan]✻ Tugas background selesai — Claude menanggapi hasilnya[/] [dim](esc untuk menghentikan)[/]")
        elif self.goal:
            console.print("[cyan]✻ Claude melanjutkan goal secara otomatis[/] [dim](esc untuk menghentikan)[/]")
        else:
            console.print("[cyan]✻ Claude melanjutkan secara otomatis[/]")
        self.bg_finished = False

    def begin_auto_turn(self) -> None:
        """Giliran otomatis (dimulai CLI sendiri) baru saja mulai: status per giliran dari nol."""
        self.auto_start = time.monotonic()
        self.auto_header = not self.goal_late  # jawaban /goal yang terlambat bukan giliran baru
        self.auto_interrupted = False
        self.printed_text = False
        self.turn_checks = 0
        self.turn_capped = False
        self.goal_note = ""
        if self.goal:  # giliran otomatis sedang jalan -> goal tidak lagi "menunggu user"
            self.goal.paused, self.goal.pause_cause = False, ""

    # ---------- pembaca pesan (jalan terus selama sesi) ----------
    def classify(self, msg: Any) -> None:
        """Catat giliran siapa yang sedang jalan / selesai, sebelum pesannya ditampilkan."""
        if isinstance(msg, SystemMessage) and not isinstance(msg, TASK_EVENTS) and msg.subtype == "init":
            if self.turn_future is None and not self.cli_busy:  # giliran otomatis, bukan prompt kita
                self.begin_auto_turn()
            self.cli_busy = True
        elif isinstance(msg, UserMessage) and not msg.parent_tool_use_id and isinstance(msg.content, str):
            origin = getattr(msg, "origin", None)
            if self.turn_future is not None and is_ours(origin):
                self.echo_seen = True  # prompt kita sudah mulai diproses
                if self.goal and self.goal.paused and not self.quiet_turn:
                    self.goal.paused, self.goal.pause_cause = False, ""  # pesan user = melanjutkan goal yang dijeda
            elif self.turn_future is not None and self.quiet_turn and not self.auto_during_quiet:
                # Giliran otomatis (notifikasi tugas) ternyata mulai tepat saat cek status goal dikirim:
                # tampilkan seperti giliran otomatis biasa; jawaban /goal datang setelahnya.
                self.auto_during_quiet = True
                self.begin_auto_turn()
        elif isinstance(msg, ResultMessage):
            fut = self.turn_future
            ours = fut is not None and not fut.done() and (is_ours(msg.origin) or self.echo_seen or self.interrupted)
            words = self.turn_prompt.split()
            goal_local = words[:1] == ["/goal"] and (len(words) == 1 or (len(words) == 2 and words[1].lower() in GOAL_CLEAR_WORDS))
            if ours and self.goal_late and msg.num_turns == 0 and not self.echo_seen and not goal_local:
                ours = False  # jawaban "/goal" yang terlambat, bukan hasil prompt user yang sedang ditunggu
            self.result_ours = bool(ours)

    async def dispatch(self, msg: Any) -> None:
        self.classify(msg)
        if self.prompt.active():  # user sedang di prompt: cetak di atas prompt tanpa merusak ketikan
            with console.capture() as cap:
                self.safe_render(msg)
            out = cap.get()
            if out:
                await self.prompt.run_above(lambda: write_raw(out))
        else:
            self.safe_render(msg)
        if isinstance(msg, ResultMessage):
            self.cli_busy = False
            fut = self.turn_future
            if fut is not None and not fut.done():
                if self.result_ours and self.sent_pending:  # pesan susulan belum dibaca: giliran berlanjut
                    self.continue_turn()
                elif self.result_ours:
                    fut.set_result(msg)
                else:  # pengaman: prompt kita ternyata tidak pernah diproses
                    asyncio.get_running_loop().call_later(15, self._stale_check, fut)
            if not self.result_ours and self.client:
                asyncio.ensure_future(self.refresh_context(self.client, warn=False))

    def _stale_check(self, fut: asyncio.Future) -> None:
        if not fut.done() and not self.cli_busy:
            fut.set_result(None)

    def safe_render(self, msg: Any) -> None:
        try:
            self.render(msg)
        except WrongAuthSource:
            raise
        except Exception as e:  # bug tampilan jangan sampai memutus sesi
            console.print(Text(f"⚠ Gagal menampilkan {type(msg).__name__}: {e}", style="dim"))

    def on_pump_error(self, err: BaseException) -> None:
        self.pump_error = err
        self.cli_busy = False
        fut = self.turn_future
        if fut is not None and not fut.done():
            fut.set_exception(err)
        else:
            self.prompt.abort(err)

    def on_init(self, data: dict[str, Any]) -> None:
        source = data.get("apiKeySource", "?")
        if source != "ANTHROPIC_API_KEY":
            raise WrongAuthSource(source)
        self.auth_source = source
        self.cli_version = data.get("claude_code_version", self.cli_version)
        self.session_id = data.get("session_id") or self.session_id
        for c in data.get("slash_commands", []) or []:
            self.prompt.commands.setdefault("/" + str(c).lstrip("/"), "")
        if self.header_shown:
            return
        self.header_shown = True
        console.print(
            f"[dim]✓ Terhubung · model [bold]{data.get('model', '?')}[/bold] · "
            f"mode {data.get('permissionMode', '?')} · auth: {source} · "
            f"{len(data.get('tools', []))} tool tersedia[/]"
        )
        tools = data.get("tools") or []
        if "PowerShell" in tools and "Bash" not in tools:  # Windows tanpa Git Bash
            console.print("[dim]  Command dijalankan lewat PowerShell (Git Bash tidak ditemukan · "
                          "pasang Git for Windows untuk memakai Bash: winget install -e --id Git.Git)[/]")

    def on_result(self, msg: ResultMessage) -> None:
        self.spin_stop()
        self.session_id = msg.session_id or self.session_id
        self.failures = 0
        # total_cost_usd kumulatif per percakapan: saat percakapan dilanjutkan (--resume, -c, /resume, sambung ulang),
        # mesin memulihkan biaya lamanya (lastCost). Hasil pertama proses seperti itu selalu cek /goal lokal tanpa
        # panggilan API (num_turns 0), jadi angkanya = biaya yang dipulihkan -> titik nol, bukan pengeluaran baru.
        total = msg.total_cost_usd or 0.0
        if not self.cost_seen:
            self.cost_seen = True
            if msg.num_turns == 0 and total > 0:
                self.cost_offset = total
        spent = max(total - self.cost_offset, 0.0)
        turn_cost = max(spent - self.cost_proc, 0.0)
        self.cost_proc = max(spent, self.cost_proc)

        if self.result_ours:
            self.last_result = msg
            self.goal_cmd = self.goal_why = None  # jawaban /goal selalu datang di giliran kita sendiri
        self.goal_note = ""
        g = self.goal

        if msg.stop_reason == "refusal":
            console.print("[yellow]⚠ Claude menolak melanjutkan permintaan ini.[/]")
        usage = msg.usage or {}
        tokens = f" · ↓ {fmt_tokens(usage['output_tokens'])} token" if usage.get("output_tokens") else ""
        checks = f" · 🎯 {self.turn_checks} cek" if self.turn_checks else ""
        stats = (f"{msg.num_turns} langkah · {msg.duration_ms / 1000:.1f} detik{tokens}{checks} · "
                 f"biaya: ${turn_cost:.4f} · total sesi: ${self.cost_total:.4f}")
        # Jawaban perintah lokal Claude Code (/goal, /compact, ...): 0 langkah, tanpa panggilan API.
        local = msg.num_turns == 0 and msg.subtype == "success" and not msg.is_error and not self.interrupted
        if local:
            self.goal_late = False
        if not self.result_ours:  # giliran otomatis (mis. menanggapi tugas background)
            if not self.printed_text and not msg.is_error and msg.result and msg.result.strip():
                self.show_text(msg.result)
            self.printed_text = False
            if local:
                self.auto_interrupted = False
                return
            if self.auto_interrupted:
                head = "[yellow]⏹ Respons otomatis dihentikan[/]"
            elif msg.is_error or msg.subtype != "success":
                head = f"[red]✗ Respons otomatis berhenti ({msg.subtype})[/]"
            else:
                head = "[green]✓ Respons otomatis selesai[/]"
            console.print(f"{head}[dim]  ·  {stats}[/]")
            if g:  # tidak bisa tanya Claude Code dari sini (jalur pembaca pesan) -> simpulkan dari alurnya
                if self.auto_interrupted or msg.is_error or msg.subtype != "success":
                    g.paused, g.pause_cause = True, ("dihentikan user" if self.auto_interrupted else "error")
                    if not self.auto_interrupted:
                        self.goal_auto_err = msg.subtype  # Claude Code mungkin menghapus goal-nya -> dicek sebelum prompt berikutnya
                    console.print(f"[yellow]⏸ Goal dijeda · {g.pause_cause} · kirim pesan untuk melanjutkan, "
                                  "/goal clear untuk membatalkan[/]")
                elif self.turn_capped or self.running_bg():
                    pass  # batas cek sudah dijelaskan / penilaian ditunda selama ada tugas background
                else:
                    self.goal_finish(inferred=True)
            self.auto_interrupted = False
            return
        if local:
            if not self.printed_text and msg.result and msg.result.strip():
                self.show_text(msg.result)
            if turn_cost > 0 or msg.duration_ms >= 1000:  # mis. /compact: ada biaya/waktu -> tetap tampilkan
                console.print(f"[green]✓ Selesai[/][dim]  ·  {stats}[/]")
            return  # jawaban seketika (/goal status, dll): tanpa "✓ Selesai · 0 langkah"
        if self.interrupted and self.perm_unanswerable:
            console.print("[yellow]⏹ Giliran dihentikan: ada izin yang tidak bisa ditanyakan (tanpa terminal)[/]", end="")
        elif self.interrupted and self.sent_pending:  # pesan susulan menunggu: Claude Code lanjut ke pesan itu
            console.print("[yellow]⏹ Dihentikan oleh user[/] [dim]· lanjut ke pesan susulan[/]", end="")
        elif self.interrupted:
            console.print("[yellow]⏹ Dihentikan oleh user[/] [dim]· ketik instruksi baru, atau 'lanjutkan'[/]", end="")
        elif msg.subtype == "error_max_budget_usd":
            console.print(f"[red]✗ Berhenti: batas budget ${self.args.budget} tercapai.[/]")
        elif msg.is_error or msg.subtype != "success":
            console.print(f"[red]✗ Berhenti ({msg.subtype})[/]")
            if msg.result:
                console.print(f"[red]{clip(msg.result, 500)}[/]")
        elif g and self.turn_capped:
            console.print("[yellow]⏹ Giliran diakhiri paksa — goal dijeda[/]", end="")
        else:
            # Perintah slash yang diteruskan ke Claude (mis. /compact) kadang cuma kirim hasil akhir.
            if not self.printed_text and msg.result and msg.result.strip():
                self.show_text(msg.result)
            console.print("[green]✓ Selesai[/]", end="")
        console.print(f"[dim]  ·  {stats}[/]")
        n = len(self.running_bg())
        if n:
            console.print(f"[yellow]⧗ {n} tugas background masih berjalan[/] [dim]— progresnya tampil live di bawah "
                          "prompt, detail: /tasks. Claude otomatis menanggapi begitu selesai"
                          + (" · penilaian goal ditunda sampai tugas selesai, lalu Claude lanjut otomatis" if g else "")
                          + ".[/]")

    # ---------- goal (/goal) ----------
    def goal_line(self, text: str, style: str = "cyan") -> None:
        """Satu baris status goal, aman dicetak saat spinner aktif (pola yang sama dengan print_bg)."""
        self.spin_stop()
        console.print(Text(text, style=style))
        self.spin_start(self.current_tool)

    def goal_cond(self, cond: str) -> str:
        return clip(oneline(cond), 160)

    def on_goal_reply(self, text: str) -> bool:
        """Terjemahkan jawaban lokal /goal dari Claude Code. Return False kalau teks ini bukan jawaban /goal."""
        cmd, why = self.goal_cmd, self.goal_why
        head = text.strip()
        g = self.goal
        if head.startswith(("Goal condition is limited", "/goal is only available", "/goal can't run")):
            if cmd is None:
                return False
            self.goal_cmd = self.goal_why = None  # kondisi > 4000 karakter, folder belum dipercaya, hooks dimatikan
            if cmd == "set":
                self.goal_refused = True
            self.goal_line(f"⚠ {'Goal tidak diset' if cmd == 'set' else '/goal ditolak'}: {clip(oneline(head), 400)}", "yellow")
            return True
        if cmd == "set":
            if not head.startswith("Goal set:"):
                return False  # teks lain (mis. jawaban giliran otomatis yang masih jalan): tampilkan biasa, tetap tunggu
            self.goal_cmd = self.goal_why = None
            cond = head[len("Goal set:"):].strip()
            self.goal = Goal(condition=cond, cost_at_set=self.cost_total)
            self.goal_line(f"🎯 Goal ditetapkan: {cond}", "bold cyan")
            if not self.goal_explained:
                self.goal_explained = True
                console.print(Text("   Claude langsung mengerjakannya. Tiap kali ia mau berhenti, pemeriksa (model kecil, kena "
                                   "biaya per cek) menilai kondisinya — juga setelah pesan-pesanmu berikutnya. "
                                   "Esc = jeda · /goal = status · /goal clear = batal.", style="dim"))
                console.print(Text("   Pemeriksa cuma membaca percakapan: tulis kondisi yang bisa dibuktikan dari output Claude "
                                   "(mis. `pytest` exit 0, `git status` bersih) dan batasi, mis. \"atau berhenti setelah "
                                   "20 giliran\" — tidak ada batas giliran bawaan.", style="dim"))
            return True
        if head.startswith("Goal active:"):
            self.goal_cmd = self.goal_why = None
            cond, turns, reason = parse_goal_active(head)
            fresh = False
            if g is None or not same_goal(g.condition, cond):  # Claude Code = sumber kebenaran
                lg = self.last_goal
                if lg and same_goal(lg.condition, cond):  # tadi dianggap selesai/dibuang -> hidupkan lagi, hitungan tetap
                    g, self.goal, self.last_goal = lg, lg, None
                    g.ended_at = g.ended_mono = g.cost_at_end = 0.0
                else:
                    g = self.goal = Goal(condition=cond, cost_at_set=self.cost_total)
                    fresh = True
            if len(cond) > len(g.condition):
                g.condition = cond  # versi lengkap (yang lokal mungkin terpotong)
            g.cli_turns = turns
            if reason:
                g.last_reason = reason
            last = clip(oneline(g.last_reason), 200) if g.last_reason else "belum dinilai"
            if why is None:  # diketik user: /goal
                self.goal_line(f"🎯 Goal aktif: {g.condition}", "bold cyan")
                bits = [f"berjalan {fmt_dur(time.monotonic() - g.set_at)}", f"dicek {g.checks}x",
                        f"cek terakhir: {last}", f"biaya sejak diset ${max(self.cost_total - g.cost_at_set, 0.0):.4f}"]
                if turns is not None and turns != g.checks:
                    bits.append(f"(Claude Code: {turns} giliran dinilai)")
                if g.paused:
                    bits.append(f"⏸ dijeda ({g.pause_cause})")
                if fresh:
                    bits.append("(baru tercatat di sini: hitungan cek & durasi mulai dari nol)")
                console.print(Text("   " + " · ".join(bits), style="dim"))
            elif why == "auto_error":
                pass  # goal selamat dari error giliran otomatis; pesan user yang barusan melanjutkannya
            elif why in ("after_turn", "print"):
                g.paused, g.pause_cause = True, "pemeriksa tidak menilai"
                self.goal_line("⏸ Goal masih aktif: giliran berakhir tanpa keputusan pemeriksa (pemeriksa gagal/timeout?) "
                               f"· cek terakhir: {last} · kirim pesan untuk melanjutkan, /goal clear untuk membatalkan", "yellow")
            elif why == "after_error":
                g.paused, g.pause_cause = True, "error"
                self.goal_line("⏸ Goal dijeda · giliran berakhir karena error · kirim pesan untuk melanjutkan, "
                               "/goal clear untuk membatalkan", "yellow")
            elif why == "startup":
                self.goal_line(f"🎯 Goal aktif dipulihkan dari percakapan ini: {self.goal_cond(g.condition)} "
                               "(hitungan cek & durasi mulai dari nol)", "cyan")
            elif why == "recovered":
                self.goal_line(f"🎯 Goal masih aktif setelah sambung ulang: {self.goal_cond(g.condition)} "
                               "· kirim pesan untuk melanjutkan", "cyan")
            return True
        if head.startswith("Goal cleared:"):  # konfirmasi pembatalan, apa pun yang tercatat di sini
            self.goal_cmd = self.goal_why = None
            cond = head[len("Goal cleared:"):].strip()
            if g:
                g.end(self.cost_total)
                self.last_goal, self.goal = g, None
            self.goal_line(f"🎯 Goal dibatalkan: {self.goal_cond(cond)}", "cyan")
            return True
        if head.startswith("No goal set"):
            self.goal_cmd = self.goal_why = None
            stale = ""
            if g and (cmd == "clear" or why is None):  # Claude Code bilang tidak ada goal -> status lokal yang tersisa dibuang
                g.end(self.cost_total)
                self.last_goal, self.goal = g, None
                stale = " (goal yang masih tercatat di sini ternyata sudah tidak aktif di Claude Code)"
            if cmd == "clear":
                self.goal_line("Tidak ada goal aktif." + stale, "dim")
            elif why is None:  # diketik user: /goal
                lg = self.last_goal
                last = (f" Goal terakhir: {self.goal_cond(lg.condition)} · berakhir {ago(lg.ended_at)} · "
                        f"{lg.stats(self.cost_total)}." if lg else "")
                console.print(Text(f"Belum ada goal aktif.{stale}{last} Pakai: /goal <kondisi>", style="dim"))
            elif why in ("after_turn", "print"):
                if g:
                    self.goal_finish(inferred=False)
            elif why in ("after_error", "auto_error"):
                if g:
                    g.end(self.cost_total)
                    self.last_goal, self.goal = g, None
                    self.goal_failed = True
                    self.goal_line(f"✗ Goal dihapus otomatis oleh Claude Code setelah error ({self.goal_err or 'error'}): "
                                   f"{self.goal_cond(g.condition)} · jalankan /goal lagi untuk melanjutkan", "red")
            elif why == "recovered":
                if g:
                    self.goal = None
                    self.goal_line(f"🎯 Goal hilang setelah sambung ulang: {self.goal_cond(g.condition)} "
                                   "· jalankan /goal lagi kalau masih perlu", "yellow")
            # why == "startup": tidak ada goal yang dipulihkan -> diam
            return True
        return False  # teks lain (mis. jawaban giliran otomatis yang masih jalan): tampilkan biasa, tetap tunggu jawaban /goal

    def goal_finish(self, inferred: bool) -> None:
        """Goal sudah tidak aktif lagi di Claude Code setelah giliran berjalan normal: tercapai atau dinilai mustahil."""
        g = self.goal
        if g is None:
            return
        g.end(self.cost_total)
        self.last_goal, self.goal = g, None
        self.goal_line(f"🎯 Goal berakhir: {self.goal_cond(g.condition)} · {g.stats(self.cost_total)}", "bold cyan")
        console.print(Text("   pemeriksa menilai kondisinya terpenuhi — atau mustahil dicapai; lihat jawaban terakhir Claude di atas."
                           + (" (disimpulkan: giliran otomatis berakhir tanpa penolakan pemeriksa — ketik /goal untuk memastikan)"
                              if inferred else ""), style="dim"))

    def on_stop_feedback(self, text: str) -> None:
        """'Stop hook feedback:\\n[<kondisi>]: <alasan>' = pemeriksa goal menolak; Claude lanjut di giliran yang sama."""
        body = text[len("Stop hook feedback:"):].strip()
        self.goal_note = ""
        g = self.goal
        flat = oneline(body)
        reason = None
        if g:  # cocokkan dulu dengan kondisi yang diketahui (kondisi bisa mengandung "]:" / spasi berubah)
            prefix = "[" + oneline(g.condition) + "]:"
            if flat.startswith(prefix):
                reason = flat[len(prefix):].strip()
        if reason is None:
            m = re.match(r"\[(.*?)\]:\s*(.*)", body, re.S)  # bentuk berkurung: pemeriksa /goal (atau Stop hook command user)
            bracket, rest = (m.group(1).strip(), m.group(2).strip()) if m else (None, "")
            if bracket is not None and g and same_goal(g.condition, bracket):
                reason = rest  # kondisi panjang dipotong Claude Code jadi 500 karakter + "…"
            elif bracket is not None and g is None and self.last_goal and same_goal(self.last_goal.condition, bracket):
                g = self.goal = self.last_goal  # tadi dianggap selesai -> ternyata masih dinilai: hidupkan lagi
                self.last_goal = None
                g.ended_at = g.ended_mono = g.cost_at_end = 0.0
                reason = rest
                self.goal_line(f"🎯 Goal masih aktif di Claude Code: {self.goal_cond(g.condition)}", "cyan")
            else:  # tanpa kurung, atau kurung yang bukan goal kita (mis. "[npm run lint]: ..." dari Stop hook user)
                self.goal_line(f"⚑ Umpan balik Stop hook: {clip(flat, 300)}", "yellow")
                if bracket is not None:
                    self.goal_dirty = True  # bisa jadi goal yang tidak tercatat di sini -> cek ke Claude Code setelah giliran
                return
        g.checks += 1
        self.turn_checks += 1
        g.last_reason = reason or ""
        g.paused, g.pause_cause = False, ""
        self.goal_line(f"🎯 Cek goal #{g.checks} · belum terpenuhi · {clip(oneline(reason or '(tanpa alasan)'), 200)}", "cyan")

    def on_notification(self, data: dict[str, Any]) -> None:
        """Pemberitahuan dari Claude Code (mis. batas Stop hook / goal)."""
        text = str(data.get("text") or data.get("content") or "").strip()
        if data.get("key") == "stop-hook-block-cap":
            m = re.search(r"(\d+) consecutive", text)
            n = f"{m.group(1)}x" if m else "berkali-kali"
            g = self.goal
            self.turn_capped = True
            if g:
                g.paused, g.pause_cause = True, "cap"
                self.goal_note = ""
                self.goal_line(f"⏸ Goal dijeda: {n} berturut-turut Claude dinilai belum memenuhi goal tanpa memakai tool. "
                               "Biasanya kondisinya tidak bisa dibuktikan dari percakapan atau butuh input darimu. "
                               "Kirim pesan untuk melanjutkan, /goal clear untuk membatalkan "
                               "(batas: CLAUDE_CODE_STOP_HOOK_BLOCK_CAP).", "yellow")
            else:
                self.goal_line(f"⚠ {text}", "yellow")
            return
        if text:
            self.goal_line(text, "yellow" if data.get("color") == "warning" else "dim")

    async def refresh_context(self, client: ClaudeSDKClient, warn: bool = True) -> None:
        try:
            usage = await asyncio.wait_for(client.get_context_usage(), 5)
            self.ctx_pct = float(usage.get("percentage", 0))
        except Exception:
            return
        if warn and self.ctx_pct >= 80:
            await self.say(f"[yellow]⚠ Konteks sudah {self.ctx_pct:.0f}% terpakai. Ketik /compact untuk meringkas.[/]")

    # ---------- izin tool ----------
    @staticmethod
    def describe_suggestions(suggestions: list[PermissionUpdate]) -> tuple[str, str]:
        """Ubah saran izin dari Claude Code jadi teks: (aturan, tempat disimpan)."""
        where_map = {
            "localSettings": ".claude/settings.local.json",
            "projectSettings": ".claude/settings.json",
            "userSettings": "~/.claude/settings.json",
            "session": "sesi ini",
        }
        rules: list[str] = []
        where: set[str] = set()
        for s in suggestions or []:
            if s.type in ("addRules", "replaceRules") and s.rules and s.behavior in (None, "allow"):
                rules += [r.tool_name + (f"({r.rule_content})" if r.rule_content else "") for r in s.rules]
            elif s.type == "setMode" and s.mode:
                rules.append(f"mode {s.mode}")
            elif s.type == "addDirectories" and s.directories:
                rules.append("folder " + ", ".join(s.directories))
            else:
                continue
            if s.destination:
                where.add(where_map.get(s.destination, s.destination))
        return ", ".join(rules), ", ".join(sorted(where))

    async def can_use_tool(
        self, tool: str, inp: dict[str, Any], ctx: ToolPermissionContext
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool in self.session_allow:
            return PermissionResultAllow()

        if tool == "ExitPlanMode":
            inp = {**inp, "plan": await self.plan_text(inp)}

        def question() -> Any:
            if tool == "ExitPlanMode":
                return self.ask_plan(inp)
            return self.ask_tool(tool, inp, ctx)

        if self.prompt.active():  # diminta agent background / giliran otomatis saat user sedang di prompt
            return await self.prompt.run_above(question)
        self.spin_stop()
        self.keys.pause()
        # Selama giliran berjalan, Ctrl+C ditangani asyncio (tidak memutus input()). Saat bertanya izin,
        # Ctrl+C harus langsung membatalkan pertanyaan -> pasang handler bawaan sementara.
        try:
            old_sigint = signal.signal(signal.SIGINT, signal.default_int_handler)
        except ValueError:
            old_sigint = None
        try:
            return question()
        finally:
            if old_sigint is not None:
                with contextlib.suppress(ValueError):
                    signal.signal(signal.SIGINT, old_sigint)
            self.keys.resume()
            self.spin_start(self.current_tool)

    async def plan_text(self, inp: dict[str, Any]) -> str:
        """Isi rencana untuk persetujuan ExitPlanMode. Claude Code versi baru menulis rencananya ke file rencana
        (~/.claude/plans/…) lalu memanggil ExitPlanMode tanpa argumen; isinya diminta lewat control request
        "get_plan" (belum ada method-nya di SDK), dengan cadangan membaca file rencana yang terakhir ditulis."""
        plan = str(inp.get("plan") or "").strip()
        if plan:
            return plan
        query = getattr(self.client, "_query", None)
        if query is not None and hasattr(query, "_send_control_request"):
            with contextlib.suppress(Exception):
                r = await asyncio.wait_for(query._send_control_request({"subtype": "get_plan"}), 5)
                if isinstance(r, dict) and r.get("exists") and str(r.get("content") or "").strip():
                    return str(r["content"]).strip()
        if self.plan_file:
            with contextlib.suppress(OSError):
                return Path(self.plan_file).read_text(encoding="utf-8", errors="replace").strip()
        return ""

    def cancelled(self, what: str) -> PermissionResultDeny:
        """Ctrl+C / Ctrl+D di pertanyaan izin = tolak (saat giliran kita: sekalian hentikan Claude)."""
        if not is_terminal(sys.stdin):  # mis. CI / cron: tidak ada yang bisa menjawab pertanyaan izin
            self.perm_unanswerable = True
            console.print(f"[yellow]✗ {what} ditolak: tidak ada terminal untuk menjawab.[/] "
                          "[dim]Siapkan aturan izin di .claude/settings.json, atau pakai --yolo di sandbox.[/]")
            why = "Tidak ada user yang bisa menyetujui permintaan ini (berjalan tanpa terminal)."
        else:
            console.print(f"[yellow]✗ {what} dibatalkan (Ctrl+C)[/]")
            why = "User membatalkan permintaan ini (Ctrl+C)."
        if self.fg_active:
            self.interrupted = True
        return PermissionResultDeny(message=why, interrupt=self.fg_active)

    def permission_view(self, tool: str, inp: dict[str, Any], ctx: ToolPermissionContext) -> tuple[str, Any, list[Any], str, str]:
        """Isi pertanyaan izin: (judul, isi panel, saran izin dari Claude Code, aturan, tempat disimpan)."""
        summary, detail = self.describe_tool(tool, inp, full=True)
        head = Text.assemble((tool, "bold"))
        if summary:
            head.append(f"({summary})")
        body: list[Any] = [head] + ([detail] if detail is not None else [])
        if getattr(ctx, "decision_reason", None):
            body.append(Text(f"Alasan: {ctx.decision_reason}", style="dim"))
        if getattr(ctx, "blocked_path", None):
            body.append(Text(f"Di luar folder yang diizinkan: {ctx.blocked_path}", style="dim"))
        title = getattr(ctx, "title", None) or "Claude minta izin"
        agent = self.tasks.get(getattr(ctx, "agent_id", None) or "")
        if agent:  # permintaan dari sub-agent: sebutkan agent yang mana
            where = " (background)" if agent.background else ""
            title = f"Agent #{agent.num} “{clip(oneline(agent.desc), 40)}”{where} · {title}"
        suggestions = getattr(ctx, "suggestions", None) or []
        rules, where = self.describe_suggestions(suggestions)
        return title, Group(*body), suggestions, rules, where

    def ask_tool(self, tool: str, inp: dict[str, Any], ctx: ToolPermissionContext) -> Any:
        title, body, suggestions, rules, where = self.permission_view(tool, inp, ctx)
        console.print(Panel(body, title=f"🔐 {title}", title_align="left", border_style="yellow"))
        console.print("  [bold]1[/] Ya")
        if rules:
            console.print(f"  [bold]2[/] Ya, dan jangan tanya lagi untuk [bold]{rules}[/]"
                          + (f" [dim](disimpan di {where})[/]" if where else ""))
        else:
            console.print(f"  [bold]2[/] Ya, dan jangan tanya lagi untuk [bold]{tool}[/] [dim](sampai script ditutup)[/]")
        console.print("  [bold]3[/] Tidak, dan beri tahu Claude harus bagaimana")
        ans = ask("[yellow]Pilih[/] [dim]\\[1/2/3, Enter=1][/] › ")
        if ans == CANCEL:
            return self.cancelled(f"Izin {tool}")
        why = ""
        if ans not in ("", "1", "y", "ya", "yes", "2", "a", "always", "selalu"):
            why = ask("[dim]Kasih tahu Claude harus gimana (opsional, Enter untuk lewati):[/] ")
            ans, why = "no", ("" if why == CANCEL else why)
        return self.permission_answer(tool, ans, suggestions, rules, why)

    def permission_answer(self, tool: str, ans: str, suggestions: list[Any], rules: str, why: str = "") -> Any:
        """Jawaban izin -> hasil untuk Claude Code. ans: "1"/"yes" = ya, "2"/"always" = jangan tanya lagi, lainnya = tidak."""
        if ans in ("", "1", "y", "ya", "yes"):
            return PermissionResultAllow()
        if ans in ("2", "a", "always", "selalu"):
            if rules:
                console.print(f"[dim]✓ Aturan ditambahkan: {rules}[/]")
                for s in suggestions:  # saran bisa ikut mengganti mode (mis. acceptEdits) -> sinkronkan footer
                    if s.type == "setMode" and s.mode:
                        self.args.mode = s.mode
                return PermissionResultAllow(updated_permissions=suggestions)
            self.session_allow.add(tool)
            console.print(f"[dim]✓ {tool} diizinkan tanpa tanya sampai keluar dari script.[/]")
            return PermissionResultAllow()
        return PermissionResultDeny(message=why or f"User menolak penggunaan {tool}. Tanyakan alternatifnya.")

    def ask_plan(self, inp: dict[str, Any]) -> Any:
        console.print(Panel(Markdown(inp.get("plan", "(rencana kosong)")), title="📋 Rencana dari Claude",
                            title_align="left", border_style="cyan"))
        console.print("  [bold]1[/] Ya, mulai dan auto-terima edit")
        console.print("  [bold]2[/] Ya, tapi tanya dulu setiap edit")
        console.print("  [bold]3[/] Tidak, lanjut merencanakan")
        ans = ask("[yellow]Setujui rencana?[/] [dim]\\[1/2/3, Enter=1][/] › ")
        if ans == CANCEL:
            return self.cancelled("Persetujuan rencana")
        if ans in ("", "1", "y", "ya", "yes", "2"):
            return self.plan_answer(ans)
        why = ask("[dim]Apa yang perlu diubah dari rencananya?[/] ")
        return self.plan_answer("no", "" if why == CANCEL else why)

    def plan_answer(self, ans: str, why: str = "") -> Any:
        """Jawaban persetujuan rencana: "1" = mulai + auto-terima edit, "2" = mulai + tanya tiap edit, lainnya = tidak."""
        if ans in ("", "1", "y", "ya", "yes", "2"):
            mode = "default" if ans == "2" else "acceptEdits"
            self.args.mode = mode
            if self.client:  # cadangan kalau CLI tidak memproses updated_permissions
                client = self.client
                asyncio.get_running_loop().call_soon(
                    lambda: asyncio.ensure_future(client.set_permission_mode(mode))
                )
            return PermissionResultAllow(
                updated_permissions=[PermissionUpdate(type="setMode", mode=mode, destination="session")]
            )
        return PermissionResultDeny(message=why or "User belum setuju dengan rencana ini. Tanyakan apa yang perlu diubah.")

    # ---------- fitur input ala Claude Code ----------
    def run_shell(self, cmd: str) -> None:
        """'!command': jalankan langsung di folder repo, output-nya dikirim ke Claude di pesan berikutnya."""
        if not cmd:
            return
        console.print(Text.assemble(("! ", "bold magenta"), (cmd, "bold")))
        try:
            r = subprocess.run(shell_command(cmd), cwd=self.repo, capture_output=True, encoding="utf-8",
                               errors="replace", stdin=subprocess.DEVNULL, timeout=600)
            out, err, code = r.stdout, r.stderr, r.returncode
        except KeyboardInterrupt:
            console.print("[yellow]  ⎿ dibatalkan[/]")
            return
        except subprocess.TimeoutExpired:
            out, err, code = "", "timeout setelah 600 detik", -1
        combined = (out + ("\n" if out and err else "") + err).rstrip("\n")
        lines = combined.splitlines() or ["(tidak ada output)"]
        shown = "\n    ".join(clip(x, 200) for x in lines[:30])
        if len(lines) > 30:
            shown += f"\n    … +{len(lines) - 30} baris"
        console.print(Text(f"  ⎿ {shown}", style="red" if code else "dim"))
        if code:
            console.print(f"[dim]  exit code {code}[/]")
        if len(combined) > MAX_SHELL_CONTEXT:
            combined = "…(dipotong)…\n" + combined[-MAX_SHELL_CONTEXT:]
        self.pending_context.append(
            f"<bash-input>{cmd}</bash-input>\n<bash-output exit_code=\"{code}\">\n{combined}\n</bash-output>"
        )
        console.print("[dim]  (output akan ikut dikirim ke Claude bersama pesan berikutnya)[/]")

    def add_memory(self, note: str) -> None:
        """'# catatan': tambahkan ke CLAUDE.md di repo, seperti shortcut # di Claude Code."""
        path = self.repo / "CLAUDE.md"
        try:
            existing = path.read_text() if path.exists() else ""
            with path.open("a") as f:
                if not existing:
                    f.write("# CLAUDE.md\n\n")
                elif not existing.endswith("\n"):
                    f.write("\n")
                f.write(f"- {note}\n")
        except OSError as e:
            console.print(f"[red]✗ Gagal menulis CLAUDE.md: {e}[/]")
            return
        console.print("[green]✓ Disimpan ke memori proyek[/] [dim](CLAUDE.md)[/]")
        self.pending_context.append(f"(User menambahkan catatan ke CLAUDE.md, ikuti mulai sekarang: {note})")

    MENTION_RE = re.compile(r"(?<![\w`])@((?:[^\s`'\"]|\\ )+)")

    def expand_mentions(self, prompt: str) -> str:
        """'@path' -> isi file (atau daftar isi folder) dilampirkan ke pesan."""
        blocks = []
        seen = set()
        for m in self.MENTION_RE.finditer(prompt):
            raw = m.group(1).rstrip(".,;:!?)").replace("\\ ", " ")
            if raw in seen:
                continue
            seen.add(raw)
            p = self.abs_path(raw)
            try:
                if p.is_file():
                    data = p.read_bytes()[: MAX_MENTION_BYTES + 1]
                    if b"\0" in data[:8000]:
                        console.print(f"[dim]  ⎿ @{raw}: file biner, cuma path-nya yang disebut[/]")
                        continue
                    text = data[:MAX_MENTION_BYTES].decode("utf-8", "replace")
                    cut = "\n…(dipotong)…" if len(data) > MAX_MENTION_BYTES else ""
                    blocks.append(f'<file path="{raw}">\n{text}{cut}\n</file>')
                    console.print(f"[dim]  ⎿ Melampirkan @{raw} ({len(text.splitlines())} baris)[/]")
                elif p.is_dir():
                    names = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir()
                                   if x.name not in (".git", "node_modules", "__pycache__"))
                    blocks.append(f'<directory path="{raw}">\n' + "\n".join(names[:300]) + "\n</directory>")
                    console.print(f"[dim]  ⎿ Melampirkan isi folder @{raw} ({len(names)} item)[/]")
            except OSError:
                continue
        if not blocks:
            return prompt
        return (prompt + "\n\nFile/folder yang disebut user dengan @ (sudah dilampirkan, tidak perlu dibaca ulang):\n"
                + "\n".join(blocks))


# ---------- daftar & riwayat sesi lama ----------
def session_list(repo: Path, exclude: str | None = None) -> list[tuple[str, str]]:
    """Percakapan lama di folder ini: [(session id, keterangan satu baris)], terbaru dulu."""
    if list_sessions is None:
        console.print("[red]SDK terlalu lama untuk /resume. Jalankan: pip install -U claude-agent-sdk[/]")
        return []
    try:
        sessions = [s for s in list_sessions(directory=str(repo), limit=20) if s.session_id != exclude]
    except Exception as e:
        console.print(f"[red]Gagal membaca daftar sesi: {e}[/]")
        return []
    if not sessions:
        console.print("[dim]Belum ada percakapan lama di folder ini.[/]")
    out = []
    for s in sessions:
        title = oneline(s.custom_title or s.summary or s.first_prompt or "(tanpa judul)")
        branch = f"  ⎇ {s.git_branch}" if s.git_branch else ""
        out.append((s.session_id, f"{ago(s.last_modified)} · {clip(title, 70)}{branch}"))
    return out


def pick_session(repo: Path, exclude: str | None = None) -> str | None:
    sessions = session_list(repo, exclude)
    if not sessions:
        return None
    console.print("[bold]Percakapan lama di folder ini:[/]")
    for i, (_, label) in enumerate(sessions, 1):
        when, _, rest = label.partition(" · ")
        console.print(f"  [bold]{i:>2}[/] [dim]{when:>14}[/]  {rich_escape(rest)}")
    ans = ask("Pilih nomor [dim](Enter untuk batal)[/] › ")
    if ans.isdigit() and 1 <= int(ans) <= len(sessions):
        return sessions[int(ans) - 1][0]
    return None


def show_history(session_id: str, repo: Path, n: int = 6) -> None:
    if get_session_messages is None:
        return
    try:
        msgs = get_session_messages(session_id, directory=str(repo))
    except Exception:
        return
    rows = []
    for m in msgs:
        if m.parent_tool_use_id or m.type not in ("user", "assistant"):
            continue
        content = m.message.get("content") if isinstance(m.message, dict) else None
        if isinstance(content, list):
            content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        if (isinstance(content, str) and content.strip() and not content.lstrip().startswith(
                ("<", "Stop hook feedback:", "A session-scoped Stop hook is now active", "Goal check-in:"))):  # obrolan /goal dilewati
            rows.append((m.type, oneline(content)))
    if not rows:
        return
    console.print("[dim]─── percakapan sebelumnya ───[/]")
    for typ, text in rows[-n:]:
        if typ == "user":
            console.print(Text("› " + clip(text, 200), style="bold dim"))
        else:
            console.print(Text("  " + clip(text, 300), style="dim"))
    console.print("[dim]────────────────────────────[/]")


# ---------- loop utama ----------
async def pump(client: ClaudeSDKClient, ui: UI) -> None:
    """Satu-satunya pembaca pesan dari mesin Claude. Jalan terus selama sesi - juga saat user
    sedang mengetik di prompt - jadi progres agent/command background tetap tampil dan
    giliran otomatis (Claude menanggapi tugas yang selesai) tidak menumpuk di antrean."""
    err: BaseException
    try:
        async for msg in client.receive_messages():
            await ui.dispatch(msg)
        err = ClaudeSDKError("mesin Claude Code berhenti (koneksi tertutup)")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        err = e
    ui.on_pump_error(err)


def on_ctrl_c(loop: asyncio.AbstractEventLoop, callback: Any) -> Any:
    """Ctrl+C -> callback di event loop, tanpa memutus await yang sedang berjalan. Mengembalikan fungsi pelepasnya.
    Windows: event loop-nya tidak mendukung add_signal_handler, jadi lewat signal.signal + call_soon_threadsafe."""
    try:
        loop.add_signal_handler(signal.SIGINT, callback)
        return lambda: loop.remove_signal_handler(signal.SIGINT)
    except (NotImplementedError, RuntimeError, ValueError):
        pass
    try:
        old = signal.signal(signal.SIGINT, lambda *_: loop.call_soon_threadsafe(callback))
    except ValueError:  # bukan thread utama
        return lambda: None
    return lambda: signal.signal(signal.SIGINT, old)


async def run_turn(client: ClaudeSDKClient, ui: UI, prompt: str, label: str | None = None,
                   quiet: bool = False) -> None:
    """Kirim satu prompt dan tunggu hasilnya. quiet=True untuk perintah lokal cepat (cek status /goal).

    Dipanggil dari task giliran (mode interaktif, ui.turn_task) -> prompt tetap aktif: spinner tampil di
    toolbar dan Esc/Ctrl+C ditangani key binding prompt. Selain itu (-p, pipe, cek goal saat start):
    spinner Live + KeyWatcher + SIGINT seperti biasa."""
    loop = asyncio.get_running_loop()
    if ui.pump_error:
        raise ui.pump_error

    fut = loop.create_future()
    tui = ui.turn_task is not None or getattr(ui, "gui", False)  # GUI: Esc/Stop di browser, Ctrl+C menutup GUI
    release_ctrl_c = None if tui else on_ctrl_c(loop, ui.interrupt_turn)

    ui.begin_turn(label)
    ui.quiet_turn, ui.turn_prompt, ui.tui_turn = quiet, prompt, tui
    if quiet:
        ui.verb = "Mengecek status goal"
    ui.turn_future, ui.echo_seen, ui.fg_active = fut, False, True
    if not tui:
        ui.keys.start(loop, ui.interrupt_turn)
        ui.spin_start()
    try:
        await client.query(prompt)
        ui.cli_busy = True
        await fut  # diselesaikan oleh pump() saat hasil giliran kita datang
    finally:
        ui.fg_active = False
        ui.turn_future = None
        ui.tui_turn = False
        ui.spin_stop()
        ui.keys.stop()
        if release_ctrl_c is not None:
            release_ctrl_c()
    if not quiet:
        await ui.refresh_context(client)


async def turn_job(client: ClaudeSDKClient, ui: UI, to_send: str, label: str) -> None:
    """Giliran user di mode interaktif: jalan sebagai task supaya prompt tetap bisa dipakai (pesan susulan,
    antrean perintah). Error diteruskan ke loop prompt lewat prompt.abort."""
    try:
        await run_turn(client, ui, to_send, label)
        await goal_after_turn(client, ui)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # WrongAuthSource / mesin Claude mati -> loop utama yang menangani (recover)
        ui.prompt.abort(e)
    finally:
        ui.on_turn_finished()


async def goal_check(client: ClaudeSDKClient, ui: UI, why: str) -> None:
    """Tanya status goal ke Claude Code lewat perintah lokal "/goal" (tanpa panggilan API, hampir seketika).
    Jawabannya diterjemahkan oleh UI.on_goal_reply sesuai `why`. HANYA dipanggil dari loop prompt / jalur -p,
    tidak pernah dari pembaca pesan (pump), supaya tidak saling tunggu."""
    if ui.pump_error or ui.cli_busy:
        return
    ui.goal_cmd, ui.goal_why = "status", why
    ui.auto_during_quiet = False
    try:
        await asyncio.wait_for(run_turn(client, ui, "/goal", quiet=True), 20)
    except asyncio.TimeoutError:
        ui.goal_late = True  # jawabannya mungkin masih datang; on_goal_reply tetap mengenalinya
        if ui.auto_during_quiet or ui.cli_busy:
            console.print("[dim]Status goal belum bisa dicek: Claude Code sedang menjalankan giliran otomatis · "
                          "ketik /goal nanti untuk mengecek.[/]")
        else:
            console.print("[yellow]⚠ Status goal tidak bisa dicek (Claude Code tidak menjawab) · ketik /goal untuk mencoba lagi.[/]")
    finally:
        ui.goal_cmd = ui.goal_why = None


async def goal_after_turn(client: ClaudeSDKClient, ui: UI) -> None:
    """Setelah giliran user selesai dan ada goal aktif: pastikan statusnya ke Claude Code."""
    g, res = ui.goal, ui.last_result
    if res is None or res.num_turns == 0 or ui.cli_busy:
        return  # jawaban lokal (/goal, /compact) / giliran otomatis sudah mulai -> tidak perlu dicek
    if not g:
        if ui.goal_dirty and not ui.interrupted:  # umpan balik Stop hook berkurung yang tidak dikenal: goal siapa?
            ui.goal_dirty = False
            await goal_check(client, ui, "after_turn")
        return
    if ui.interrupted or res.terminal_reason in ("aborted_streaming", "aborted_tools"):
        g.paused, g.pause_cause = True, "dihentikan user"  # Esc / Ctrl+C: goal tetap aktif di Claude Code
        console.print("[yellow]⏸ Goal dijeda · dihentikan user · kirim pesan untuk melanjutkan, /goal clear untuk membatalkan[/]")
        return
    if ui.turn_capped or ui.running_bg():
        return  # batas cek sudah dijelaskan / penilaian ditunda selama ada tugas background
    failed = res.is_error or res.subtype != "success"
    ui.goal_err = res.subtype if failed else ""
    await goal_check(client, ui, "after_error" if failed else "after_turn")


async def wait_background(ui: UI) -> None:
    """Mode -p: tunggu tugas background (dan tanggapan otomatis Claude) selesai sebelum keluar."""
    if not ui.running_bg() and not ui.cli_busy:
        return
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    release_ctrl_c = on_ctrl_c(loop, stop.set)
    ui.begin_turn(None)
    ui.waiting_bg, ui.fg_active = True, True
    ui.keys.start(loop, stop.set)
    ui.spin_start()
    quiet_since: float | None = None
    try:
        while not stop.is_set() and not ui.pump_error:
            if ui.running_bg() or ui.cli_busy:
                quiet_since = None
            elif quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since > 2.5:  # beri waktu CLI memulai giliran tanggapan
                break
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), 0.25)
    finally:
        ui.fg_active = ui.waiting_bg = False
        ui.spin_stop()
        ui.keys.stop()
        release_ctrl_c()
    if stop.is_set() and ui.running_bg():
        console.print("[yellow]⏹ Berhenti menunggu tugas background.[/]")


def confirm_drop_tasks(ui: UI, action: str) -> bool:
    """Giliran yang sedang jalan / tugas background ikut mati kalau proses Claude ditutup (/exit, /clear, /resume)
    -> tanya dulu. GUI: browser sudah menanyakannya sebelum mengirim perintah."""
    if getattr(ui, "gui", False):
        return True
    n = len(ui.running_bg())
    if ui.busy():
        lead = "Claude masih bekerja" + (f" dan {n} tugas background berjalan" if n else "")
    elif n:
        lead = f"Masih ada {n} tugas background berjalan"
    else:
        return True
    ans = ask(f"[yellow]{lead}; {action} akan menghentikannya. Lanjut?[/] [dim]\\[y/N][/] › ")
    return ans in ("y", "ya", "yes")


def show_tasks(ui: UI, arg: str) -> None:
    """/tasks: daftar tugas background & agent, /tasks N: detail, /tasks log: on/off log di layar."""
    if arg == "log":
        ui.bg_log = not ui.bg_log
        console.print("[green]✓ Log aktivitas agent background di layar: " + ("nyala" if ui.bg_log else "mati")
                      + "[/] [dim](progres live di bawah prompt tetap tampil)[/]")
        return
    tasks = list(ui.tasks.values())
    if not tasks:
        console.print("[dim]Belum ada agent / tugas background di sesi ini. Contoh: minta Claude "
                      "\"jalankan test di background\" atau \"pakai agent background untuk …\".[/]")
        return
    if arg.lstrip("#").isdigit():
        t = next((x for x in tasks if x.num == int(arg.lstrip("#"))), None)
        if t is None:
            console.print(f"[red]Tugas #{arg.lstrip('#')} tidak ada.[/] Ketik /tasks untuk daftarnya.")
            return
        show_task_detail(t)
        return
    width = max(console.width - 1, 40)
    running = sum(1 for t in tasks if t.status == "running")
    console.print(f"[bold]Agent & tugas background[/] [dim]({running} berjalan, {len(tasks) - running} selesai)[/]")
    for t in tasks:
        line = ui.task_line(t, width)
        if not t.background:
            line.append(" · foreground", style="dim")
            line.truncate(width, overflow="ellipsis")
        console.print(line)
    console.print("[dim]/tasks <no> detail, log & output · /stop <no> hentikan · /tasks log on/off log di layar[/]")


def show_task_detail(t: BgTask) -> None:
    icon, style, word = STATUS_VIEW.get(t.status, ("•", "dim", t.status))
    head = Text.assemble((f"#{t.num} ", "bold"), (f"{t.label} ", "cyan"), (t.desc or "(tanpa deskripsi)", "bold"))
    if t.agent_type:
        head.append(f" ({t.agent_type})", style="dim")
    head.append(" · ")
    head.append(f"{icon} {word}", style=style)
    head.append(" · " + " · ".join(t.stats()) + (" · background" if t.background else " · foreground"), style="dim")
    console.print(head)
    if t.prompt:
        console.print(Padding(Text("Tugas: " + clip(oneline(t.prompt), 500), style="dim"), (0, 0, 0, 2)))
    if t.last_tool:
        console.print(Padding(Text(f"Tool terakhir: {t.last_tool}", style="dim"), (0, 0, 0, 2)))
    if t.log:
        console.print("  [bold]Aktivitas[/] [dim](terbaru di bawah)[/]")
        for ts, entry in list(t.log)[-20:]:
            console.print(Padding(Text(f"{time.strftime('%H:%M:%S', time.localtime(ts))}  {clip(entry, 220)}",
                                       style="dim"), (0, 0, 0, 4)))
    report = ""
    if t.kind == "agent":
        report = agent_report(t.output_file) if t.output_file and t.status != "running" else ""
        if report:
            console.print("  [bold]Laporan agent[/]")
            console.print(Padding(Markdown(clip(report, 4000)), (0, 0, 0, 4)))
    elif t.output_file:
        out = tail_lines(t.output_file, 20)
        console.print("  [bold]Output terakhir[/]")
        for line in out or ["(belum ada output)"]:
            console.print(Padding(Text(clip(line, 220), style="dim"), (0, 0, 0, 4)))
        console.print(Padding(Text(f"file lengkap: {t.output_file}", style="dim"), (0, 0, 0, 2)))
    if t.summary and t.summary != t.desc and not report:
        console.print(Padding(Text("Ringkasan: " + clip(oneline(t.summary), 400), style="dim"), (0, 0, 0, 2)))
    if t.status == "running" and t.detached:
        console.print(f"[dim]  /stop {t.num} untuk menghentikan[/]")


def stop_targets(ui: UI, arg: str) -> list[BgTask]:
    """Tugas background mana yang dimaksud /stop (cetak daftar / kesalahan kalau belum jelas)."""
    running = ui.running_bg()
    if not running:
        console.print("[dim]Tidak ada tugas background yang sedang berjalan.[/]")
        return []
    num = arg.lstrip("#")
    if arg == "all":
        return running
    if num.isdigit():
        targets = [t for t in running if t.num == int(num)]
        if not targets:
            console.print(f"[red]Tugas #{num} tidak sedang berjalan.[/] Ketik /tasks untuk daftarnya.")
        return targets
    if not arg and len(running) == 1:
        return running
    console.print("Tugas background yang berjalan:")
    for t in running:
        console.print(ui.task_line(t, max(console.width - 1, 40)))
    console.print("[dim]Ketik /stop <no> atau /stop all[/]")
    return []


async def stop_bg(client: ClaudeSDKClient, ui: UI, targets: list[BgTask]) -> None:
    for t in targets:
        try:
            await client.stop_task(t.id)
        except Exception as e:
            ui.note(f"[red]✗ Gagal menghentikan #{t.num}: {e}[/]")


async def stop_tasks(client: ClaudeSDKClient, ui: UI, arg: str) -> None:
    targets = stop_targets(ui, arg)
    for t in targets:
        console.print(f"[yellow]⏹ Menghentikan #{t.num} {clip(oneline(t.desc), 60)}…[/]")
    await stop_bg(client, ui, targets)


async def show_context(client: ClaudeSDKClient) -> None:
    try:
        u = await asyncio.wait_for(client.get_context_usage(), 15)
    except Exception as e:
        console.print(f"[red]Gagal membaca pemakaian konteks: {e}[/]")
        return
    pct = float(u.get("percentage", 0))
    filled = int(round(pct / 100 * 30))
    bar = Text("█" * filled, style="red" if pct >= 80 else "yellow" if pct >= 50 else "green")
    bar.append("░" * (30 - filled), style="dim")
    console.print(Text.assemble(("Konteks ", "bold"), bar,
                                f"  {u.get('totalTokens', 0):,} / {u.get('maxTokens', 0):,} token ({pct:.0f}%)"))
    total = max(u.get("maxTokens", 0), 1)
    for c in sorted(u.get("categories", []), key=lambda c: -c.get("tokens", 0)):
        if c.get("tokens"):
            console.print(f"  [dim]●[/] {c['name']:<28} {c['tokens']:>9,}  [dim]{c['tokens'] / total * 100:4.1f}%[/]")
    if u.get("isAutoCompactEnabled"):
        console.print("[dim]Auto-compact aktif. Ketik /compact untuk meringkas sekarang.[/]")


def settings_rules(repo: Path) -> list[str]:
    rules = []
    for f in (repo / ".claude" / "settings.local.json", repo / ".claude" / "settings.json"):
        try:
            data = json.loads(f.read_text())
            rules += [f"{r} [dim]({f.name})[/]" for r in data.get("permissions", {}).get("allow", [])]
        except (OSError, ValueError, AttributeError):
            continue
    return rules


async def handle_command(cmd: str, client: ClaudeSDKClient, ui: UI) -> Any:
    """Return None (selesai), "exit", "clear", "forward" (kirim ke Claude), atau ("resume", id)."""
    name, _, arg = cmd.partition(" ")
    arg = arg.strip()
    args = ui.args
    if name in ("/exit", "/quit"):
        return "exit" if confirm_drop_tasks(ui, "keluar") else None
    if name == "/clear":
        return "clear" if confirm_drop_tasks(ui, "/clear") else None
    if name == "/tasks":
        show_tasks(ui, arg)
        return None
    if name in ("/stop", "/kill"):
        await stop_tasks(client, ui, arg)
        return None
    if name == "/help":
        console.print("[bold]Perintah:[/]")
        for c, desc in LOCAL_COMMANDS.items():
            console.print(f"  [cyan]{c:<10}[/] {desc}")
        forwarded = sorted(c for c in ui.prompt.commands if c not in LOCAL_COMMANDS)
        if forwarded:
            console.print("[bold]Perintah Claude Code / proyek[/] [dim](diteruskan ke Claude)[/]:")
            console.print("  " + "  ".join(f"[cyan]{c}[/]" for c in forwarded))
        console.print(GUI_SHORTCUTS_TEXT if getattr(ui, "gui", False) else SHORTCUTS_TEXT)
    elif name == "/status":
        console.print(
            f"  📂 Folder       {ui.repo}\n"
            f"  🤖 Model        {args.model}\n"
            f"  🔐 Mode         {args.mode}\n"
            f"  🔑 Auth         {ui.auth_source}\n"
            f"  🧾 Session      {ui.session_id or '(belum ada)'}\n"
            f"  ⚙️  Claude Code  {ui.cli_version or '(muncul setelah pesan pertama)'}\n"
            f"  ⧗ Background   {len(ui.running_bg())} berjalan · {len(ui.tasks)} total di sesi ini (/tasks)\n"
            f"  🎯 Goal         {goal_status_row(ui)}\n"
            f"  💰 Biaya        ${ui.cost_total:.4f}" + (f" / budget ${args.budget}" if args.budget else "")
        )
    elif name == "/cost":
        console.print(f"Total biaya sesi ini: [bold]${ui.cost_total:.4f}[/]"
                      + (f" [dim](budget ${args.budget})[/]" if args.budget else ""))
    elif name == "/context":
        await show_context(client)
    elif name == "/model":
        if not arg:
            console.print(f"Model sekarang: [bold]{args.model}[/]")
            console.print("[dim]Pilihan: " + ", ".join(f"{k} ({v})" for k, v in MODEL_ALIASES.items()) + "[/]")
        else:
            model = MODEL_ALIASES.get(arg.lower(), arg)
            await client.set_model(model)
            args.model = model
            console.print(f"[green]✓ Model diganti ke {model}[/]")
    elif name == "/mode":
        if arg not in MODES:
            console.print(f"Mode sekarang: [bold]{args.mode}[/]. Pilihan: {', '.join(MODES)}")
        else:
            await client.set_permission_mode(arg)
            args.mode = arg
            console.print(f"[green]✓ Mode izin diganti ke {arg}[/]")
    elif name == "/allow":
        if arg == "reset":
            ui.session_allow.clear()
            console.print("[green]✓ Izin sesi dihapus[/] [dim](aturan di .claude/settings*.json tidak diubah)[/]")
        else:
            console.print(f"[bold]Otomatis:[/] {', '.join(AUTO_TOOLS)}")
            console.print(f"[bold]Izin sesi:[/] {', '.join(sorted(ui.session_allow)) or '(belum ada)'}")
            rules = settings_rules(ui.repo)
            console.print("[bold]Aturan tersimpan:[/] " + ("\n  " + "\n  ".join(rules) if rules else "(belum ada)"))
    elif name == "/resume":
        if getattr(ui, "gui", False):
            sid = await ui.pick_session(exclude=ui.session_id)
        else:
            sid = pick_session(ui.repo, exclude=ui.session_id)
        if sid and confirm_drop_tasks(ui, "pindah percakapan"):
            return ("resume", sid)
    elif name == "/rewind":
        if not ui.checkpoints:
            console.print("[dim]Belum ada titik rewind di percakapan ini.[/]")
            return None
        recent = ui.checkpoints[-10:]
        if getattr(ui, "gui", False):
            pick = await ui.choose("Kembalikan file ke kondisi sebelum prompt:",
                                   [clip(oneline(label), 90) for _, label in reversed(recent)])
            ans = str(pick + 1) if pick is not None else ""
        else:
            console.print("[bold]Kembalikan file ke kondisi sebelum prompt:[/]")
            for i, (_, label) in enumerate(reversed(recent), 1):
                console.print(f"  [bold]{i:>2}[/] {clip(oneline(label), 90)}")
            ans = ask("Pilih nomor [dim](Enter untuk batal)[/] › ")
        if not (ans.isdigit() and 1 <= int(ans) <= len(recent)):
            return None
        idx = len(ui.checkpoints) - int(ans)
        uuid, label = ui.checkpoints[idx]
        try:
            await client.rewind_files(uuid)
        except Exception as e:
            console.print(f"[red]✗ Gagal rewind: {e}[/]")
            return None
        del ui.checkpoints[idx:]
        console.print(f"[green]✓ File dikembalikan ke kondisi sebelum:[/] {clip(oneline(label), 80)}")
        ui.pending_context.append(
            f'(Catatan: user memakai /rewind. Semua perubahan file sejak pesan "{clip(oneline(label), 120)}" '
            "sudah dibatalkan, jadi file kembali ke kondisi sebelum pesan itu.)"
        )
    elif name == "/goal":
        # Dikerjakan Claude Code sendiri; kita cuma menandai jawaban apa yang ditunggu lalu meneruskannya
        # lewat run_turn biasa (spinner, Esc, label /rewind ikut jalan). Jawabannya diterjemahkan di on_goal_reply.
        word = arg.lower()
        if not arg:
            ui.goal_cmd, ui.goal_why = "status", None
        elif word in GOAL_CLEAR_WORDS:
            ui.goal_cmd, ui.goal_why = "clear", None
            if ui.auto_running():  # Claude Code mengantre perintah sampai giliran yang sedang jalan selesai
                ui.interrupt_auto()
                console.print("[dim]⏹ Giliran otomatis dihentikan dulu supaya /goal clear tidak mengantre di belakangnya.[/]")
        else:
            if ui.goal:
                console.print(f"[yellow]🎯 Goal sebelumnya akan diganti:[/] {rich_escape(ui.goal_cond(ui.goal.condition))} "
                              f"[dim]({ui.goal.stats(ui.cost_total)})[/]")
            if args.mode == "plan":
                console.print("[yellow]⚠ Mode plan: Claude tidak bisa mengedit file, jadi goal ini mungkin tidak pernah "
                              "terpenuhi (pemeriksa akan menolak terus sampai batasnya).[/]")
            elif args.mode in ("default", "acceptEdits"):
                what = "edit file & command" if args.mode == "default" else "command (Bash dll.)"
                console.print(f"[yellow]⚠ Mode {args.mode}: {what} yang belum diizinkan tetap ditanya dulu, jadi goal bisa "
                              "berhenti menunggu jawabanmu — jawab 2 (jangan tanya lagi) atau pakai --yolo kalau mau "
                              "lepas tangan.[/]")
            ui.goal_cmd, ui.goal_why = "set", None
        return "forward"
    elif name in ui.prompt.commands or (ui.repo / ".claude" / "commands" / f"{name[1:]}.md").exists():
        return "forward"  # /compact, /init, /review, perintah custom dari .claude/commands, skill, dll
    else:
        console.print(f"[red]Perintah tidak dikenal: {name}[/]. Ketik /help")
    return None


def goal_status_row(ui: UI) -> str:
    g = ui.goal
    if not g:
        return "(tidak ada)"
    row = f"{rich_escape(clip(oneline(g.condition), 80))} · {g.checks} cek"
    if g.paused:
        row += f" · ⏸ dijeda ({g.pause_cause})"
    return row + " · detail: /goal"


async def load_commands(client: ClaudeSDKClient, ui: UI) -> None:
    """Ambil daftar slash command dari Claude Code (bawaan + .claude/commands + skill) untuk Tab & /help."""
    try:
        info = await asyncio.wait_for(client.get_server_info(), 5) or {}
    except Exception:
        return
    for c in info.get("commands", []) or []:
        name = c.get("name") if isinstance(c, dict) else c
        if name:
            desc = c.get("description", "") if isinstance(c, dict) else ""
            ui.prompt.commands.setdefault("/" + str(name).lstrip("/"), desc)


def build_options(ui: UI, resume_id: str | None = None, continue_last: bool = False) -> ClaudeAgentOptions:
    a = ui.args
    kwargs: dict[str, Any] = dict(
        cwd=str(ui.repo),
        max_buffer_size=a.buffer_mb * 1024 * 1024,
        model=a.model,
        system_prompt={"type": "preset", "preset": "claude_code"},
        setting_sources=["project", "local"],  # baca CLAUDE.md & .claude/settings*.json milik repo
        allowed_tools=AUTO_TOOLS,
        disallowed_tools=BLOCKED_TOOLS,
        permission_mode=a.mode,
        can_use_tool=ui.can_use_tool,
        thinking={"type": "adaptive", "display": "summarized"},
        # /rewind: simpan snapshot file + kirim balik uuid tiap prompt user
        enable_file_checkpointing=True,
        extra_args={"replay-user-messages": None},
        stderr=on_cli_stderr,
    )
    if a.effort:
        kwargs["effort"] = a.effort
    if a.budget:
        kwargs["max_budget_usd"] = a.budget
    if resume_id:
        kwargs["resume"] = resume_id  # lanjutkan percakapan yang sama (auto-recovery / --resume)
    elif continue_last:
        kwargs["continue_conversation"] = True
    return ClaudeAgentOptions(**kwargs)


def explain_error(e: Exception, buffer_mb: int) -> str:
    text = str(e) or type(e).__name__
    if "maximum buffer size" in text:
        return (
            f"Output tool terlalu besar untuk buffer ({buffer_mb} MB), mis. file/log yang sangat panjang.\n"
            "  Tips: jalankan ulang dengan --buffer-mb lebih besar, atau minta Claude membaca "
            "file per bagian / memotong output (mis. `| tail -200`)."
        )
    return text


def compose(ui: UI, prompt: str) -> str:
    """Gabungkan output '!command' / catatan yang tertunda + lampiran @file ke pesan user."""
    prompt = ui.expand_mentions(prompt)
    if ui.pending_context:
        # Teks user tetap di depan supaya judul sesi (/resume) = apa yang user ketik.
        prompt += "\n\nKonteks tambahan dari user:\n" + "\n\n".join(ui.pending_context)
        ui.pending_context.clear()
    return prompt


async def session(ui: UI, resume_id: str | None, continue_last: bool = False) -> Any:
    """Satu proses Claude. Return "exit", "clear", "recover" (error), atau ("resume", id)."""
    # asyncio.run (Python 3.11+) membatalkan seluruh sesi saat Ctrl+C; kita mau perilaku klasik:
    # Ctrl+C di pertanyaan singkat = batal menjawab, saat Claude bekerja = hentikan Claude.
    # (GUI: Ctrl+C di terminal menutup GUI dengan rapi, diatur run_gui.)
    if not getattr(ui, "gui", False):
        with contextlib.suppress(ValueError):
            signal.signal(signal.SIGINT, signal.default_int_handler)
    client = ClaudeSDKClient(options=build_options(ui, resume_id, continue_last))
    reader: asyncio.Future | None = None
    try:
        try:
            await client.connect()
        except (CLINotFoundError, WrongAuthSource):
            raise
        except Exception as e:
            raise StartFailed(str(e) or type(e).__name__) from e
        ui.attach(client)
        reader = asyncio.ensure_future(pump(client, ui))
        await load_commands(client, ui)

        # Goal (/goal) hidup di proses Claude Code: dipulihkan saat --resume/-c dan saat sambung ulang
        # ke sesi yang sama; hilang kalau proses baru dimulai tanpa sesi.
        if ui.goal and not resume_id:
            console.print(f"[yellow]🎯 Goal hilang karena proses Claude dimulai ulang tanpa sesi:[/] "
                          f"{rich_escape(ui.goal_cond(ui.goal.condition))} [dim]· jalankan /goal lagi kalau masih perlu[/]")
            ui.goal = None
        elif resume_id or continue_last:
            try:
                await goal_check(client, ui, "recovered" if ui.goal else "startup")
            except WrongAuthSource:
                raise
            except Exception as e:
                ui.spin_stop()
                console.print(f"\n[red]✗ Terjadi error:[/] {explain_error(e, ui.args.buffer_mb)}")
                return "recover"

        if ui.args.print:  # mode sekali jalan (-p)
            raw = ui.args.print
            if raw.lstrip().startswith("/"):  # perintah slash dikirim apa adanya (tanpa lampiran @file)
                to_send = raw.strip()
                if to_send.lower().split() in [["/goal", w] for w in GOAL_CLEAR_ALIASES]:
                    to_send = "/goal clear"
                if to_send.split()[0] == "/goal":
                    await handle_command(to_send, client, ui)  # tandai jawaban /goal yang ditunggu + peringatan mode
            else:
                to_send = compose(ui, raw)
            await run_turn(client, ui, to_send, raw)
            main_result, main_interrupted = ui.last_result, ui.interrupted  # dicek ulang di bawah untuk exit code
            await goal_after_turn(client, ui)
            await wait_background(ui)
            if (ui.goal and not ui.goal.paused and not ui.cli_busy and ui.last_result is not None
                    and ui.last_result.num_turns > 0):  # ada giliran yang dinilai -> pastikan statusnya
                await goal_check(client, ui, "print")
            if ui.goal:  # belum selesai (dijeda / batas cek): beri tahu cara melanjutkan + exit code khusus
                console.print(f"[yellow]⏸ Goal belum selesai (dijeda):[/] {rich_escape(ui.goal_cond(ui.goal.condition))}")
                if ui.session_id:
                    console.print("[dim]Lanjutkan dengan:[/]")
                    console.print(f"  {self_command()} {quote_arg(str(ui.repo))} --resume {ui.session_id}", soft_wrap=True)
                ui.exit_code = 3
            elif ui.goal_refused or ui.goal_failed:  # ditolak / dihapus setelah error: jangan terlihat seperti sukses
                ui.exit_code = 3
            elif main_interrupted:  # Ctrl+C = 130; izin yang tak bisa ditanyakan (tanpa terminal) = gagal biasa
                ui.exit_code = 1 if ui.perm_unanswerable else 130
            elif main_result is not None and (main_result.is_error or main_result.subtype != "success"):
                ui.exit_code = 1  # error / budget habis: jangan terlihat sukses di script & CI
            return "exit"

        prefill = ""
        while True:
            try:
                prompt = await ui.prompt.read(prefill)
            except EOFError:
                if ui.exit_confirmed or confirm_drop_tasks(ui, "keluar"):
                    console.print()
                    return "exit"
                prefill = ""
                continue
            except KeyboardInterrupt:
                prefill = ""
                if ui.auto_running():  # Ctrl+C saat Claude menanggapi tugas background -> hentikan dulu
                    ui.interrupt_auto()
                    continue
                now = time.monotonic()
                if now - ui.last_ctrl_c < 2:
                    console.print()
                    return "exit"
                ui.last_ctrl_c = now
                n = len(ui.running_bg())
                console.print("[dim](tekan Ctrl+C sekali lagi untuk keluar"
                              + (f" — {n} tugas background akan ikut berhenti" if n else "") + ")[/]")
                continue
            except WrongAuthSource:
                raise
            except Exception as e:  # mesin Claude mati saat user di prompt (dilempar lewat prompt.abort)
                console.print(f"\n[red]✗ Terjadi error:[/] {explain_error(e, ui.args.buffer_mb)}")
                return "recover"
            prefill = ""
            if ui.pump_error is not None:
                if isinstance(ui.pump_error, WrongAuthSource):
                    raise ui.pump_error
                console.print(f"\n[red]✗ Terjadi error:[/] {explain_error(ui.pump_error, ui.args.buffer_mb)}")  # type: ignore[arg-type]
                return "recover"
            if not prompt:
                continue
            if prompt == "?":
                prompt = "/help"
            if prompt.startswith("!"):
                if getattr(ui, "gui", False):  # GUI tetap responsif selama command berjalan
                    await asyncio.to_thread(ui.run_shell, prompt[1:].strip())
                else:
                    ui.run_shell(prompt[1:].strip())
                continue
            if prompt.startswith("#") and not prompt.startswith("##") and "\n" not in prompt and prompt[1:].strip():
                ui.add_memory(prompt[1:].strip())
                continue
            if ui.goal and ui.goal_auto_err and not ui.cli_busy:
                # Giliran otomatis tadi berakhir error: Claude Code mungkin sudah menghapus goal-nya. Pastikan dulu,
                # supaya giliran berikutnya tidak melaporkan "goal berakhir" seolah-olah tercapai.
                ui.goal_err, ui.goal_auto_err = ui.goal_auto_err, ""
                try:
                    await goal_check(client, ui, "auto_error")
                except WrongAuthSource:
                    raise
                except Exception as e:
                    ui.spin_stop()
                    console.print(f"\n[red]✗ Terjadi error:[/] {explain_error(e, ui.args.buffer_mb)}")
                    return "recover"
            if prompt.startswith("/"):
                if prompt.lower().split() in [["/goal", w] for w in GOAL_CLEAR_ALIASES]:
                    prompt = "/goal clear"  # padanan Indonesia -> kata yang dimengerti Claude Code
                action = await handle_command(prompt, client, ui)
                if action != "forward":
                    if action is not None:
                        return action
                    continue
                to_send = prompt  # perintah slash harus tetap di awal pesan
            else:
                to_send = compose(ui, prompt)
            if ui.prompt.interactive:
                # Giliran jalan sebagai task: prompt langsung aktif lagi, jadi user bisa mengirim pesan susulan
                # atau mengantrekan perintah selagi Claude bekerja (seperti Claude Code).
                ui.turn_task = asyncio.ensure_future(turn_job(client, ui, to_send, prompt))
                continue
            try:
                await run_turn(client, ui, to_send, prompt)
                await goal_after_turn(client, ui)
            except WrongAuthSource:
                raise
            except Exception as e:  # mesin Claude crash / koneksi putus -> sambung ulang
                ui.spin_stop()
                console.print(f"\n[red]✗ Terjadi error:[/] {explain_error(e, ui.args.buffer_mb)}")
                return "recover"
            prefill = ui.keys.take_typeahead()
    finally:
        task = ui.turn_task
        if task is not None:  # keluar / /clear / /resume / recover saat giliran masih jalan
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
        ui.prompt.stop()
        ui.spin_stop()
        ui.keys.stop()
        if reader is not None:
            reader.cancel()
            with contextlib.suppress(BaseException):
                await reader
        n = len(ui.running_bg())
        if n:
            console.print(f"[dim]⏹ {n} tugas background dihentikan karena proses Claude ditutup.[/]")
        try:
            await client.disconnect()
        except Exception:
            pass


def keep_awake() -> None:
    """Cegah komputer tidur (sleep) selama claude-code-mini jalan, berhenti otomatis saat keluar.
    macOS: `caffeinate -i`. Windows: SetThreadExecutionState (layar tetap boleh mati)."""
    if os.environ.get("CCMINI_NO_CAFFEINATE"):
        return
    if WINDOWS:
        with contextlib.suppress(Exception):
            import ctypes

            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        return
    if sys.platform != "darwin":
        return
    try:
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def self_command() -> str:
    """Cara menjalankan script ini lagi (untuk petunjuk --resume)."""
    if os.environ.get("CCMINI_LAUNCHER"):
        return "claude-code-mini"
    return f"{PY_CMD} {quote_arg(sys.argv[0])}"


# ---------- GUI (--gui): tampilan web lokal di browser ----------
# Server lokal (Starlette + uvicorn, sudah ikut terpasang bersama claude-agent-sdk) di 127.0.0.1. Logika giliran, izin,
# goal, tugas background, dan pesan susulan memakai UI yang sama dengan terminal; WebUI cuma mengganti tampilannya.
# Keamanan: semua request harus membawa token acak (dicetak di terminal), Host/Origin harus loopback, dan API hanya
# menerima header X-CCMini-Token, jadi halaman web lain tidak bisa menyuruh Claude menjalankan apa pun.
GUI_PORT = 8765
GUI_WIDTH = 100  # lebar (kolom) output rich yang dikirim ke browser

GUI_SHORTCUTS_TEXT = """\
[bold]Di GUI:[/]
  [cyan]Enter[/] kirim · [cyan]Shift+Enter[/] baris baru · [cyan]Esc[/] hentikan Claude · [cyan]Shift+Tab[/] ganti mode izin
  [cyan]![/][dim]command[/], [cyan]@[/][dim]path[/], [cyan]#[/][dim] catatan[/], /perintah: sama seperti di terminal ([cyan]Tab[/] melengkapi / dan @)
  Saat Claude bekerja: pesan biasa dibaca Claude setelah langkah ini; /perintah, !command, # catatan antre
  (↑ di kolom kosong = pesan terakhir) · pertanyaan izin: klik tombolnya atau tekan 1/2/3
[bold]Tugas background:[/] progres tampil di bawah · [cyan]/tasks[/] detail & log · [cyan]/stop 2[/] hentikan
[bold]Goal:[/] [cyan]/goal[/] [dim]kondisi[/] kerja terus sampai terpenuhi · [cyan]/goal[/] status · [cyan]/goal clear[/] batal
"""

GUI_HTML = r'''<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>claude-code-mini</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext x='50' y='78' font-size='90' text-anchor='middle' fill='%23c2603e'%3E%E2%9C%BB%3C/text%3E%3C/svg%3E">
<style>
:root {
  color-scheme: light dark;
  --bg:#f8f7f4; --panel:#ffffff; --raised:#fbfaf8; --text:#1f1e1d; --muted:#6d6a64; --faint:#9a968e;
  --border:#e5e1d8; --accent:#c2603e; --accent-fg:#ffffff; --accent-soft:#f6e9e3; --user:#efebe3; --code:#f3f1ec;
  --ok:#2e7d32; --err:#b3261e; --link:#1d4ed8; --shadow:0 1px 2px rgba(31,30,29,.06);
  --c0:#1f1e1d; --c1:#b3261e; --c2:#2e7d32; --c3:#946200; --c4:#1d4ed8; --c5:#8e3fb0; --c6:#0e7490; --c7:#6d6a64; --c8:#8a877f; --c9:#d93025; --c10:#3b8f3f; --c11:#a87500; --c12:#3b6fe0; --c13:#a855c7; --c14:#0891b2; --c15:#1f1e1d;
  --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, "Cascadia Mono", Consolas, "Liberation Mono", monospace;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:#1d1c1a; --panel:#262523; --raised:#2b2a27; --text:#ecebe7; --muted:#a8a49c; --faint:#7d7a73;
    --border:#3a3834; --accent:#d97757; --accent-fg:#1d1c1a; --accent-soft:#3a2b25; --user:#33312d; --code:#2d2b28;
    --ok:#81c995; --err:#f28b82; --link:#8ab4f8; --shadow:none;
    --c0:#ecebe7; --c1:#f28b82; --c2:#81c995; --c3:#f2c94c; --c4:#8ab4f8; --c5:#d7aefb; --c6:#78d9ec; --c7:#bdb9b1; --c8:#8a877f; --c9:#ff9a90; --c10:#a6e3b5; --c11:#ffd772; --c12:#a8c7fa; --c13:#e3c2ff; --c14:#9fe5f2; --c15:#ffffff;
  }
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { background: var(--bg); color: var(--text); font: 15px/1.55 var(--sans); display: flex; flex-direction: column; }
header { display: flex; align-items: center; gap: 12px; padding: 9px 16px; border-bottom: 1px solid var(--border);
  background: var(--panel); flex-wrap: wrap; }
.brand { font-weight: 600; display: flex; align-items: center; gap: 7px; white-space: nowrap; }
.brand .star { color: var(--accent); font-size: 19px; line-height: 1; }
.repo { color: var(--muted); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: 1; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; }
button { font: inherit; font-size: 13px; border: 1px solid var(--border); background: var(--raised); color: var(--text);
  border-radius: 8px; padding: 5px 11px; cursor: pointer; }
button:hover:not(:disabled) { border-color: var(--faint); }
button:disabled { opacity: .55; cursor: default; }
button:focus-visible, select:focus-visible, textarea:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
button.primary { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); font-weight: 600; }
button.danger { color: var(--err); }
main { flex: 1; overflow-y: auto; }
#chat { max-width: 940px; margin: 0 auto; padding: 22px 16px 30px; display: flex; flex-direction: column; gap: 12px; }
.empty { color: var(--muted); text-align: center; margin-top: 14vh; line-height: 1.8; }
.empty .big { font-size: 34px; color: var(--accent); }
.empty small { color: var(--faint); }
.user { align-self: flex-end; max-width: 85%; background: var(--user); border-radius: 14px; padding: 8px 14px;
  white-space: pre-wrap; overflow-wrap: anywhere; }
.md { overflow-wrap: anywhere; }
.md > :first-child { margin-top: 0; } .md > :last-child { margin-bottom: 0; }
.md pre { background: var(--code); padding: 10px 12px; border-radius: 8px; overflow: auto; font: 13px/1.5 var(--mono); }
.md code { font: 13px var(--mono); background: var(--code); padding: 1px 5px; border-radius: 5px; }
.md pre code { background: none; padding: 0; }
.md table { border-collapse: collapse; display: block; overflow-x: auto; }
.md th, .md td { border: 1px solid var(--border); padding: 4px 9px; }
.md a { color: var(--link); }
.md blockquote { margin: 0; padding-left: 12px; border-left: 3px solid var(--border); color: var(--muted); }
details.thinking { color: var(--muted); font-style: italic; font-size: 14px; }
details.thinking summary { cursor: pointer; }
details.thinking div { white-space: pre-wrap; padding: 4px 0 0 18px; }
.tool { border: 1px solid var(--border); background: var(--panel); border-radius: 10px; box-shadow: var(--shadow); overflow: hidden; }
.tool.nested { margin-left: 28px; }
.tool .head { display: flex; gap: 8px; align-items: baseline; padding: 7px 12px; font-size: 14px; }
.tool .dot { color: var(--ok); } .tool.nested .dot { color: var(--c5); } .tool.err .dot { color: var(--err); }
.tool.run .dot { color: var(--faint); animation: blink 1.2s infinite; }
.tool .name { font-weight: 600; white-space: nowrap; }
.tool .sum { font-family: var(--mono); font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }
.tool pre, pre.log, .ask pre { margin: 0; font: 12.5px/1.45 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; }
.tool .detail { padding: 0 12px 8px 30px; }
.tool .result { border-top: 1px dashed var(--border); padding: 6px 12px 8px 30px; color: var(--muted); }
.tool .result.err { color: var(--err); }
.tool details summary { cursor: pointer; font-size: 12px; color: var(--faint); margin-top: 4px; }
.tool details pre { max-height: 360px; overflow: auto; background: var(--code); padding: 8px; border-radius: 6px; margin-top: 4px; color: var(--text); }
pre.log { padding: 0 2px; }
.ask { border: 1.5px solid var(--accent); background: var(--panel); border-radius: 12px; padding: 12px 14px; box-shadow: var(--shadow); }
.ask .title { font-weight: 600; margin-bottom: 8px; }
.ask .body { background: var(--code); border-radius: 8px; padding: 8px 10px; margin: 0 0 10px; max-height: 50vh; overflow: auto; }
.ask .opts { display: flex; flex-direction: column; gap: 6px; }
.ask .opts button { text-align: left; padding: 7px 12px; display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
.ask .opts kbd { font: 12px var(--mono); color: var(--faint); }
.ask .opts small { color: var(--muted); }
.ask .opts button.chosen { border-color: var(--accent); background: var(--accent-soft); opacity: 1; }
.ask.done { border-color: var(--border); }
.ask.done .opts button:not(.chosen) { display: none; }
.ask .reason { display: flex; gap: 6px; margin-top: 8px; }
.ask .reason input { flex: 1; font: inherit; font-size: 14px; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--bg); color: var(--text); min-width: 0; }
.answer { font-size: 13px; color: var(--muted); margin-top: 6px; }
.banner { background: var(--accent-soft); color: var(--text); border-bottom: 1px solid var(--border); padding: 8px 16px; font-size: 14px; text-align: center; }
.banner.err { color: var(--err); }
#dock { border-top: 1px solid var(--border); background: var(--panel); }
#dock .inner { max-width: 940px; margin: 0 auto; padding: 8px 16px 10px; }
#working { display: flex; align-items: center; gap: 10px; padding: 1px 0 7px; }
#working .spin { width: 13px; height: 13px; border: 2px solid var(--accent-soft); border-top-color: var(--accent); border-radius: 50%;
  animation: spin .8s linear infinite; flex: none; }
#working .txt { flex: 1; min-width: 0; font: 12.5px var(--mono); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#working button { padding: 3px 10px; }
.rows { font: 12.5px/1.5 var(--mono); color: var(--muted); padding-bottom: 5px; }
.rows:empty { display: none; }
.rows div { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.composer { position: relative; display: flex; gap: 8px; align-items: flex-end; }
textarea { flex: 1; resize: none; font: 15px/1.45 var(--sans); padding: 10px 12px; border-radius: 12px; border: 1px solid var(--border);
  background: var(--bg); color: var(--text); max-height: 40vh; min-height: 44px; }
#send { height: 44px; padding: 0 18px; }
#sugg { position: absolute; left: 0; right: 86px; bottom: 100%; margin-bottom: 6px; background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; box-shadow: 0 6px 24px rgba(0,0,0,.14); max-height: 280px; overflow: auto; z-index: 5; }
#sugg div { padding: 6px 10px; font: 13px var(--mono); cursor: pointer; display: flex; gap: 14px; }
#sugg div span { color: var(--muted); font-family: var(--sans); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#sugg div.on { background: var(--accent-soft); }
footer { display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; font-size: 12.5px; color: var(--muted); padding-top: 8px; }
footer select { font: inherit; font-size: 12.5px; background: var(--raised); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 2px 4px; max-width: 260px; }
footer select.yolo { color: var(--err); font-weight: 600; }
#conn::before { content: "● "; color: var(--ok); } #conn.lost::before { color: var(--err); }
[hidden] { display: none !important; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes blink { 50% { opacity: .3; } }
.b { font-weight: 600; } .d { opacity: .62; } .i { font-style: italic; } .u { text-decoration: underline; } .s { text-decoration: line-through; }
.c0{color:var(--c0)}.c1{color:var(--c1)}.c2{color:var(--c2)}.c3{color:var(--c3)}.c4{color:var(--c4)}.c5{color:var(--c5)}.c6{color:var(--c6)}.c7{color:var(--c7)}.c8{color:var(--c8)}.c9{color:var(--c9)}.c10{color:var(--c10)}.c11{color:var(--c11)}.c12{color:var(--c12)}.c13{color:var(--c13)}.c14{color:var(--c14)}.c15{color:var(--c15)}.bg0{background:var(--c0)}.bg1{background:var(--c1)}.bg2{background:var(--c2)}.bg3{background:var(--c3)}.bg4{background:var(--c4)}.bg5{background:var(--c5)}.bg6{background:var(--c6)}.bg7{background:var(--c7)}.bg8{background:var(--c8)}.bg9{background:var(--c9)}.bg10{background:var(--c10)}.bg11{background:var(--c11)}.bg12{background:var(--c12)}.bg13{background:var(--c13)}.bg14{background:var(--c14)}.bg15{background:var(--c15)}
@media (max-width: 640px) {
  body { font-size: 14px; } .user { max-width: 95%; } .tool.nested { margin-left: 10px; }
  .tool .detail, .tool .result { padding-left: 12px; } #chat { padding: 14px 10px 24px; } #dock .inner { padding: 8px 10px 10px; }
}
</style>
</head>
<body>
<header>
  <div class="brand"><span class="star">✻</span>claude-code-mini</div>
  <div class="repo" id="repo"></div>
  <div class="actions">
    <button data-cmd="/clear" title="Mulai percakapan baru (konteks lama dibuang)">Baru</button>
    <button data-cmd="/resume" title="Lanjutkan percakapan lama di folder ini">Riwayat</button>
    <button data-cmd="/rewind" title="Kembalikan file ke kondisi sebelum prompt tertentu">Rewind</button>
    <button data-cmd="/help">Bantuan</button>
    <button data-cmd="/exit" class="danger" title="Tutup claude-code-mini (percakapan tetap tersimpan)">Keluar</button>
  </div>
</header>
<div id="banner" class="banner" hidden></div>
<main id="main"><div id="chat"></div></main>
<div id="dock"><div class="inner">
  <div id="working" hidden aria-live="polite"><div class="spin"></div><div class="txt" id="workingText"></div>
    <button id="stop" class="danger" title="Hentikan Claude (Esc)">■ Stop</button></div>
  <div class="rows" id="rows"></div>
  <div class="composer">
    <div id="sugg" hidden></div>
    <textarea id="input" rows="1" aria-label="Pesan" autofocus></textarea>
    <button id="send" class="primary" title="Kirim (Enter)">Kirim</button>
  </div>
  <footer>
    <label>Mode <select id="mode" title="Ganti mode izin (Shift+Tab)"></select></label>
    <label>Model <select id="model"></select></label>
    <span id="ctx"></span><span id="cost"></span><span id="goal"></span>
    <span id="conn">menyambung…</span>
  </footer>
</div></div>
<script>
(() => {
"use strict";
const TOKEN = __CCM_TOKEN__;
const $ = (id) => document.getElementById(id);
const chat = $("chat"), main = $("main"), input = $("input"), sugg = $("sugg");
const st = { busy: false, asking: false, tasks: [], modes: {}, cycle: [], models: {}, name: "", mode: "", model: "" };
const tools = new Map(), asks = new Map(), sent = [];
let lastSeq = 0, lastLog = null, es = null, closed = false, histIdx = -1;
let suggItems = [], suggIdx = 0, suggTimer = null;

if (location.search) history.replaceState(null, "", location.pathname);  // token tidak terlihat di address bar

function post(action, body) {
  return fetch("/api/" + action, { method: "POST", headers: { "Content-Type": "application/json", "X-CCMini-Token": TOKEN },
    body: JSON.stringify(body || {}) }).then(r => r.json()).catch(() => ({}));
}
function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function nearBottom() { return main.scrollHeight - main.scrollTop - main.clientHeight < 160; }
function toBottom(stick) { if (stick) main.scrollTop = main.scrollHeight; }
function add(node, isLog) {
  const stick = nearBottom();
  const empty = chat.querySelector(".empty");
  if (empty) empty.remove();
  chat.appendChild(node);
  lastLog = isLog ? node : null;
  toBottom(stick);
  return node;
}
function emptyState() {
  const d = mk("div", "empty");
  d.appendChild(mk("div", "big", "✻"));
  d.appendChild(mk("div", null, "Ketik pesan di bawah untuk mulai."));
  d.appendChild(mk("small", null, "/ perintah · @ lampirkan file · ! jalankan command · # simpan catatan ke CLAUDE.md"));
  return d;
}
function links(root) { root.querySelectorAll("a[href]").forEach(a => { a.target = "_blank"; a.rel = "noopener noreferrer"; }); }
function banner(text, kind) {
  const b = $("banner");
  b.hidden = !text; b.textContent = text || ""; b.className = "banner" + (kind ? " " + kind : "");
}
function title() {
  const pre = asks.size ? "🔐 " : st.busy ? "⏳ " : "";
  document.title = pre + (st.name ? st.name + " · " : "") + "claude-code-mini";
}

// ---------- event dari claude-code-mini ----------
const H = {
  user(ev) { add(mk("div", "user", ev.text)); },
  assistant(ev) { const d = mk("div", "md"); d.innerHTML = ev.html; links(d); add(d); },
  thinking(ev) {
    const d = mk("details", "thinking");
    d.appendChild(mk("summary", null, "✻ Berpikir…"));
    d.appendChild(mk("div", null, ev.text));
    add(d);
  },
  tool(ev) {
    const card = mk("div", "tool run" + (ev.nested ? " nested" : ""));
    const head = mk("div", "head");
    head.appendChild(mk("span", "dot", "●"));
    head.appendChild(mk("span", "name", ev.name));
    if (ev.summary) head.appendChild(mk("span", "sum", ev.summary));
    card.appendChild(head);
    if (ev.detail) { const pre = mk("pre", "detail"); pre.innerHTML = ev.detail; card.appendChild(pre); }
    tools.set(ev.id, card);
    add(card);
  },
  tool_result(ev) {
    const box = mk("div", "result" + (ev.error ? " err" : ""));
    box.appendChild(mk("pre", null, "⎿  " + ev.summary));
    if (ev.full) {
      const d = mk("details");
      d.appendChild(mk("summary", null, "Lihat output lengkap"));
      d.appendChild(mk("pre", null, ev.full));
      box.appendChild(d);
    }
    const card = tools.get(ev.id);
    if (!card) { add(box); return; }
    const stick = nearBottom();
    card.classList.remove("run");
    if (ev.error) card.classList.add("err");
    card.appendChild(box);
    toBottom(stick);
  },
  log(ev) {
    if (lastLog && lastLog === chat.lastElementChild) {
      const stick = nearBottom();
      lastLog.insertAdjacentHTML("beforeend", ev.html);
      toBottom(stick);
      return;
    }
    const pre = mk("pre", "log");
    pre.innerHTML = ev.html;
    add(pre, true);
  },
  ask(ev) {
    const card = mk("div", "ask");
    card.appendChild(mk("div", "title", ev.title));
    if (ev.body) {
      const plan = ev.kind === "plan";
      const b = mk(plan ? "div" : "pre", "body" + (plan ? " md" : ""));
      b.innerHTML = ev.body;
      if (plan) links(b);
      card.appendChild(b);
    }
    const opts = mk("div", "opts");
    ev.options.forEach((o, i) => {
      const btn = mk("button");
      btn.dataset.value = o.value;
      btn.appendChild(mk("kbd", null, String(i + 1)));
      btn.appendChild(mk("span", null, o.label));
      if (o.note) btn.appendChild(mk("small", null, "(" + o.note + ")"));
      btn.onclick = () => choose(ev.id, o);
      opts.appendChild(btn);
    });
    card.appendChild(opts);
    asks.set(ev.id, { card, ev });
    add(card);
    if (!input.value) opts.firstChild.focus({ preventScroll: true });
    title();
  },
  answered(ev) {
    const a = asks.get(ev.id);
    if (!a) return;
    asks.delete(ev.id);
    a.card.classList.add("done");
    a.card.querySelectorAll(".opts button").forEach(b => {
      b.disabled = true;
      if (b.dataset.value === String(ev.value)) b.classList.add("chosen");
    });
    const r = a.card.querySelector(".reason");
    if (r) r.remove();
    a.card.appendChild(mk("div", "answer", "→ " + ev.label));
    if (document.activeElement === document.body || a.card.contains(document.activeElement)) input.focus({ preventScroll: true });
    title();
  },
  status(s) {
    st.busy = s.busy; st.asking = s.asking; st.tasks = s.tasks || []; st.mode = s.mode; st.model = s.model;
    $("working").hidden = !(s.busy || s.asking);
    $("workingText").textContent = s.working || (s.asking ? "Menunggu jawabanmu…" : "Claude bekerja…");
    const rows = $("rows");
    rows.textContent = "";
    (s.pending || []).forEach(t => rows.appendChild(mk("div", null, "⏳ dibaca Claude setelah langkah ini: " + t)));
    (s.queued || []).forEach(t => rows.appendChild(mk("div", null, "⏳ setelah giliran selesai: " + t)));
    (s.tasks || []).forEach(t => rows.appendChild(mk("div", null, t)));
    selects();
    $("ctx").textContent = s.ctx == null ? "" : "konteks " + s.ctx + "%";
    $("cost").textContent = s.cost || "";
    $("goal").textContent = s.goal || "";
    input.placeholder = s.busy
      ? "Ketik pesan susulan… Enter = kirim (dibaca Claude setelah langkah ini) · Esc = hentikan"
      : "Ketik pesan… Enter kirim · Shift+Enter baris baru · / perintah · @ file · ! command";
    title();
  },
  fatal(ev) { banner(ev.text, "err"); },
  bye() {
    closed = true;
    if (es) es.close();
    banner("claude-code-mini sudah berhenti. Jalankan lagi dari terminal untuk melanjutkan percakapan.", "err");
    $("conn").textContent = "berhenti"; $("conn").classList.add("lost");
    input.disabled = true; $("send").disabled = true; $("working").hidden = true;
  },
};

function handle(ev) {
  if (ev.type === "hello") {
    chat.textContent = ""; chat.appendChild(emptyState());
    tools.clear(); asks.clear(); lastLog = null; lastSeq = 0;
    st.modes = ev.modes || {}; st.cycle = ev.cycle || []; st.models = ev.models || {}; st.name = ev.name || "";
    $("repo").textContent = "📂 " + ev.repo; $("repo").title = ev.repo;
    title();
    return;
  }
  if (ev.seq) { if (ev.seq <= lastSeq) return; lastSeq = ev.seq; }
  const f = H[ev.type];
  if (f) f(ev);
}

function connect() {
  es = new EventSource("/events?t=" + encodeURIComponent(TOKEN));
  es.onopen = () => { $("conn").textContent = "terhubung"; $("conn").classList.remove("lost"); if (!closed) banner(""); };
  es.onerror = () => {
    if (closed) return;
    $("conn").textContent = "terputus"; $("conn").classList.add("lost");
    banner("Koneksi ke claude-code-mini terputus — mencoba lagi…", "err");
  };
  es.onmessage = (e) => {
    let ev;
    try { ev = JSON.parse(e.data); } catch (err) { return; }
    try { handle(ev); } catch (err) { console.error(err); }
  };
}

// ---------- pertanyaan izin / pilihan ----------
function choose(id, o) {
  const a = asks.get(id);
  if (!a) return;
  if (o.value === "no" && a.ev.reason) {
    if (a.card.querySelector(".reason")) { a.card.querySelector(".reason input").focus(); return; }
    const row = mk("div", "reason");
    const inp = mk("input");
    inp.placeholder = a.ev.reason;
    const go = mk("button", "primary", "Kirim");
    const submit = () => post("answer", { id, value: "no", reason: inp.value.trim() });
    go.onclick = submit;
    inp.onkeydown = (e) => {
      if (e.key === "Enter") { e.preventDefault(); submit(); }
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); row.remove(); }
    };
    row.appendChild(inp); row.appendChild(go);
    a.card.appendChild(row);
    inp.focus();
    return;
  }
  post("answer", { id, value: o.value });
}

// ---------- kolom chat ----------
function autosize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight + 2, window.innerHeight * 0.4) + "px";
}
function guard(cmd) {
  const word = cmd.split(/\s/)[0].toLowerCase();
  if (["/clear", "/resume", "/exit", "/quit"].includes(word) && (st.busy || st.tasks.length))
    return confirm("Claude masih bekerja atau ada tugas background; " + word + " akan menghentikannya. Lanjut?");
  return true;
}
function send() {
  const text = input.value.trim();
  if (!text || !guard(text)) return;
  post("send", { text });
  sent.push(text); histIdx = -1;
  input.value = ""; autosize(); hideSugg();
}
document.querySelectorAll("[data-cmd]").forEach(b => b.onclick = () => {
  const cmd = b.dataset.cmd;
  if (cmd === "/exit" && !confirm("Tutup claude-code-mini? Percakapan tetap tersimpan dan bisa dilanjutkan nanti.")) return;
  if (!guard(cmd)) return;
  post("send", { text: cmd });
});
$("send").onclick = send;
$("stop").onclick = () => post("stop");
$("mode").onchange = (e) => post("mode", { mode: e.target.value });
$("model").onchange = (e) => post("model", { model: e.target.value });

function selects() {
  const m = $("mode"), want = st.cycle.slice();
  if (st.mode && !want.includes(st.mode)) want.push(st.mode);
  if (m.dataset.sig !== want.join()) {
    m.textContent = "";
    want.forEach(k => { const o = mk("option", null, st.modes[k] || k); o.value = k; m.appendChild(o); });
    m.dataset.sig = want.join();
  }
  m.value = st.mode;
  m.classList.toggle("yolo", st.mode === "bypassPermissions");
  const md = $("model"), entries = Object.entries(st.models);
  if (st.model && !entries.some(([, v]) => v === st.model)) entries.push([st.model, st.model]);
  const sig = entries.map(e => e.join("=")).join();
  if (md.dataset.sig !== sig) {
    md.textContent = "";
    entries.forEach(([k, v]) => { const o = mk("option", null, k === v ? v : k + " · " + v); o.value = v; md.appendChild(o); });
    md.dataset.sig = sig;
  }
  md.value = st.model;
}

// saran /perintah dan @path
function hideSugg() { sugg.hidden = true; suggItems = []; }
function scheduleSugg() { clearTimeout(suggTimer); suggTimer = setTimeout(updateSugg, 90); }
async function updateSugg() {
  const before = input.value.slice(0, input.selectionStart);
  const word = (before.match(/\S*$/) || [""])[0];
  if (!((word.startsWith("/") && before.trimStart() === word) || word.startsWith("@"))) { hideSugg(); return; }
  const r = await post("complete", { text: before });
  if (input.value.slice(0, input.selectionStart) !== before) return;  // sudah berubah lagi
  suggItems = r.items || []; suggIdx = 0;
  if (!suggItems.length) { hideSugg(); return; }
  sugg.textContent = "";
  suggItems.forEach((it, i) => {
    const d = mk("div", i === 0 ? "on" : null);
    d.appendChild(document.createTextNode(it.label));
    if (it.meta) d.appendChild(mk("span", null, it.meta));
    d.onmousedown = (e) => { e.preventDefault(); applySugg(it); };
    sugg.appendChild(d);
  });
  sugg.hidden = false;
}
function moveSugg(d) {
  suggIdx = (suggIdx + d + suggItems.length) % suggItems.length;
  [...sugg.children].forEach((c, i) => c.classList.toggle("on", i === suggIdx));
  sugg.children[suggIdx].scrollIntoView({ block: "nearest" });
}
function applySugg(it) {
  const pos = input.selectionStart, before = input.value.slice(0, pos), after = input.value.slice(pos);
  const word = (before.match(/\S*$/) || [""])[0], start = before.length - word.length;
  input.value = before.slice(0, start) + it.value + after;
  const np = start + it.value.length;
  input.setSelectionRange(np, np);
  hideSugg(); autosize(); input.focus();
  if (it.value.endsWith("/") || it.value.endsWith("\\")) scheduleSugg();  // folder: lanjut ke isinya
}

input.addEventListener("input", () => { autosize(); scheduleSugg(); });
input.addEventListener("blur", () => setTimeout(hideSugg, 150));
input.addEventListener("keydown", (e) => {
  if (!sugg.hidden && suggItems.length) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); moveSugg(e.key === "ArrowDown" ? 1 : -1); return; }
    if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
      const it = suggItems[suggIdx];
      const word = (input.value.slice(0, input.selectionStart).match(/\S*$/) || [""])[0];
      if (!(e.key === "Enter" && word === it.label)) { e.preventDefault(); applySugg(it); return; }
    }
    if (e.key === "Escape") { e.preventDefault(); hideSugg(); return; }
  }
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); return; }
  if (e.key === "Tab" && e.shiftKey) { e.preventDefault(); post("mode", { mode: "cycle" }); return; }
  if (e.key === "Escape") { if (st.busy || st.asking) { e.preventDefault(); post("stop"); } return; }
  if (e.key === "ArrowUp" && !input.value && sent.length) {
    e.preventDefault(); histIdx = histIdx < 0 ? sent.length - 1 : Math.max(0, histIdx - 1);
    input.value = sent[histIdx]; autosize();
  } else if (e.key === "ArrowDown" && histIdx >= 0 && input.selectionStart === input.value.length) {
    e.preventDefault(); histIdx += 1;
    input.value = histIdx < sent.length ? sent[histIdx] : ""; if (histIdx >= sent.length) histIdx = -1; autosize();
  }
});
document.addEventListener("keydown", (e) => {
  const t = e.target, typing = t === input || t.tagName === "INPUT" || t.tagName === "SELECT";
  if (typing) return;
  if (e.key === "Escape" && (st.busy || st.asking)) { e.preventDefault(); post("stop"); return; }
  if (/^[1-9]$/.test(e.key) && asks.size) {
    const a = [...asks.values()].pop(), o = a.ev.options[Number(e.key) - 1];
    if (o) { e.preventDefault(); choose(a.ev.id, o); }
    return;
  }
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) input.focus();
});

chat.appendChild(emptyState());
autosize();
connect();
})();
</script>
</body>
</html>
'''

GUI_LOCKED_HTML = r'''<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>claude-code-mini</title>
<style>body{font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;background:#f8f7f4;color:#1f1e1d;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0;padding:16px;box-sizing:border-box}
@media (prefers-color-scheme: dark){body{background:#1d1c1a;color:#ecebe7}}
div{max-width:560px}b{color:#c2603e}</style></head>
<body><div><p><b>✻ claude-code-mini</b></p>
<p>Halaman ini butuh token. Buka lewat URL lengkap yang dicetak di terminal saat menjalankan
<code>claude-code-mini --gui</code> (alamat yang berakhiran <code>/?t=…</code>).</p></div></body></html>
'''

_HTML_CONSOLE: Any = None
_MD: Any = None


def segments_html(segments: Any) -> str:
    """Segment rich -> HTML. Warna standar jadi kelas c0..c15 (warnanya mengikuti tema terang/gelap halaman)."""
    out = []
    for seg in segments:
        text, style, control = seg.text, seg.style, seg.control
        if control or not text:
            continue
        t = htmllib.escape(text, quote=False)
        if not style:
            out.append(t)
            continue
        cls, css = [], []
        for flag, c in (("bold", "b"), ("dim", "d"), ("italic", "i"), ("underline", "u"), ("strike", "s")):
            if getattr(style, flag):
                cls.append(c)
        for prefix, color in (("c", style.color), ("bg", style.bgcolor)):
            if color is None or color.is_default:
                continue
            if color.number is not None and color.number < 16:
                cls.append(f"{prefix}{color.number}")
            else:
                r, g, b = color.get_truecolor()
                css.append(f"{'color' if prefix == 'c' else 'background'}:#{r:02x}{g:02x}{b:02x}")
        attrs = (f' class="{" ".join(cls)}"' if cls else "") + (f' style="{";".join(css)}"' if css else "")
        out.append(f"<span{attrs}>{t}</span>" if attrs else t)
    return "".join(out)


def rich_html(renderable: Any, width: int = GUI_WIDTH) -> str:
    """Renderable rich (diff, todo, panel) -> HTML untuk browser."""
    global _HTML_CONSOLE
    if _HTML_CONSOLE is None:
        _HTML_CONSOLE = Console(file=io.StringIO(), force_terminal=True, color_system="truecolor", width=width,
                                highlight=False, legacy_windows=False)
    c = _HTML_CONSOLE
    return segments_html(c.render(renderable, c.options.update(width=width)))


def md_html(text: str) -> str:
    """Markdown jawaban Claude -> HTML. HTML mentah di teksnya di-escape (tidak dijalankan browser)."""
    global _MD
    if _MD is None:
        from markdown_it import MarkdownIt

        _MD = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable(["table", "strikethrough"])
    return _MD.render(text)


class _NullFile(io.TextIOBase):
    def write(self, s: str) -> int:
        return len(s)


class WebConsole(Console):
    """`console` di mode GUI: setiap console.print dikirim ke browser sebagai potongan HTML (event "log"),
    tidak ke terminal. Warna, panel, dan diff rich tetap terlihat."""

    def __init__(self, emit: Any):
        super().__init__(file=_NullFile(), record=True, force_terminal=True, color_system="truecolor",
                         width=GUI_WIDTH, highlight=False, legacy_windows=False)
        self._emit = emit

    def print(self, *objects: Any, **kwargs: Any) -> None:
        super().print(*objects, **kwargs)
        with self._record_buffer_lock:
            segments = list(self._record_buffer)
            del self._record_buffer[:]
        html = segments_html(segments)
        if html.strip():
            self._emit("log", {"html": html})


class WebHub:
    """Event dari UI ke semua tab browser (Server-Sent Events). Riwayatnya disimpan, jadi tab yang baru dibuka atau
    di-reload langsung menampilkan percakapan yang sedang berjalan. Aman dipanggil dari thread lain."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.log: deque[dict[str, Any]] = deque(maxlen=5000)
        self.clients: set[asyncio.Queue] = set()
        self.seq = 0
        self.status: dict[str, Any] | None = None

    def emit(self, kind: str, data: dict[str, Any] | None = None) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        ev = {"type": kind, **(data or {})}
        try:
            same = asyncio.get_running_loop() is loop
        except RuntimeError:
            same = False
        if same:
            self._push(ev)
        else:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self._push, ev)

    def _push(self, ev: dict[str, Any]) -> None:
        self.seq += 1
        ev["seq"] = self.seq
        if ev["type"] == "status":
            self.status = ev
        else:
            self.log.append(ev)
        for q in list(self.clients):
            q.put_nowait(ev)

    def close(self) -> None:
        for q in list(self.clients):
            q.put_nowait(None)


class _NoKeys:
    """Pengganti KeyWatcher di mode GUI (tombol dibaca di browser, bukan di terminal)."""

    def start(self, *args: Any) -> None:
        pass

    pause = resume = stop = start

    def take_typeahead(self) -> str:
        return ""


class WebPrompt:
    """Pengganti PromptInput di mode GUI: pesan datang dari browser (POST /api/send), bukan dari keyboard."""

    def __init__(self, ui: "WebUI"):
        self.ui = ui
        self.repo = ui.repo
        self.commands: dict[str, str] = dict(LOCAL_COMMANDS)
        self.interactive = True  # giliran jalan sebagai task: browser tetap bisa mengirim pesan susulan
        self.queue: deque[str] = deque()  # ketikan saat Claude bekerja yang menunggu giliran selesai
        self.inbox: asyncio.Queue | None = None
        self._paths = PromptInput(ui)  # dipakai untuk melengkapi @path

    def _box(self) -> asyncio.Queue:
        if self.inbox is None:
            self.inbox = asyncio.Queue()
        return self.inbox

    def active(self) -> bool:
        return False

    def submit(self, text: str) -> None:
        self._box().put_nowait(text)

    async def read(self, prefill: str = "") -> str:
        box = self._box()
        while True:
            err, self.ui.turn_error = self.ui.turn_error, None
            if err is not None:
                raise err
            if self.queue and not self.ui.busy():  # antrean dari saat Claude bekerja
                text = self.queue.popleft()
                self.ui.show_user(text)
                return text
            item = await box.get()
            if item is DRAIN:
                continue
            if isinstance(item, BaseException):
                raise item
            return item

    def drain(self) -> None:
        if self.queue and not self.ui.busy():
            self._box().put_nowait(DRAIN)

    async def run_above(self, func: Any) -> Any:
        return func()

    async def above(self, func: Any) -> Any:
        r = func()
        return await r if inspect.isawaitable(r) else r

    def abort(self, err: BaseException) -> None:
        self._box().put_nowait(err)

    def stop(self) -> None:
        pass

    def path_matches(self, text: str) -> list[str]:
        return self._paths.path_matches(text)


class WebUI(UI):
    """UI untuk mode --gui. Pesan, tool, dan pertanyaan izin dikirim ke browser sebagai event terstruktur;
    output lain (console.print) sebagai potongan HTML lewat WebConsole."""

    gui = True

    def __init__(self, repo: Path, args: argparse.Namespace, hub: WebHub):
        self.hub = hub
        self.waiters: dict[str, asyncio.Future] = {}
        self.ask_seq = 0
        super().__init__(repo, args)
        self.prompt = WebPrompt(self)  # type: ignore[assignment]
        self.keys = _NoKeys()  # type: ignore[assignment]

    # --- tampilan ---
    def spin_start(self, tool: str | None = None) -> None:
        self.current_tool = tool  # spinner digambar browser dari event status

    def spin_stop(self) -> None:
        pass

    def show_text(self, text: str) -> None:
        self.hub.emit("assistant", {"html": md_html(text)})

    def show_thinking(self, text: str) -> None:
        self.hub.emit("thinking", {"text": clip(text, 20000)})

    def show_user(self, text: str, gap: bool = True) -> None:
        self.hub.emit("user", {"text": text})

    def print_tool_use(self, block: ToolUseBlock, nested: bool) -> None:
        summary, detail = self.describe_tool(block.name, block.input or {})
        self.hub.emit("tool", {"id": block.id, "name": TOOL_LABEL.get(block.name, block.name), "summary": summary,
                               "detail": rich_html(detail) if detail is not None else "", "nested": nested})

    def print_tool_result(self, block: ToolResultBlock, nested: bool) -> None:
        name = self.tool_names.get(block.tool_use_id, "")
        msg = self.result_summary(block)
        if msg is None:
            return
        full = "" if name in ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit") else self.result_text(block).strip("\n")
        if full.strip() == msg.strip() or (not block.is_error and len(full.splitlines()) <= 4 and len(full) <= 720):
            full = ""  # ringkasannya sudah memuat semuanya
        self.hub.emit("tool_result", {"id": block.tool_use_id, "summary": msg, "error": bool(block.is_error),
                                      "full": clip(full, 30000), "nested": nested})

    # --- pertanyaan (izin, rencana, pilihan) ---
    async def ask_web(self, kind: str, title: str, body: str = "", options: Any = (),
                      reason: str | None = None) -> tuple[str | None, str]:
        """Tampilkan pertanyaan di browser dan tunggu jawabannya: (nilai pilihan atau None kalau dibatalkan, alasan)."""
        self.ask_seq += 1
        qid = f"q{self.ask_seq}"
        fut = asyncio.get_running_loop().create_future()
        self.waiters[qid] = fut
        opts = [{"value": o[0], "label": o[1], "note": o[2] if len(o) > 2 else ""} for o in options]
        self.hub.emit("ask", {"id": qid, "kind": kind, "title": title, "body": body, "options": opts, "reason": reason})
        try:
            value, why = await fut
        finally:
            self.waiters.pop(qid, None)
        label = next((o["label"] for o in opts if o["value"] == value), "Dibatalkan")
        self.hub.emit("answered", {"id": qid, "value": value, "label": label + (f" · {why}" if why else "")})
        return value, why

    def answer(self, qid: str, value: Any, why: str = "") -> bool:
        fut = self.waiters.get(str(qid))
        if fut is None or fut.done():
            return False
        fut.set_result((None if value is None else str(value), str(why or "")))
        return True

    def cancel_questions(self) -> bool:
        pending = [f for f in self.waiters.values() if not f.done()]
        for fut in pending:
            fut.set_result((None, ""))
        return bool(pending)

    async def can_use_tool(self, tool: str, inp: dict[str, Any], ctx: ToolPermissionContext) -> Any:
        if tool in self.session_allow:
            return PermissionResultAllow()
        if tool == "ExitPlanMode":
            ans, why = await self.ask_web(
                "plan", "📋 Rencana dari Claude", md_html(await self.plan_text(inp) or "(rencana kosong)"),
                [("1", "Ya, mulai dan auto-terima edit"), ("2", "Ya, tapi tanya dulu setiap edit"),
                 ("no", "Tidak, lanjut merencanakan")], reason="Apa yang perlu diubah dari rencananya?")
            return self.cancelled("Persetujuan rencana") if ans is None else self.plan_answer(ans, why)
        title, body, suggestions, rules, where = self.permission_view(tool, inp, ctx)
        note = (f"disimpan di {where}" if where else "") if rules else "sampai claude-code-mini ditutup"
        ans, why = await self.ask_web(
            "permission", f"🔐 {title}", rich_html(body),
            [("yes", "Ya"), ("always", f"Ya, dan jangan tanya lagi untuk {rules or tool}", note),
             ("no", "Tidak, dan beri tahu Claude harus bagaimana")],
            reason="Kasih tahu Claude harus gimana (opsional)")
        return self.cancelled(f"Izin {tool}") if ans is None else self.permission_answer(tool, ans, suggestions, rules, why)

    def cancelled(self, what: str) -> PermissionResultDeny:
        console.print(f"[yellow]✗ {what} dibatalkan[/]")
        if self.fg_active:
            self.interrupted = True
        return PermissionResultDeny(message="User membatalkan permintaan ini.", interrupt=self.fg_active)

    def interrupt_turn(self) -> bool:
        if self.cancel_questions():  # pertanyaan izin yang menunggu dibatalkan (sekaligus menghentikan giliran)
            return True
        return super().interrupt_turn()

    async def choose(self, title: str, labels: list[str]) -> int | None:
        value, _ = await self.ask_web("choice", title, "", [(str(i), lab) for i, lab in enumerate(labels)]
                                      + [("cancel", "Batal")])
        return int(value) if value and value.isdigit() else None

    async def pick_session(self, exclude: str | None = None) -> str | None:
        sessions = session_list(self.repo, exclude)
        if not sessions:
            return None
        i = await self.choose("Lanjutkan percakapan lama di folder ini:", [label for _, label in sessions])
        return sessions[i][0] if i is not None else None

    # --- status untuk browser ---
    def status_snapshot(self) -> dict[str, Any]:
        auto = self.auto_running()
        if self.fg_active:
            working = self.status_text().plain
        elif auto:
            working = f"✻ Claude menanggapi tugas background… ({fmt_dur(time.monotonic() - self.auto_start)} · esc untuk berhenti)"
        else:
            working = ""
        g = self.goal
        return {
            "busy": self.busy() or auto, "working": working, "asking": bool(self.waiters),
            "mode": self.args.mode, "mode_label": MODE_LABEL.get(self.args.mode, self.args.mode), "model": self.args.model,
            "cost": f"${self.cost_total:.4f}", "ctx": None if self.ctx_pct is None else round(self.ctx_pct),
            "goal": (f"🎯 {clip(oneline(g.condition), 60)} · {g.checks} cek" + (" · ⏸ dijeda" if g.paused else "")) if g else "",
            "pending": [label for _, label in list(self.sent_pending)], "queued": list(self.prompt.queue),
            "tasks": [self.task_line(t, 160).plain.strip() for t in self.running_bg()],
            "session": self.session_id or "",
        }

    def hello(self) -> dict[str, Any]:
        return {"repo": str(self.repo), "name": self.repo.name or str(self.repo), "modes": MODE_LABEL,
                "cycle": MODE_CYCLE, "models": MODEL_ALIASES, "windows": WINDOWS}

    def completions(self, text: str) -> list[dict[str, str]]:
        """Saran untuk kolom chat: /perintah di awal baris, @path di mana saja."""
        word = re.search(r"\S*$", text).group(0)  # type: ignore[union-attr]
        if word.startswith("/") and text.lstrip() == word:
            return [{"value": c + " ", "label": c, "meta": clip(self.prompt.commands.get(c) or "", 70)}
                    for c in sorted(self.prompt.commands) if c.startswith(word)][:60]
        if word.startswith("@"):
            with contextlib.suppress(OSError):
                return [{"value": m, "label": m.strip(), "meta": ""} for m in self.prompt.path_matches(word)][:60]
        return []

    async def handle_api(self, action: str, body: dict[str, Any]) -> dict[str, Any]:
        if action == "send":
            text = str(body.get("text") or "").strip()
            if not text:
                return {"ok": False}
            if self.busy():  # Claude bekerja: pesan susulan / antre / perintah ringan, sama seperti di terminal
                self.submit_while_busy(text)
            else:
                self.show_user(text)
                self.prompt.submit(text)
        elif action == "stop":
            self.interrupt_turn()
        elif action == "answer":
            return {"ok": self.answer(str(body.get("id")), body.get("value"), str(body.get("reason") or ""))}
        elif action == "mode":
            mode = str(body.get("mode") or "")
            if mode == "cycle":
                self.cycle_mode()
            elif mode in MODES:
                self.args.mode = mode
                if self.client:
                    asyncio.ensure_future(self._call(self.client.set_permission_mode(mode)))
        elif action == "model":
            model = str(body.get("model") or "")
            model = MODEL_ALIASES.get(model.lower(), model)
            if model and model != self.args.model:
                try:
                    if self.client:
                        await self.client.set_model(model)
                    self.args.model = model
                    console.print(f"[green]✓ Model diganti ke {model}[/]")
                except Exception as e:
                    console.print(f"[red]✗ Gagal mengganti model: {e}[/]")
        elif action == "complete":
            return {"items": self.completions(str(body.get("text") or ""))}
        else:
            return {"ok": False, "error": "unknown action"}
        return {"ok": True}


def build_web_app(ui: WebUI, hub: WebHub, token: str, cookie: str) -> Any:
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
    from starlette.routing import Route

    loopback = {"127.0.0.1", "localhost", "::1"}
    secure_headers = {
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                    "img-src data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                                    "form-action 'none'"),
    }

    def host_ok(request: Any) -> bool:
        host = (request.headers.get("host") or "").lower()
        name = host[1:host.find("]")] if host.startswith("[") else host.rsplit(":", 1)[0]
        if name not in loopback:  # tolak DNS rebinding: nama host harus loopback
            return False
        origin = request.headers.get("origin")
        if origin and (urllib.parse.urlsplit(origin).hostname or "") not in loopback:
            return False
        return True

    def token_ok(value: Any) -> bool:
        return bool(value) and secrets.compare_digest(str(value).encode(), token.encode())

    async def page(request: Any) -> Any:
        if not host_ok(request):
            return PlainTextResponse("forbidden", status_code=403)
        via_url = token_ok(request.query_params.get("t"))
        if not (via_url or token_ok(request.cookies.get(cookie))):
            return HTMLResponse(GUI_LOCKED_HTML, status_code=403, headers=secure_headers)
        html = GUI_HTML.replace("__CCM_TOKEN__", json.dumps(token))
        resp = HTMLResponse(html, headers=secure_headers)
        if via_url:  # reload tanpa token di URL tetap bisa (cookie ini tidak dikirim ke situs lain)
            resp.set_cookie(cookie, token, httponly=True, samesite="strict", path="/")
        return resp

    async def events(request: Any) -> Any:
        if not (host_ok(request) and (token_ok(request.query_params.get("t")) or token_ok(request.cookies.get(cookie)))):
            return PlainTextResponse("forbidden", status_code=403)
        q: asyncio.Queue = asyncio.Queue()
        hub.clients.add(q)

        def sse(ev: dict[str, Any]) -> str:
            return "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"

        async def gen() -> Any:
            try:
                yield sse({"type": "hello", **ui.hello()})
                for ev in list(hub.log):
                    yield sse(ev)
                if hub.status:
                    yield sse(hub.status)
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), 15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    if ev is None:
                        break
                    yield sse(ev)
            finally:
                hub.clients.discard(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    async def api(request: Any) -> Any:
        if not (host_ok(request) and token_ok(request.headers.get("x-ccmini-token"))):
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return JSONResponse(await ui.handle_api(request.path_params["action"], body))

    return Starlette(routes=[Route("/", page), Route("/events", events),
                             Route("/api/{action}", api, methods=["POST"])])


async def start_web_server(make_app: Any, port: int) -> tuple[Any, asyncio.Task, int]:
    """Jalankan uvicorn di event loop ini, di 127.0.0.1. Kalau port terpakai, coba port berikutnya.
    make_app(port) membuat aplikasinya setelah port-nya pasti."""
    import socket

    import uvicorn

    class QuietServer(uvicorn.Server):  # Ctrl+C diurus script ini sendiri, bukan uvicorn
        def install_signal_handlers(self) -> None:
            pass

        @contextlib.contextmanager
        def capture_signals(self) -> Any:
            yield

    sock = None
    for cand in [port, *range(port + 1, port + 20), 0] if port else [0]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if not WINDOWS:  # di Windows SO_REUSEADDR malah membolehkan dua proses memakai port yang sama
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", cand))
        except OSError:
            s.close()
            continue
        sock = s
        break
    if sock is None:
        raise OSError("tidak ada port kosong untuk GUI")
    config = uvicorn.Config(make_app(sock.getsockname()[1]), log_level="warning", access_log=False, lifespan="off", timeout_graceful_shutdown=1)
    server = QuietServer(config)
    task = asyncio.ensure_future(server.serve(sockets=[sock]))
    for _ in range(200):
        if server.started or task.done():
            break
        await asyncio.sleep(0.05)
    if task.done():
        task.result()  # lempar error start-nya
    return server, task, sock.getsockname()[1]


def open_browser(url: str) -> bool:
    """Buka GUI sebagai jendela aplikasi (Edge/Chrome --app: tanpa address bar & tab); kalau tidak ada, browser bawaan."""
    cands: list[Path] = []
    if WINDOWS:
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands += [Path(base) / "Microsoft/Edge/Application/msedge.exe",
                          Path(base) / "Google/Chrome/Application/chrome.exe"]
    elif sys.platform == "darwin":
        cands += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                  Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                  Path("/Applications/Chromium.app/Contents/MacOS/Chromium")]
    else:
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return False  # server tanpa layar: buka lewat SSH tunnel
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                cands.append(Path(found))
    for exe in cands:
        if exe.is_file():
            try:
                subprocess.Popen([str(exe), f"--app={url}"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=not WINDOWS)
                return True
            except OSError:
                continue
    try:
        import webbrowser

        return webbrowser.open(url)
    except Exception:
        return False


async def status_ticker(ui: WebUI, hub: WebHub) -> None:
    """Kirim status (spinner, mode, biaya, antrean, tugas background) ke browser setiap kali berubah."""
    last = None
    while True:
        try:
            snap = ui.status_snapshot()
        except Exception:
            snap = last
        if snap != last:
            hub.emit("status", snap)
            last = snap
        await asyncio.sleep(0.25)


def run_gui(repo: Path, args: argparse.Namespace, resume_id: str | None, continue_last: bool) -> WebUI:
    """Mode --gui: server web lokal + sesi Claude di event loop yang sama, sampai /exit atau Ctrl+C di terminal."""
    global console
    term = console
    hub = WebHub()
    ui = WebUI(repo, args, hub)
    token = secrets.token_urlsafe(24)

    async def main_coro() -> None:
        global console
        hub.loop = asyncio.get_running_loop()
        server = task = None
        try:
            # cookie per port: dua GUI di port berbeda tidak saling menimpa
            server, task, port = await start_web_server(
                lambda p: build_web_app(ui, hub, token, f"ccmini_{p}"), args.port)
            url = f"http://127.0.0.1:{port}/?t={token}"
            opened = not args.no_browser and open_browser(url)
            term.print(f"[bold cyan]✻ claude-code-mini GUI[/] · 📂 {rich_escape(str(repo))}")
            term.print(f"  {url}", soft_wrap=True, highlight=False)
            term.print("[dim]  " + ("Browser sudah dibuka. " if opened else "Buka URL di atas di browser. ")
                       + "Biarkan terminal ini terbuka; Ctrl+C (atau /exit di GUI) untuk berhenti.[/]")
            if not opened:
                term.print(f"[dim]  Di server: jalankan di komputermu  ssh -L {port}:127.0.0.1:{port} user@server  "
                           "lalu buka URL itu di browser.[/]", soft_wrap=True)
            stopping = False

            def request_stop() -> None:  # Ctrl+C pertama: tutup sesi dengan rapi; kedua: paksa
                nonlocal stopping
                if stopping:
                    return
                stopping = True
                term.print("\n[dim]Menutup GUI… (Ctrl+C sekali lagi untuk memaksa)[/]")
                release()
                with contextlib.suppress(ValueError):
                    signal.signal(signal.SIGINT, signal.default_int_handler)
                ui.prompt.abort(EOFError())

            release = on_ctrl_c(asyncio.get_running_loop(), request_stop)
            console = WebConsole(hub.emit)
            ticker = asyncio.ensure_future(status_ticker(ui, hub))
            try:
                rid, cont = resume_id, continue_last
                if rid:
                    show_history(rid, repo)
                while True:
                    action = await session(ui, rid, cont)
                    cont = False
                    done, rid = after_session(ui, action, repo)
                    if done:
                        break
            except BaseException as e:
                if not isinstance(e, (KeyboardInterrupt, asyncio.CancelledError)):
                    text = explain_error(e, args.buffer_mb) if isinstance(e, Exception) else str(e)
                    hub.emit("fatal", {"text": f"claude-code-mini berhenti karena error: {text}"})
                raise
            finally:
                ticker.cancel()
        finally:
            console = term
            hub.emit("bye", {})
            await asyncio.sleep(0.3)
            hub.close()
            if server is not None:
                server.should_exit = True
                with contextlib.suppress(BaseException):
                    await asyncio.wait_for(task, 5)

    try:
        asyncio.run(main_coro())
    except KeyboardInterrupt:
        console = term
        term.print("\n[dim]GUI dihentikan.[/]")
    return ui


def after_session(ui: UI, action: Any, repo: Path) -> tuple[bool, str | None]:
    """Sesudah satu proses Claude selesai: (selesai?, session id untuk proses berikutnya)."""
    if action == "exit":
        return True, None
    if action == "clear":
        had_goal = ui.goal
        ui.reset()
        console.print("[dim]✻ Percakapan baru dimulai (konteks lama dibuang"
                      + (f' · goal "{rich_escape(clip(oneline(had_goal.condition), 60))}" ikut dibatalkan' if had_goal else "")
                      + ")[/]")
        return False, None
    if isinstance(action, tuple) and action[0] == "resume":
        cost, had_goal = ui.cost_total, ui.goal
        ui.reset()
        ui.cost_base = cost
        show_history(action[1], repo)
        console.print("[dim]✻ Percakapan lama dilanjutkan"
                      + (f' · goal "{rich_escape(clip(oneline(had_goal.condition), 60))}" tetap tersimpan di percakapan tadi'
                         if had_goal else "") + "[/]")
        return False, action[1]
    # action == "recover": sambung ulang otomatis, lanjutkan percakapan yang sama
    ui.failures += 1
    if ui.failures > MAX_RECOVERY:
        console.print(f"[red]✗ Gagal pulih setelah {MAX_RECOVERY}x percobaan. Script dihentikan.[/]")
        sys.exit(1)
    ui.on_reconnect()
    if ui.session_id:
        console.print(
            f"[yellow]🔄 Menyambung ulang ({ui.failures}/{MAX_RECOVERY})… percakapan dilanjutkan, "
            "konteks tetap ada.[/]\n[dim]Tugas terakhir terhenti. Ketik 'lanjutkan' untuk meneruskan, "
            "atau beri instruksi lain.[/]"
        )
    else:
        console.print(f"[yellow]🔄 Menyambung ulang ({ui.failures}/{MAX_RECOVERY})… "
                      "(percakapan baru, sesi lama belum sempat tersimpan)[/]")
    return False, ui.session_id


def main() -> None:
    if "--setup" in sys.argv[1:]:  # biasanya sudah ditangani bootstrap(); ini cadangan kalau main() dipanggil langsung
        setup()
        return
    p = argparse.ArgumentParser(prog="claude-code-mini",
                                description="claude-code-mini: Claude Code versi mini via API key (Claude Agent SDK)")
    p.add_argument("repo", nargs="?", default=".", help="folder repo yang dikerjakan (default: folder sekarang)")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"model Claude atau alias {'/'.join(MODEL_ALIASES)} (default: {DEFAULT_MODEL})")
    p.add_argument("--mode", default="acceptEdits", choices=MODES, help="mode izin awal (default: acceptEdits)")
    p.add_argument("--effort", choices=EFFORTS, help="seberapa keras Claude berpikir (default: bawaan model)")
    p.add_argument("--budget", type=float, help="batas biaya maksimal dalam USD, mis. 5")
    p.add_argument("--yolo", action="store_true", help="semua tool jalan tanpa tanya izin - hati-hati!")
    p.add_argument("-c", "--continue", dest="cont", action="store_true", help="lanjutkan percakapan terakhir")
    p.add_argument("-r", "--resume", nargs="?", const="", metavar="SESSION_ID",
                   help="lanjutkan percakapan lama (tanpa ID = pilih dari daftar)")
    p.add_argument("-p", "--print", metavar="PROMPT",
                   help="jalankan satu prompt lalu keluar (exit code: 0 sukses, 1 error, 3 goal belum selesai)")
    p.add_argument("--buffer-mb", type=int, default=DEFAULT_BUFFER_MB,
                   help=f"batas ukuran output tool dalam MB (default: {DEFAULT_BUFFER_MB})")
    p.add_argument("--setup", action="store_true",
                   help="pasang/update library & perintah `claude-code-mini`")
    p.add_argument("--gui", action="store_true",
                   help="buka tampilan GUI di browser (server lokal di 127.0.0.1, tanpa library tambahan)")
    p.add_argument("--port", type=int, default=GUI_PORT,
                   help=f"port GUI (default: {GUI_PORT}; kalau terpakai, dipilih port lain)")
    p.add_argument("--no-browser", action="store_true",
                   help="GUI: jangan buka browser otomatis (mis. di server; buka URL-nya lewat SSH tunnel)")
    args = p.parse_args()
    if args.gui and args.print:
        p.error("--gui tidak bisa digabung dengan -p")
    if args.yolo:
        args.mode = "bypassPermissions"
    args.model = MODEL_ALIASES.get(args.model.lower(), args.model)

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        sys.exit(f"Folder tidak ditemukan: {repo}")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            "[red]ANTHROPIC_API_KEY belum di-set.[/] Script ini sengaja hanya jalan pakai API key "
            "supaya tidak memakai kuota subscription."
        )
        if WINDOWS and win_user_env("ANTHROPIC_API_KEY"):
            console.print("Key-nya sudah tersimpan, tapi belum terbaca di terminal ini: buka terminal baru.")
        elif WINDOWS:
            console.print("Simpan dulu lewat PowerShell (key tidak tampil di layar):")
            console.print(f"  [bold]{rich_escape(key_hint())}[/]", soft_wrap=True)
        else:
            console.print('Jalankan dulu:  [bold]export ANTHROPIC_API_KEY="sk-ant-..."[/]')
        sys.exit(1)

    if not args.print and not args.gui:
        console.print(
            Panel.fit(
                f"[bold]✻ claude-code-mini[/] [dim](Claude Code via API key)[/]\n"
                f"📂 {repo}\n"
                f"🤖 {args.model} · mode: {args.mode}"
                + (f" · effort: {args.effort}" if args.effort else "")
                + (f" · budget: ${args.budget}" if args.budget else "")
                + "\n[dim]? bantuan · ! shell · @ file · # memori · Esc menghentikan Claude[/]",
                border_style="cyan",
            )
        )
    if args.mode == "bypassPermissions":
        console.print("[bold red]⚠ Mode YOLO: Claude bisa menjalankan command apa pun tanpa bertanya.[/]")
        if hasattr(os, "geteuid") and os.geteuid() == 0 and not os.environ.get("IS_SANDBOX"):
            console.print(
                "[yellow]Catatan: Claude Code menolak mode YOLO kalau dijalankan sebagai root/sudo.[/]\n"
                "[dim]Jalankan sebagai user biasa, atau kalau ini memang container/VM sekali pakai: "
                "IS_SANDBOX=1 claude-code-mini … --yolo[/]"
            )

    keep_awake()
    resume_id: str | None = None
    continue_last = args.cont
    if args.resume is not None:
        resume_id = args.resume or pick_session(repo)
        if not resume_id:
            sys.exit(0)

    ui: UI | None = None
    try:
        if args.gui:
            ui = run_gui(repo, args, resume_id, continue_last)
        else:
            ui = UI(repo, args)
            if resume_id:
                show_history(resume_id, repo)
            while True:
                action = asyncio.run(session(ui, resume_id, continue_last))
                continue_last = False
                done, resume_id = after_session(ui, action, repo)
                if done:
                    break
    except WrongAuthSource as e:
        console.print(
            f"\n[bold red]✗ Dihentikan: Claude memakai auth '{e}', bukan ANTHROPIC_API_KEY.[/]\n"
            "Biar tidak memotong kuota subscription / salah tagihan, cek lagi environment variable-nya."
        )
        sys.exit(1)
    except CLINotFoundError:
        console.print("[red]Binary Claude Code tidak ditemukan.[/] Coba pasang ulang: "
                      f"{self_command()} --setup")
        sys.exit(1)
    except StartFailed as e:
        console.print(
            f"[red]✗ Mesin Claude Code gagal start:[/] {clip(str(e), 300)}\n"
            "[dim]Cek: koneksi internet/proxy ke api.anthropic.com, ANTHROPIC_API_KEY valid, "
            f"lalu update dengan: {self_command()} --setup\n"
            "Detail error dari mesin Claude (kalau ada) tampil di atas pesan ini.[/]"
        )
        sys.exit(1)
    except ClaudeSDKError as e:
        console.print(f"[red]Error SDK: {e}[/]")
        sys.exit(1)
    except KeyboardInterrupt:
        pass

    if ui is None:
        return
    gui = " --gui" if args.gui else ""
    if ui.session_id and not args.print:
        console.print(f"[dim]Total biaya: ${ui.cost_total:.4f} · Lanjutkan nanti dengan:[/]"
                      + ("  [dim](goal aktif ikut dipulihkan)[/]" if ui.goal else ""))
        console.print(f"  {self_command()} {quote_arg(str(repo))}{gui} --resume {ui.session_id}", soft_wrap=True)
    elif not args.print:
        console.print("[dim]Sampai jumpa 👋[/]")
    if ui.exit_code:
        sys.exit(ui.exit_code)


if __name__ == "__main__":
    main()
