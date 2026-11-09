"""Tes end-to-end claude-code-mini: mesin Claude Code asli + API tiruan (fakeapi.py), tanpa API key dan tanpa biaya.

Mencakup --setup (perintah claude-code-mini), mode -p (exit code, output UTF-8, izin tanpa terminal, Ctrl+C/Esc)
dan tampilan interaktif yang dijalankan di pseudo-terminal (term.py): izin, mengetik saat Claude bekerja, Esc,
Shift+Tab, !command, @file, keluar. Jalan di Windows, Linux, dan macOS (CI: .github/workflows/tests.yml).

    python tests/e2e.py            # semua tes (jalankan setelah `claude-code-mini.py --setup`)
    python tests/e2e.py --nogit    # Windows tanpa Git Bash: Claude harus memakai tool PowerShell
Butuh: pyte + ptyprocess (Linux/macOS) atau pyte + pywinpty (Windows).
Env:
    CCMINI_APP   perintah aplikasi sebagai JSON list (bawaan: ~/.local/bin/claude-code-mini[.exe]; tes --setup
                 dilewati kalau diisi)
    CCMINI_OUT   folder log dan repo tes (bawaan: ./test-out)
Aplikasi dijalankan dengan HOME (Windows: USERPROFILE) di dalam folder log, jadi riwayat ketikan dan percakapan
asli tidak tersentuh.
"""
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from term import Term  # noqa: E402

WIN = os.name == "nt"
for _s in (sys.stdout, sys.stderr):  # runner Windows: cp1252, tidak bisa mencetak ✓ / ⏹
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
OUT = Path(os.environ.get("CCMINI_OUT") or Path.cwd() / "test-out").resolve()
OUT.mkdir(parents=True, exist_ok=True)
LAUNCHER = Path.home() / ".local" / "bin" / ("claude-code-mini.exe" if WIN else "claude-code-mini")
APP = json.loads(os.environ["CCMINI_APP"]) if os.environ.get("CCMINI_APP") else [str(LAUNCHER)]
REPO = OUT / "repo"
APP_HOME = OUT / "home"  # HOME untuk aplikasi: riwayat ketikan & percakapan tes tidak bercampur dengan yang asli
APP_HOME.mkdir(parents=True, exist_ok=True)
PY = "python" if WIN else "python3"  # untuk command yang butuh izin (echo diizinkan otomatis oleh Claude Code)
fails: list[str] = []
results: list[str] = []


def check(name, cond, info=""):
    line = ("ok   " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else "")
    print(line, flush=True)
    results.append(line)
    if not cond:
        fails.append(name)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = free_port()


def start_fake():
    p = subprocess.Popen([sys.executable, str(HERE / "fakeapi.py"), str(PORT), str(OUT / "fakeapi.log")],
                         stdout=subprocess.DEVNULL, stderr=open(OUT / "fakeapi.err", "w"))
    for _ in range(100):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                return p
        time.sleep(0.1)
    raise RuntimeError("fakeapi tidak jalan")


def env(isolate=True, **extra):
    e = dict(os.environ)
    e.update(ANTHROPIC_API_KEY="sk-ant-fake-test-key", ANTHROPIC_BASE_URL=f"http://127.0.0.1:{PORT}",
             CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", CCMINI_NO_CAFFEINATE="1", TERM="xterm-256color",
             PYTHONIOENCODING="")
    e.pop("PYTHONIOENCODING")
    if isolate:
        e["USERPROFILE" if WIN else "HOME"] = str(APP_HOME)
    for k, v in extra.items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = v
    return e


