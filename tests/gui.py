"""Tes GUI claude-code-mini (--gui): server web lokalnya diuji lewat HTTP + Server-Sent Events, dengan mesin Claude
Code asli dan API tiruan (fakeapi.py). Tanpa browser dan tanpa API key; tampilannya sendiri dicek manual.

    python tests/gui.py      (jalankan setelah `claude-code-mini.py --setup`; butuh pyte + ptyprocess/pywinpty)
Env sama dengan tests/e2e.py (CCMINI_APP, CCMINI_OUT).
"""
import http.client
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import e2e  # noqa: E402
from e2e import APP, OUT, PY, REPO, check, env, make_repo, start_fake  # noqa: E402
from term import Term  # noqa: E402

URL_RE = re.compile(r"http://127\.0\.0\.1:(\d+)/\?t=([\w-]+)")


class Gui:
    """claude-code-mini --gui sebagai proses anak + klien SSE yang mencatat semua event."""

    def __init__(self):
        self.proc = subprocess.Popen(APP + [str(REPO), "--model", "haiku", "--gui", "--no-browser", "--port", "0"],
                                     env=env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
        self.out: list[str] = []
        self.events: list[dict] = []
        threading.Thread(target=self._pump, daemon=True).start()
        end = time.time() + 60
        m = None
        while time.time() < end and not m:
            m = URL_RE.search("".join(self.out))
            time.sleep(0.1)
        if not m:
            raise RuntimeError("GUI tidak memberi URL:\n" + "".join(self.out)[-1500:])
        self.port, self.token = int(m.group(1)), m.group(2)
        threading.Thread(target=self._sse, daemon=True).start()
        self.wait(lambda e: e["type"] == "status", 30)

    def _pump(self):
        for raw in iter(self.proc.stdout.readline, b""):
            self.out.append(raw.decode("utf-8", "replace"))

    def _sse(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=600)
        conn.request("GET", "/events?t=" + self.token)
        resp = conn.getresponse()
        buf = b""
        while True:
            try:
                chunk = resp.read1(65536)
            except (http.client.HTTPException, OSError):  # server ditutup
                break
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf:
                block, buf = buf.split(b"\n\n", 1)
                for line in block.decode("utf-8", "replace").splitlines():
                    if line.startswith("data: "):
                        self.events.append(json.loads(line[6:]))

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        data = r.read().decode("utf-8", "replace")
        conn.close()
        return r.status, data

    def api(self, action, body=None):
        status, data = self.request("POST", "/api/" + action, json.dumps(body or {}),
                                    {"Content-Type": "application/json", "X-CCMini-Token": self.token})
        return json.loads(data) if status == 200 else {"status": status}

    def mark(self):
        return len(self.events)

    def wait(self, pred, timeout=60, after=0):
        end = time.time() + timeout
        while time.time() < end:
            for ev in self.events[after:]:
                if pred(ev):
                    return ev
            if self.proc.poll() is not None and not any(pred(ev) for ev in self.events[after:]):
                break
            time.sleep(0.1)
        raise TimeoutError("event tidak muncul; event terakhir: "
                           + json.dumps(self.events[-6:], ensure_ascii=False)[-1500:])

    def logs(self, after=0):
        return "".join(e.get("html", "") for e in self.events[after:] if e["type"] == "log")

    def turn_done(self, after, timeout=90):
        return self.wait(lambda e: e["type"] == "log" and ("Selesai" in e["html"] or "Dihentikan" in e["html"]
                                                          or "Berhenti" in e["html"]), timeout, after)


def is_type(etype, **match):
    def pred(ev):
        return ev["type"] == etype and all(v in str(ev.get(k, "")) for k, v in match.items())
    return pred


def test_security(g):
    status, _ = g.request("GET", "/")
    check("G1a halaman tanpa token -> 403", status == 403, str(status))
    status, body = g.request("GET", "/?t=" + g.token)
    check("G1b halaman dengan token -> 200", status == 200 and "claude-code-mini" in body, str(status))
    status, _ = g.request("GET", "/?t=" + g.token, headers={"Host": "evil.example:%d" % g.port})
    check("G1c Host bukan loopback (DNS rebinding) -> 403", status == 403, str(status))
    status, _ = g.request("POST", "/api/send", json.dumps({"text": "x"}), {"Content-Type": "application/json"})
    check("G1d API tanpa header token -> 403", status == 403, str(status))
    status, _ = g.request("POST", "/api/send", json.dumps({"text": "x"}),
                          {"Content-Type": "application/json", "X-CCMini-Token": g.token, "Origin": "https://evil.example"})
    check("G1e API dari Origin lain -> 403", status == 403, str(status))
    status, _ = g.request("GET", "/events")
    check("G1f SSE tanpa token -> 403", status == 403, str(status))


def test_flow(g):
    items = g.api("complete", {"text": "lihat @hal"}).get("items", [])
    check("G2 saran @path", any(i["label"] == "@halo.py" for i in items), json.dumps(items)[:200])

    m = g.mark()
    g.api("send", {"text": "tes [[sh:echo halo-gui]]"})
    g.wait(is_type("user", text="halo-gui"), 10, m)
    tool = g.wait(is_type("tool", summary="echo halo-gui"), 90, m)
    res = g.wait(lambda e: e["type"] == "tool_result" and e["id"] == tool["id"], 60, m)
    g.wait(is_type("assistant", html="SELESAI"), 60, m)
    g.turn_done(m)
    check("G3 pesan -> kartu tool + hasil + jawaban", "halo-gui" in res["summary"] and tool["name"] in ("Bash", "PowerShell"),
          json.dumps(res)[:300])
    check("G3b kartu command membawa command lengkap untuk tombol salin", tool.get("copy") == "echo halo-gui",
          json.dumps(tool)[:300])

    # izin: ya
    m = g.mark()
    g.api("send", {"text": f'[[sh:{PY} -c "print(424242)"]]'})
    ask = g.wait(is_type("ask", kind="permission"), 90, m)
    check("G4a pertanyaan izin dengan 3 pilihan", len(ask["options"]) == 3 and "424242" in ask["body"], json.dumps(ask)[:300])
    g.api("answer", {"id": ask["id"], "value": "yes"})
    g.wait(lambda e: e["type"] == "answered" and e["id"] == ask["id"], 10, m)
    g.wait(lambda e: e["type"] == "tool_result" and "424242" in e["summary"], 60, m)
    g.turn_done(m)
    check("G4b jawab Ya -> command jalan", True)

    # izin: tidak, dengan alasan
    m = g.mark()
    g.api("send", {"text": f'[[sh:{PY} -c "print(777)"]]'})
    ask = g.wait(is_type("ask", kind="permission"), 90, m)
    g.api("answer", {"id": ask["id"], "value": "no", "reason": "jangan, pakai cara lain"})
    ans = g.wait(lambda e: e["type"] == "answered" and e["id"] == ask["id"], 10, m)
    res = g.wait(lambda e: e["type"] == "tool_result" and e.get("error"), 60, m)
    g.turn_done(m)
    check("G4c jawab Tidak + alasan -> ditolak, alasan tercatat", "jangan, pakai cara lain" in ans["label"]
          and not any("777" in e.get("summary", "") and not e.get("error") for e in g.events[m:] if e["type"] == "tool_result"),
          json.dumps(res)[:300])

    # pesan susulan saat Claude bekerja
    m = g.mark()
    g.api("send", {"text": "[[sleep:3:3]]"})
    g.wait(lambda e: e["type"] == "tool" and "leep" in e.get("summary", ""), 90, m)
    g.wait(lambda e: e["type"] == "status" and e.get("busy"), 10, m)
    g.api("send", {"text": "[[say:42]]"})
    g.wait(lambda e: e["type"] == "status" and "[[say:42]]" in e.get("pending", []), 10, m)
    g.wait(is_type("user", text="[[say:42]]"), 60, m)
    g.wait(lambda e: e["type"] == "assistant" and ">42<" in e["html"], 60, m)
    g.turn_done(m)
    time.sleep(0.5)
    n_done = g.logs(m).count("Selesai")
    check("G5 pesan susulan saat Claude bekerja: dibaca, satu giliran", n_done == 1, str(n_done))

    # Stop
    m = g.mark()
    g.api("send", {"text": "[[sleep:4:3]]"})
    g.wait(lambda e: e["type"] == "tool" and "leep" in e.get("summary", ""), 90, m)
    time.sleep(1.0)
    g.api("stop")
    g.wait(lambda e: e["type"] == "log" and "Dihentikan oleh user" in e["html"], 60, m)
    check("G6 tombol Stop menghentikan Claude", True)

    # perintah ringan + /help versi GUI
    m = g.mark()
    g.api("send", {"text": "/help"})
    g.wait(lambda e: e["type"] == "log" and "Di GUI:" in e["html"], 20, m)
    check("G7 /help menampilkan pintasan GUI", True)

    # diff dari tool Edit
    (REPO / "kalkulator.py").write_text("def bagi(a, b):\n    return a * b\n", encoding="utf-8")
    m = g.mark()
    g.api("send", {"text": "[[edit:kalkulator.py|return a * b|return a / b]]"})
    tool = g.wait(lambda e: e["type"] == "tool" and e["name"] == "Update", 90, m)
    g.turn_done(m)
    check("G8 kartu edit dengan diff berwarna", "return a / b" in tool["detail"] and 'class="c2"' in tool["detail"]
          and "return a / b" in (REPO / "kalkulator.py").read_text(encoding="utf-8"), tool["detail"][:300])

    # plan mode -> persetujuan rencana (isi rencana dari file rencana)
    g.api("mode", {"mode": "plan"})
    g.wait(lambda e: e["type"] == "status" and e.get("mode") == "plan", 10)
    m = g.mark()
    g.api("send", {"text": "[[plan:## Rencana\\n1. Ubah bagi\\n2. Tambah tes]]"})
    ask = g.wait(is_type("ask", kind="plan"), 90, m)
    check("G9a kartu persetujuan rencana berisi rencananya", "Rencana" in ask["body"] and "Tambah tes" in ask["body"],
          ask["body"][:300])
    g.api("answer", {"id": ask["id"], "value": "1"})
    g.wait(lambda e: e["type"] == "status" and e.get("mode") == "acceptEdits", 30, m)
    g.turn_done(m)
    check("G9b setuju -> mode jadi acceptEdits", True)

    # /clear lalu /resume -> pilihan percakapan lama (percakapan tadi)
    m = g.mark()
    g.api("send", {"text": "/clear"})
    g.wait(lambda e: e["type"] == "log" and "Percakapan baru dimulai" in e["html"], 60, m)
    time.sleep(0.8)  # status terbaru (/clear memulai hitungan biaya dari 0)
    cost_before = [e for e in g.events if e["type"] == "status"][-1]["cost"]
    m = g.mark()
    g.api("send", {"text": "/resume"})
    ask = g.wait(is_type("ask", kind="choice"), 30, m)
    g.api("answer", {"id": ask["id"], "value": "0"})
    g.wait(lambda e: e["type"] == "log" and "Percakapan lama dilanjutkan" in e["html"], 60, m)
    check("G10 /resume: pilih percakapan lama lewat tombol", len(ask["options"]) >= 2)
    g.wait(lambda e: e["type"] == "log" and "Terhubung" in e["html"], 60, m)  # proses baru + cek /goal lokal
    time.sleep(1.5)
    cost_after = [e for e in g.events if e["type"] == "status"][-1]["cost"]
    check("G10b /resume tidak menambah biaya (biaya lama yang dipulihkan mesin bukan pengeluaran baru)",
          cost_after == cost_before and "0 langkah" not in g.logs(m), f"{cost_before} -> {cost_after}")

    # menyalin: blok kode bernomor (tombol salin, /copy N di browser) + teks asli jawaban (/copy)
    m = g.mark()
    g.api("send", {"text": "[[say:Pakai:\\n```bash\\necho gui-salin\\n```]]"})
    ans = g.wait(lambda e: e["type"] == "assistant" and "gui-salin" in e["html"], 60, m)
    g.turn_done(m)
    check("G13 jawaban: blok kode bernomor untuk tombol salin + teks asli Markdown",
          re.search(r'<pre data-copy="\d+"><code', ans["html"]) is not None and "```bash" in ans.get("text", ""),
          json.dumps(ans)[:300])

    # sidebar riwayat: percakapan baru muncul paling atas dan ditandai; /resume ID (klik di sidebar) langsung pindah
    first = [e for e in g.events if e["type"] == "status"][-1].get("session")
    m = g.mark()
    g.api("send", {"text": "/clear"})
    g.wait(lambda e: e["type"] == "log" and "Percakapan baru dimulai" in e["html"], 60, m)
    m = g.mark()
    g.api("send", {"text": "percakapan kedua [[say:jawaban-kedua]]"})
    g.wait(is_type("assistant", html="jawaban-kedua"), 60, m)
    g.turn_done(m)
    r = g.api("sessions", {})
    items, cur = r.get("items", []), r.get("current")
    ids = [it.get("id") for it in items]
    check("G14a daftar riwayat: percakapan baru paling atas dan ditandai, yang lama tetap ada",
          len(items) >= 2 and ids[0] == cur and first in ids and all(it.get("title") and it.get("when") for it in items),
          json.dumps(r)[:400])
    m = g.mark()
    g.api("send", {"text": f"/resume {first}"})
    g.wait(lambda e: e["type"] == "log" and "Percakapan lama dilanjutkan" in e["html"], 60, m)
    g.wait(lambda e: e["type"] == "status" and e.get("session") == first, 60, m)
    check("G14b /resume ID (klik di sidebar) langsung pindah ke percakapan itu", True)

    # /exit -> browser diberi tahu, proses selesai
    m = g.mark()
    g.api("send", {"text": "/exit"})
    g.wait(is_type("bye"), 30, m)
    code = g.proc.wait(30)
    out = "".join(g.out)
    check("G11 /exit: event bye, exit 0, petunjuk --gui --resume", code == 0 and "--gui --resume" in out
          and "Traceback" not in out, f"code={code} {out[-500:]}")


def test_ctrl_c():
    """Ctrl+C di terminal: GUI ditutup rapi (tanpa traceback), exit 0."""
    t = Term(APP + [str(REPO), "--model", "haiku", "--gui", "--no-browser", "--port", "0"], env=env(),
             log=str(OUT / "gui-ctrlc.raw"))
    try:
        t.wait(r"127\.0\.0\.1:\d+", timeout=60)
        time.sleep(2.0)
        t.key("C-c")
        ended = t.wait_exit(30)
        hist = t.history()
        check("G12 Ctrl+C di terminal menutup GUI dengan rapi", ended and t.exitstatus() == 0 and "Menutup GUI" in hist
              and "Traceback" not in hist, f"ended={ended} code={t.exitstatus()} {t.screen_text()[-600:]}")
    except Exception as e:
        check("G12 Ctrl+C di terminal menutup GUI dengan rapi", False, str(e)[-600:])
    finally:
        (OUT / "gui-ctrlc.txt").write_text(t.history(), encoding="utf-8")
        t.kill()


def main():
    make_repo()
    fake = start_fake()
    g = None
    try:
        g = Gui()
        test_security(g)
        test_flow(g)
    except Exception as e:
        check("GUI (exception)", False, str(e)[-1500:])
    finally:
        if g is not None:
            (OUT / "gui-events.json").write_text(json.dumps(g.events, ensure_ascii=False, indent=1), encoding="utf-8")
            (OUT / "gui-out.txt").write_text("".join(g.out), encoding="utf-8")
            if g.proc.poll() is None:
                g.proc.kill()
    try:
        test_ctrl_c()
    finally:
        fake.terminate()
    (OUT / "gui-results.txt").write_text("\n".join(e2e.results) + f"\nFAILS: {e2e.fails or 'none'}\n", encoding="utf-8")
    print("\nFAILS:", e2e.fails or "none", flush=True)
    sys.exit(1 if e2e.fails else 0)


if __name__ == "__main__":
    main()
