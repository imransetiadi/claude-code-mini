"""Tes installer sekali jalan: install.sh (macOS/Linux) dan install.ps1 (Windows).

1. Installer dari checkout ini dijalankan di pseudo-terminal dengan HOME (Windows: USERPROFILE) baru di dalam folder
   log dan API palsu (fakeapi.py, termasuk GET /v1/models untuk cek key). Yang diketik: teks yang bukan key, key yang
   ditolak, lalu key yang benar. Dicek: tidak ada key yang tampil di layar, key tersimpan (file 600 / environment
   variable user), PATH ditambahkan, dan perintah claude-code-mini yang terpasang jalan (-p) dengan PATH dan key dari
   konfigurasi yang disimpan installer.
2. Installer dijalankan lagi tanpa terminal (= update): tidak bertanya lagi dan tidak menggandakan apa pun. Dengan
   --download, run kedua memakai perintah dari README (`curl … | bash` / `irm … | iex`) dan mengunduh dari GitHub
   pada commit GITHUB_SHA.

    python tests/install.py [--download]
Butuh pyte + ptyprocess (Linux/macOS) atau pyte + pywinpty (Windows). Di Windows installer menulis PATH dan
ANTHROPIC_API_KEY ke environment variable user (registry), jadi tes ini hanya jalan di CI (GITHUB_ACTIONS) kecuali
diberi --force; nilai lamanya dipulihkan sesudahnya.
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import e2e  # noqa: E402
from e2e import OUT, PORT, WIN, check, fails, start_fake  # noqa: E402
from term import Term  # noqa: E402

if WIN:
    import winreg

ROOT = HERE.parent
HOMEDIR = OUT / "install-home"
KEY_OK = "sk-ant-fake-installer-0123456789abcdef"
KEY_BAD = "sk-ant-api03-ditolak-0123456789abcdef"  # fakeapi menolaknya (401)
NOT_KEY = "halo-ini-bukan-api-key"
SHELL = "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"
RC = HOMEDIR / (".zshrc" if sys.platform == "darwin" else ".bashrc")
MARK = "# >>> claude-code-mini >>>"
BIN = HOMEDIR / ".local" / "bin"
LAUNCHER = BIN / ("claude-code-mini.exe" if WIN else "claude-code-mini")
KEY_FILE = HOMEDIR / ".config" / "claude-code-mini" / "api_key"


# ---------------------------------------------------------------- environment variable user (Windows)
def reg_get(name):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
        try:
            return winreg.QueryValueEx(k, name)  # (nilai mentah, jenis)
        except FileNotFoundError:
            return None


def reg_restore(name, saved):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        if saved is None:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(k, name, 0, saved[1], saved[0])


def user_path_entries():
    raw = (reg_get("Path") or ("", 0))[0]
    return [os.path.expandvars(p).rstrip("\\").lower() for p in raw.split(";") if p]


# ---------------------------------------------------------------- menjalankan installer
def inst_env(**extra):
    e = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "CCMINI_SOURCE", "CCMINI_NEW_KEY", "CCMINI_PYTHON", "CCMINI_REF", "CCMINI_REPO",
              "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_BIN_HOME", "ZDOTDIR"):
        e.pop(k, None)
    e.update(ANTHROPIC_BASE_URL=f"http://127.0.0.1:{PORT}", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
             CCMINI_NO_CAFFEINATE="1", TERM="xterm-256color")
    # PATH tanpa .local/bin milik HOME asli: perintah yang dipakai tes pasti hasil instalasi ini
    e["PATH"] = os.pathsep.join(p for p in e.get("PATH", "").split(os.pathsep)
                                if not re.search(r"[\\/]\.local[\\/]bin[\\/]?$", p))
    if WIN:
        e["USERPROFILE"] = str(HOMEDIR)
    else:
        e["HOME"] = str(HOMEDIR)
        e["SHELL"] = SHELL
        if (Path.home() / ".pyenv").is_dir():  # shim pyenv mencari Python-nya di $HOME/.pyenv
            e.setdefault("PYENV_ROOT", str(Path.home() / ".pyenv"))
    e.update(extra)
    return e


def installer_cmd():
    if WIN:
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install.ps1")]
    return ["bash", str(ROOT / "install.sh")]


def run_installed(prompt):
    """Perintah claude-code-mini yang terpasang, dengan PATH dan API key dari yang disimpan installer."""
    e2e.make_repo()
    if WIN:
        env = inst_env(ANTHROPIC_API_KEY=(reg_get("ANTHROPIC_API_KEY") or ("", 0))[0])
        env["PATH"] = os.path.expandvars((reg_get("Path") or ("", 0))[0]) + ";" + env["PATH"]
        exe = shutil.which("claude-code-mini", path=env["PATH"]) or "claude-code-mini"
        cmd = [exe, str(e2e.REPO), "--model", "haiku", "-p", prompt]
    else:  # shell baru yang memuat file startup hasil installer (tanpa ANTHROPIC_API_KEY dari luar)
        env = inst_env()
        cmd = [SHELL, "-c", f'. "{RC}" && claude-code-mini "$0" --model haiku -p "$1"', str(e2e.REPO), prompt]
    r = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")


def test_interactive():
    t = Term(installer_cmd(), rows=50, cols=200, env=inst_env(), cwd=str(HOMEDIR), log=str(OUT / "install1.raw"))
    try:
        t.wait(r"Tempel API key", timeout=900)  # Python dicari, --setup memasang library, baru key ditanya
        t.type(NOT_KEY)
        t.key("Enter")
        t.wait(r"bukan API key", timeout=30)
        t.wait(r"Tempel API key", after=1, timeout=30)
        t.type(KEY_BAD)
        t.key("Enter")
        t.wait(r"ditolak Anthropic \(401\)", timeout=60)
        t.wait(r"Tempel API key", after=2, timeout=30)
        t.type(KEY_OK)
        t.key("Enter")
        t.wait(r"siap dipakai", timeout=120)
        t.wait_exit(60)
        code = t.exitstatus()
        out = t.history()
    except TimeoutError as e:
        code, out = None, t.history()
        check("N0 installer interaktif sampai selesai", False, str(e)[-1500:])
    finally:
        t.kill()
    (OUT / "install1.txt").write_text(out, encoding="utf-8")
    check("N1 installer: Python ditemukan, --setup, perintah claude-code-mini dibuat (exit 0)",
          code == 0 and "Python 3." in out and LAUNCHER.is_file(), f"exit {code}: {out[-1500:]}")
    check("N2 teks yang bukan key ditolak, key yang salah ditolak Anthropic (401)",
          "bukan API key" in out and "ditolak Anthropic (401)" in out and "Key diterima Anthropic" in out, out[-1500:])
    check("N3 key tidak pernah tampil di layar", not any(s in out for s in (KEY_OK, KEY_BAD, NOT_KEY)))
    check("N4 petunjuk PATH/key dari --setup tidak muncul (diurus installer)",
          "belum ada di PATH" not in out and "ANTHROPIC_API_KEY belum di-set" not in out, out[-1500:])
    if WIN:
        val = reg_get("ANTHROPIC_API_KEY")
        check("N5 key tersimpan sebagai environment variable user", val is not None and val[0] == KEY_OK)
        check("N6 ~\\.local\\bin masuk PATH user sebagai REG_EXPAND_SZ",
              user_path_entries().count(str(BIN).lower()) == 1 and reg_get("Path")[1] == winreg.REG_EXPAND_SZ,
              str(reg_get("Path")))
    else:
        mode = stat.S_IMODE(KEY_FILE.stat().st_mode) if KEY_FILE.exists() else 0
        check("N5 key tersimpan di ~/.config/claude-code-mini/api_key, hanya bisa dibaca pemiliknya",
              KEY_FILE.exists() and KEY_FILE.read_text().strip() == KEY_OK and mode == 0o600, oct(mode))
        rc = RC.read_text() if RC.exists() else ""
        check(f"N6 blok PATH + API key di ~/{RC.name}", rc.count(MARK) == 1, rc[-600:])
    rc, out = run_installed("[[say:halo dari installer]]")
    check("N7 perintah terpasang jalan dengan PATH dan key dari installer (-p)",
          rc == 0 and "halo dari installer" in out, out[-800:])


def test_again(download):
    env = inst_env()
    cmd = installer_cmd()
    if download:
        repo, sha = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_SHA")
        base = f"https://raw.githubusercontent.com/{repo}/{sha}"
        try:
            urllib.request.urlopen(f"{base}/install.sh", timeout=30).close()
        except Exception as e:  # mis. commit dari fork, atau dijalankan di luar GitHub Actions
            print(f"skip N9: {base} tidak bisa diunduh ({e})", flush=True)
            download = False
        else:
            env.update(CCMINI_REF=sha, CCMINI_REPO=repo)
            if WIN:
                ps = "pwsh" if shutil.which("pwsh") else "powershell.exe"
                cmd = [ps, "-NoProfile", "-Command", f"irm {base}/install.ps1 | iex"]
            else:
                cmd = ["bash", "-c", f"curl -fsSL {base}/install.sh | bash"]
    # tanpa terminal (start_new_session: tidak ada /dev/tty) -> installer tidak boleh bertanya apa pun
    r = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=900, cwd=str(HOMEDIR),
                       **({} if WIN else {"start_new_session": True}))
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    (OUT / "install2.txt").write_text(out, encoding="utf-8")
    check("N8 installer lagi tanpa terminal (update): selesai, key tidak ditanya lagi",
          r.returncode == 0 and "siap dipakai" in out and "sudah tersimpan" in out and "Tempel API key" not in out,
          out[-1500:])
    if download:
        check("N9 lewat perintah README: claude-code-mini.py diunduh dari GitHub", "Mengunduh claude-code-mini.py" in out,
              out[-800:])
    if WIN:
        check("N10 tidak ada yang digandakan (PATH user)", user_path_entries().count(str(BIN).lower()) == 1)
    else:
        check("N10 tidak ada yang digandakan (blok di file startup)", RC.read_text().count(MARK) == 1)
    rc, out = run_installed("[[say:masih jalan setelah update]]")
    check("N11 perintah terpasang masih jalan setelah update", rc == 0 and "masih jalan setelah update" in out,
          out[-800:])


def test_bash_on_windows():
    """install.sh di terminal bash Windows (Git Bash; MobaXterm/Cygwin serupa): harus mengarahkan ke PowerShell."""
    bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
    if not bash.exists():
        print("skip N12: Git Bash tidak ada", flush=True)
        return
    r = subprocess.run([str(bash), (ROOT / "install.sh").as_posix()], env=inst_env(), stdin=subprocess.DEVNULL,
                       capture_output=True, timeout=120)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    check("N12 install.sh di Git Bash: berhenti dan mengarahkan ke PowerShell (irm … | iex)",
          r.returncode == 1 and "terminal bash di Windows" in out and "install.ps1 | iex" in out, out[-800:])


def main():
    if WIN and not (os.environ.get("GITHUB_ACTIONS") or "--force" in sys.argv):
        print("skip: di Windows tes ini mengubah environment variable user; jalankan di CI atau dengan --force")
        return
    shutil.rmtree(HOMEDIR, ignore_errors=True)  # folder milik tes ini sendiri: instalasi harus mulai dari nol
    HOMEDIR.mkdir(parents=True)
    saved = {n: reg_get(n) for n in ("Path", "ANTHROPIC_API_KEY")} if WIN else {}
    fake = start_fake()
    try:
        test_interactive()
        test_again("--download" in sys.argv)
        if WIN:
            test_bash_on_windows()
    finally:
        fake.terminate()
        for name, value in saved.items():
            reg_restore(name, value)
    print("FAILS:", ", ".join(fails) if fails else "none")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