def run_p(prompt, *args, extra_env=None, timeout=180):
    r = subprocess.run(APP + [str(REPO), "--model", "haiku", *args, "-p", prompt], env=env(**(extra_env or {})),
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    return r.returncode, out


def make_repo():
    REPO.mkdir(parents=True, exist_ok=True)
    (REPO / "halo.py").write_text('def halo():\n    return "halo"\n', encoding="utf-8")
    try:
        subprocess.run(["git", "init", "-q"], cwd=REPO, capture_output=True)
    except OSError:  # tes tanpa Git
        pass


SLEEP = r"(Bash\(sleep \d\)|PowerShell\(Start-Sleep -Seconds \d\))"


# ---------------------------------------------------------------- setup
def test_setup():
    if os.environ.get("CCMINI_APP"):  # aplikasi dijalankan dengan perintah lain, bukan launcher hasil --setup
        return
    check("S1 perintah claude-code-mini ada setelah --setup", LAUNCHER.is_file(), str(LAUNCHER))
    r = subprocess.run([str(LAUNCHER), "--help"], capture_output=True, timeout=120)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    check("S2 claude-code-mini --help", r.returncode == 0 and "usage: claude-code-mini" in out, out[-300:])
    # --setup lewat perintahnya sendiri. Windows: .exe yang sedang jalan harus bisa diganti, pip tidak boleh terkunci
    r = subprocess.run([str(LAUNCHER), "--setup"], capture_output=True, timeout=900)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    (OUT / "setup2.txt").write_text(out, encoding="utf-8")
    check("S3 claude-code-mini --setup lewat perintahnya sendiri",
          r.returncode == 0 and "Perintah claude-code-mini dibuat" in out and LAUNCHER.is_file(), out[-600:])
    if WIN:
        check("S4 pesan setup Windows (mesin, shell, PATH/key)",
              "Mesin Claude Code" in out and ("Git Bash" in out or "PowerShell" in out), out[-600:])
    r = subprocess.run([str(LAUNCHER), "--help"], capture_output=True, timeout=120)
    check("S5 perintah hasil setup ulang jalan", r.returncode == 0)


# ---------------------------------------------------------------- mode -p
def test_print_mode():
    rc, out = run_p("tes [[sh:echo halo-p]]", "--yolo")
    (OUT / "p1.txt").write_text(out, encoding="utf-8")
    check("P1 -p tool shell + jawaban, exit 0", rc == 0 and "halo-p" in out and "SELESAI" in out, f"rc={rc} {out[-400:]}")
    rc, out = run_p(f'[[sh:{PY} -c "print(5)"]]')
    (OUT / "p2.txt").write_text(out, encoding="utf-8")
    check("P2 -p izin tanpa terminal -> exit 1", rc == 1 and "tidak ada terminal" in out, f"rc={rc} {out[-400:]}")
    rc, out = run_p("[[say:✓ héllo 🎯 selesai]]")
    (OUT / "p3.txt").write_text(out, encoding="utf-8")
    check("P3 -p output Unicode ke pipe (UTF-8)", rc == 0 and "✓ héllo 🎯 selesai" in out, f"rc={rc} {out[-300:]}")
    rc, out = run_p("[[say:x]]", extra_env={"ANTHROPIC_API_KEY": None})
    check("P4 tanpa API key -> exit 1 + petunjuk",
          rc == 1 and "ANTHROPIC_API_KEY belum di-set" in out and (not WIN or "Read-Host" in out or "terminal baru" in out),
          f"rc={rc} {out[-400:]}")
    if WIN:
        rc, out = run_p("[[ps:Write-Output hai-ps]]", "--yolo", extra_env={"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"})
        (OUT / "p5.txt").write_text(out, encoding="utf-8")
        check("P5 tool PowerShell tampil seperti Bash", rc == 0 and "PowerShell(Write-Output hai-ps)" in out
              and "hai-ps" in out.split("PowerShell(Write-Output hai-ps)")[-1], f"rc={rc} {out[-500:]}")
    if WIN:
        # Dijalankan langsung dari folder clone dengan Python sistem: script menjalankan ulang dirinya di venv sebagai
        # proses anak (os.execv tidak bisa di Windows). Exit code harus diteruskan; pencegah sleep ikut aktif di sini.
        script = str(HERE.parent / "claude-code-mini.py")
        e = env(isolate=False, CCMINI_NO_CAFFEINATE=None)  # butuh venv di HOME asli
        r = subprocess.run([sys.executable, script, str(REPO), "--model", "haiku", "-p", "[[say:lewat-venv]]"], env=e,
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=180)
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
        check("P8 py claude-code-mini.py -> jalan ulang di venv, exit 0", r.returncode == 0 and "lewat-venv" in out,
              f"rc={r.returncode} {out[-400:]}")
        r = subprocess.run([sys.executable, script, str(REPO), "-p", "[[say:x]]"], env=env(False, ANTHROPIC_API_KEY=None),
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=180)
        check("P9 exit code dari proses venv diteruskan (tanpa key -> 1)", r.returncode == 1, f"rc={r.returncode}")
    # percakapan lanjutan (-c): biaya lama yang dipulihkan mesin bukan pengeluaran run ini
    run_p("[[say:biaya-satu]]")
    rc, out = run_p("[[say:biaya-dua]]", "-c")
    (OUT / "p10.txt").write_text(out, encoding="utf-8")
    m = re.search(r"biaya:\s*\$([\d.]+)\s*·\s*total\s+sesi:\s*\$([\d.]+)", out)
    check("P10 -c: biaya lama tidak dihitung lagi (satu baris Selesai, total sesi = biaya giliran)",
          rc == 0 and out.count("Selesai") == 1 and m is not None and m.group(1) == m.group(2) and float(m.group(1)) > 0,
          f"rc={rc} {out[-500:]}")
    # Ctrl+C dan Esc di mode -p (butuh terminal): exit 130
    for name, keyname in (("P6 -p Ctrl+C -> exit 130", "C-c"), ("P7 -p Esc -> exit 130", "Escape")):
        t = Term(APP + [str(REPO), "--model", "haiku", "--yolo", "-p", "[[sleep:4:3]]"], env=env(),
                 log=str(OUT / f"{name[:2]}.raw"))
        try:
            t.wait(SLEEP, timeout=90)
            time.sleep(1.0)
            t.key(keyname)
            ended = t.wait_exit(40)
            code = t.exitstatus()
            hist = t.history()
            check(name, ended and code == 130 and "Dihentikan oleh user" in hist, f"ended={ended} code={code}\n{t.screen_text()[-500:]}")
        except Exception as e:
            check(name, False, str(e)[-500:])
        finally:
            (OUT / f"{name[:2]}.screen.txt").write_text(t.history(), encoding="utf-8")
            t.kill()


# ---------------------------------------------------------------- interaktif
def test_interactive():
    t = Term(APP + [str(REPO), "--model", "haiku"], env=env(), log=str(OUT / "tui.raw"))
    try:
        t.wait(r"shift\+tab", timeout=90)
        time.sleep(1.0)
        check("I1 prompt + toolbar tampil", t.has(r"(?m)^›") and t.has(r"shift\+tab"), t.screen_text()[-300:])

        t.type("[[sh:echo halo-tui]]")
        t.key("Enter")
        t.wait(r"✓ Selesai", timeout=90)
        check("I2 tool shell + jawaban", t.count(r"halo-tui") >= 2 and t.count("SELESAI") >= 1, t.screen_text()[-600:])
        check("I2b baris 'Terhubung'", t.count(r"Terhubung · model") == 1)

        n = t.count(r"✓ Selesai")
        t.type(f'[[sh:{PY} -c "print(12345)"]]')
        t.key("Enter")
        t.wait(r"Claude minta izin", timeout=90)
        time.sleep(0.5)
        t.type("1")
        t.key("Enter")
        t.wait(r"✓ Selesai", after=n, timeout=90)
        check("I3 panel izin -> jawab 1 -> command jalan", t.count(r"12345") >= 2, t.screen_text()[-600:])

        nperm = t.count(r"Claude minta izin")
        t.type(f'[[sh:{PY} -c "print(67890)"]]')
        t.key("Enter")
        t.wait(r"Claude minta izin", after=nperm, timeout=90)
        time.sleep(0.8)
        t.key("C-c")
        t.wait(r"dibatalkan \(Ctrl\+C\)", timeout=30)
        t.wait(r"Dihentikan oleh user", timeout=60)
        time.sleep(1.0)
        n = t.count(r"✓ Selesai")
        t.type("[[say:masih-hidup]]")
        t.key("Enter")
        t.wait(r"✓ Selesai", after=n, timeout=90)
        hist = t.history()
        check("I4 Ctrl+C di pertanyaan izin: dibatalkan, mesin Claude tetap hidup",
              "masih-hidup" in hist and "Menyambung ulang" not in hist and "koneksi tertutup" not in hist,
              t.screen_text()[-600:])

        # pesan susulan saat Claude bekerja
        n, ns = t.count(r"✓ Selesai"), t.count(SLEEP)
        t.type("[[sleep:3:3]]")
        t.key("Enter")
        t.wait(SLEEP, after=ns, timeout=90)
        try:  # prompt + toolbar digambar ulang sesaat setelah output tool dicetak di atasnya
            t.wait_screen(r"esc untuk berhenti", timeout=10)
            check("I5a spinner di toolbar saat bekerja", True)
        except TimeoutError as e:
            check("I5a spinner di toolbar saat bekerja", False, str(e)[-400:])
        t.type("[[say:42]]")
        t.key("Enter")
        t.wait(r"› \[\[say:42\]\]", timeout=60)
        t.wait(r"✓ Selesai", after=n, timeout=90)
        time.sleep(0.8)
        hist = t.history()
        check("I5b pesan susulan dibaca Claude, satu giliran", "42" in hist.split("› [[say:42]]")[-1]
              and t.count(r"✓ Selesai") == n + 1, t.screen_text()[-600:])

        # /cost langsung saat bekerja, lalu Esc
        nd, ns = t.count(r"Dihentikan oleh user"), t.count(SLEEP)
        t.type("[[sleep:3:3]]")
        t.key("Enter")
        t.wait(SLEEP, after=ns, timeout=90)
        t.type("/cost")
        t.key("Enter")
        t.wait(r"Total biaya sesi ini", timeout=30)
        check("I6 /cost langsung dijalankan saat Claude bekerja", t.has(r"esc untuk berhenti"), t.screen_text()[-400:])
        t.key("Escape")
        t.wait(r"Menghentikan Claude", timeout=30)
        t.wait(r"Dihentikan oleh user", after=nd, timeout=60)
        check("I7 Esc menghentikan Claude", True)
        time.sleep(1.0)

        # !command lewat shell lokal
        if WIN:
            t.type('!Write-Output "halo shell"; Write-Output "héllo ✓"')
        else:
            t.type('!echo "halo shell"; echo "héllo ✓"')
        t.key("Enter")
        t.wait(r"⎿ halo shell", timeout=60)
        time.sleep(0.5)
        check("I8 !command (PowerShell di Windows), kutip & UTF-8 utuh", t.count(r"héllo ✓") >= 2, t.screen_text()[-400:])

        # @file
        n = t.count(r"✓ Selesai")
        t.type("lihat @halo.py [[say:ok-file]]")
        t.key("Enter")
        t.wait(r"✓ Selesai", after=n, timeout=90)
        check("I9 @file dilampirkan", t.count(r"Melampirkan @halo\.py") >= 1 and t.count("ok-file") >= 2,
              t.screen_text()[-400:])

        # Shift+Tab mengganti mode izin, Ctrl+C sekali di prompt kosong = peringatan
        time.sleep(1.0)
        t.key("BTab")
        try:
            t.wait_screen(r"plan mode", timeout=10)
            t.key("BTab")
            t.wait_screen(r"tanya dulu sebelum edit", timeout=10)
            t.key("BTab")
            t.wait_screen(r"auto-terima edit", timeout=10)
            check("I11 Shift+Tab mengganti mode izin", True)
        except TimeoutError as e:
            check("I11 Shift+Tab mengganti mode izin", False, str(e)[-400:])
        t.key("C-c")
        try:
            t.wait(r"tekan Ctrl\+C sekali lagi untuk keluar", timeout=10)
            check("I12 Ctrl+C di prompt: peringatan, belum keluar", t.alive())
        except TimeoutError as e:
            check("I12 Ctrl+C di prompt: peringatan, belum keluar", False, str(e)[-400:])

        # keluar
        time.sleep(2.5)  # lewat jendela 2 detik Ctrl+C ganda
        t.key("C-d")
        ended = t.wait_exit(30)
        hist = t.history()
        check("I10 Ctrl+D keluar (exit 0) + petunjuk --resume", ended and t.exitstatus() == 0
              and "Lanjutkan nanti dengan" in hist, f"ended={ended} code={t.exitstatus()} {t.screen_text()[-300:]}")
    except Exception as e:
        check("interaktif (exception)", False, str(e)[-1500:])
    finally:
        (OUT / "tui.screen.txt").write_text(t.history(), encoding="utf-8")
        t.kill()


def test_nogit():
    """Windows tanpa Git Bash (folder Git disingkirkan oleh workflow): Claude Code harus memakai tool PowerShell."""
    rc, out = run_p("[[sh:Write-Output tanpa-git-bash]]", "--yolo")
    (OUT / "nogit.txt").write_text(out, encoding="utf-8")
    check("G1 tanpa Git Bash: tool PowerShell dipakai + catatan di header",
          rc == 0 and "PowerShell(Write-Output tanpa-git-bash)" in out and "lewat PowerShell" in out, f"rc={rc} {out[-600:]}")


def main():
    make_repo()
    fake = start_fake()
    try:
        if "--nogit" in sys.argv:
            test_nogit()
        else:
            test_setup()
            test_print_mode()
            test_interactive()
    finally:
        fake.terminate()
    (OUT / "results.txt").write_text("\n".join(results) + f"\nFAILS: {fails or 'none'}\n", encoding="utf-8")
    print("\nFAILS:", fails or "none", flush=True)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
