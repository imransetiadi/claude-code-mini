"""Unit test offline claude-code-mini (tanpa mesin Claude dan tanpa jaringan): /goal (status, umpan balik pemeriksa,
batas cek), giliran otomatis, toolbar, dan kolom chat saat Claude bekerja (pesan susulan, antrean, Esc).
Jalankan dengan Python dari venv claude-code-mini (butuh claude-agent-sdk, rich, prompt_toolkit):
    ~/.local/share/claude-code-mini/venv/bin/python tests/unit.py
(Windows: %USERPROFILE%\\.local\\share\\claude-code-mini\\venv\\Scripts\\python.exe tests\\unit.py)"""
import argparse, sys, time
from pathlib import Path
sys.argv = ["claude-code-mini"]
import importlib.util
import os
_spec = importlib.util.spec_from_file_location("ccm", os.environ.get("CCMINI_SCRIPT") or str(Path(__file__).resolve().parents[1] / "claude-code-mini.py"))
ng = importlib.util.module_from_spec(_spec); sys.modules["ccm"] = ng; _spec.loader.exec_module(ng)
from claude_agent_sdk._internal.message_parser import parse_message
from rich.console import Console
ng.console = ng.Console(file=open(os.devnull, "w"), force_terminal=False, width=200, highlight=False)  # dummy; replaced per check
fails = []
def check(name, cond, info=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else ""))
    if not cond: fails.append(name)
def capture(fn):
    import io
    buf = io.StringIO(); old = ng.console
    ng.console = Console(file=buf, force_terminal=False, width=200, highlight=False)
    try: fn()
    finally: ng.console = old
    return buf.getvalue()
S = "s"
def asst(text, stop_reason=None):
    return parse_message({"type": "assistant", "message": {"id": "m", "type": "message", "role": "assistant", "model": "x", "stop_reason": stop_reason, "content": [{"type": "text", "text": text}]}, "parent_tool_use_id": None, "session_id": S, "uuid": "u"})
def user_text(text):
    return parse_message({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}, "parent_tool_use_id": None, "session_id": S, "uuid": "u2"})
def result(num_turns=0, subtype="success", is_error=False, text="", origin=None, terminal="completed"):
    return parse_message({"type": "result", "subtype": subtype, "is_error": is_error, "num_turns": num_turns, "duration_ms": 10, "duration_api_ms": 5, "result": text, "session_id": S, "total_cost_usd": 0.01, "usage": {}, "uuid": "r", "origin": origin, "terminal_reason": terminal})
def notif(text="A hook blocked the turn from ending 9 consecutive times — overriding and ending turn. blah", key="stop-hook-block-cap"):
    return parse_message({"type": "system", "subtype": "notification", "key": key, "text": text, "priority": "high", "color": "warning", "uuid": "n", "session_id": S})
def mkui(mode="acceptEdits"):
    args = argparse.Namespace(mode=mode, model="claude-haiku-5-5", budget=None, effort=None, print=None, buffer_mb=64, cont=False, resume=None)
    return ng.UI(Path("."), args)

# 1) parse_goal_active
c, n, r = ng.parse_goal_active("Goal active: file x ada (2 turns)\nLast check: belum ada file")
check("parse (2 turns)", (c, n, r) == ("file x ada", 2, "belum ada file"), repr((c, n, r)))
c, n, r = ng.parse_goal_active("Goal active: tes (a) lulus (b) (1 turn)")
check("parse (1 turn) + kurung di kondisi", (c, n, r) == ("tes (a) lulus (b)", 1, ""), repr((c, n, r)))
c, n, r = ng.parse_goal_active("Goal active: kondisi (3 turns) palsu (not yet evaluated)")
check("parse not yet evaluated", (c, n, r) == ("kondisi (3 turns) palsu", None, ""), repr((c, n, r)))
c, n, r = ng.parse_goal_active("Goal active: kondisi tanpa kurung")
check("parse tanpa kurung", (c, n, r) == ("kondisi tanpa kurung", None, ""), repr((c, n, r)))
c, n, r = ng.parse_goal_active("Goal active: k (5 turns)\nLast check: baris satu\nbaris dua")
check("parse alasan multi-baris", r == "baris satu\nbaris dua" and n == 5, repr((c, n, r)))

# 2) set -> feedback -> cap -> result
ui = mkui()
ui.goal_cmd = "set"
out = capture(lambda: ui.render(asst("Goal set: file hello.txt berisi hi")))
check("set: goal dibuat", ui.goal is not None and ui.goal.condition == "file hello.txt berisi hi")
check("set: baris Indonesia + penjelasan", "Goal ditetapkan: file hello.txt berisi hi" in out and "Pemeriksa cuma membaca" in out, out[:200])
check("set: flag dibersihkan", ui.goal_cmd is None and ui.goal_explained)
out = capture(lambda: ui.render(asst("Goal set: teks biasa dari Claude yang kebetulan mirip")))
check("teks Claude setelah set dicetak biasa (Markdown)", ui.goal.condition == "file hello.txt berisi hi" and "mirip" in out)
ui.fg_active = True
out = capture(lambda: ui.render(user_text("Stop hook feedback:\n[file hello.txt berisi hi]: belum ada file hello.txt")))
check("feedback: cek +1 + alasan", ui.goal.checks == 1 and ui.goal.last_reason == "belum ada file hello.txt" and "Cek goal #1" in out, out)
check("feedback: turn_checks", ui.turn_checks == 1)
out = capture(lambda: ui.render(user_text("Stop hook feedback:\n[file hello.txt berisi hi]: masih [x]: kosong")))
check("feedback dengan ']:' di alasan", ui.goal.checks == 2 and ui.goal.last_reason == "masih [x]: kosong", ui.goal.last_reason)
out = capture(lambda: ui.render(notif()))
check("cap: paused + penjelasan", ui.goal.paused and ui.goal.pause_cause == "cap" and "9x berturut-turut" in out, out)
ui.result_ours = True; ui.turn_future = None
out = capture(lambda: ui.render(result(num_turns=5, text="")))
check("hasil setelah cap: kepala 'diakhiri paksa' + stat cek", "Giliran diakhiri paksa" in out and "🎯 2 cek" in out, out)
check("last_result tersimpan", ui.last_result is not None and ui.last_result.num_turns == 5)

# 3) status typed by user (goal paused) -> no ✓ Selesai
ui.goal_cmd, ui.goal_why = "status", None
out = capture(lambda: ui.render(asst("Goal active: file hello.txt berisi hi (2 turns)\nLast check: masih kosong")))
check("status: baris aktif + dijeda", "Goal aktif: file hello.txt berisi hi" in out and "dijeda (cap)" in out and "cek terakhir: masih kosong" in out, out)
ui.result_ours = True
out = capture(lambda: ui.render(result(num_turns=0, text="Goal active: ...")))
check("status: tanpa '✓ Selesai · 0 langkah'", "Selesai" not in out and "langkah" not in out, out)

# 4) after_turn + No goal set -> berakhir (goal finished)
ui.goal.paused = False
ui.goal_cmd, ui.goal_why = "status", "after_turn"
out = capture(lambda: ui.render(asst("No goal set. Usage: `/goal <condition>`")))
check("after_turn: goal berakhir -> last_goal", ui.goal is None and ui.last_goal is not None and "Goal berakhir" in out and "2 cek" in out, out)
ui.goal_cmd, ui.goal_why = "status", None
out = capture(lambda: ui.render(asst("No goal set. Usage: `/goal <condition>`")))
check("status tanpa goal: 'Belum ada goal aktif' + goal terakhir", "Belum ada goal aktif" in out and "Goal terakhir" in out, out)

# 5) clear
ui.goal = ng.Goal(condition="x"); ui.goal_cmd = "clear"
out = capture(lambda: ui.render(asst("Goal cleared: x")))
check("clear: dibatalkan", ui.goal is None and "Goal dibatalkan: x" in out, out)
ui.goal_cmd = "clear"
out = capture(lambda: ui.render(asst("No goal set")))
check("clear tanpa goal", "Tidak ada goal aktif" in out, out)

# 6) refusal while set
ui.goal_cmd = "set"
out = capture(lambda: ui.render(asst("Goal condition is limited to 4000 characters (got 4001)")))
check("set ditolak: ⚠ + state tetap", ui.goal is None and "Goal tidak diset" in out, out)

# 7) user Stop hook (no bracket) + lazy adoption
out = capture(lambda: ui.render(user_text("Stop hook feedback:\nJangan lupa jalankan lint dulu")))
check("stop hook user tanpa kurung -> generik", ui.goal is None and "Umpan balik Stop hook" in out, out)
out = capture(lambda: ui.render(user_text("Stop hook feedback:\n[npm run lint]: lint errors")))
check("kurung yang bukan goal kita (Stop hook command user) -> generik + goal_dirty", ui.goal is None and "Umpan balik Stop hook" in out and ui.goal_dirty, out)
ui.last_goal = ng.Goal(condition="kondisi dari resume yang cukup panjang supaya lolos batas empat puluh karakter"); ui.last_goal.checks = 2; ui.last_goal.end(0.5)
out = capture(lambda: ui.render(user_text("Stop hook feedback:\n[kondisi dari resume yang cukup panjang supaya lolos batas empat puluh karakter]: belum")))
check("goal terakhir dihidupkan lagi dari feedback", ui.goal is not None and ui.goal.checks == 3 and ui.last_goal is None and "masih aktif di Claude Code" in out, out)
ui.goal = ng.Goal(condition="kondisi dari resume")  # untuk langkah berikutnya

# 8) automatic turn end with goal and no feedback -> inferred finish; with error -> paused
ui.result_ours = False; ui.turn_future = None
ui.turn_capped = False  # giliran baru (init otomatis) selalu me-reset ini
out = capture(lambda: ui.render(result(num_turns=2, text="ok", origin={"kind": "task-notification"})))
check("giliran otomatis selesai normal -> berakhir (disimpulkan)", ui.goal is None and "disimpulkan" in out, out)
ui.goal = ng.Goal(condition="y"); ui.result_ours = False
out = capture(lambda: ui.render(result(num_turns=2, subtype="error_during_execution", is_error=True, origin={"kind": "task-notification"})))
check("giliran otomatis error -> dijeda", ui.goal is not None and ui.goal.paused and ui.goal.pause_cause == "error" and "Goal dijeda" in out, out)
ui.result_ours = False
out = capture(lambda: ui.render(result(num_turns=0, text="No goal set", origin=None)))
check("jawaban lokal terlambat (otomatis): tanpa kepala respons otomatis", "Respons otomatis" not in out, out)

# 9) footer / status_text / status row
ui.goal = ng.Goal(condition="z"); ui.goal.checks = 3; ui.goal.paused = True; ui.goal.pause_cause = "cap"
f = ui.footer().plain
check("footer chip", "🎯 goal" in f and "3 cek ⏸" in f and "(/goal)" in f, f)
ui.goal_note = ""; st = ui.status_text().plain
check("spinner bit", "🎯 goal · 3 cek" in st, st)
ui.goal_note = "🎯 pemeriksa menilai goal…"; st = ui.status_text().plain
check("spinner note", "pemeriksa menilai goal" in st, st)
check("status row", "z · 3 cek · ⏸ dijeda (cap)" in ng.goal_status_row(ui), ng.goal_status_row(ui))
# stop_reason end_turn sets note
ui.goal_note = ""
capture(lambda: ui.render(asst("selesai bicara", stop_reason="end_turn")))
check("end_turn -> goal_note", ui.goal_note == "🎯 pemeriksa menilai goal…", ui.goal_note)
# 10) stats arithmetic
g = ng.Goal(condition="q", cost_at_set=1.0); g.set_at -= 65; g.end(1.25)
check("stats setelah selesai", g.stats(99.0) == "0 cek · 1m 05s · biaya $0.2500", g.stats(99.0))
print("\nFAILS:", fails or "none")

# ===== tambahan setelah review =====
import asyncio
fails.clear()
loop = asyncio.new_event_loop()
def echo(text="<command-name>x</command-name>"):
    return parse_message({"type": "user", "message": {"role": "user", "content": text}, "parent_tool_use_id": None, "session_id": S, "uuid": "e1"})
# R1: jeda dicabut saat prompt user diproses (echo), tidak saat giliran quiet
ui = mkui(); ui.goal = ng.Goal(condition="g1"); ui.goal.paused, ui.goal.pause_cause = True, "dihentikan user"
ui.turn_future = loop.create_future(); ui.quiet_turn = True; ui.turn_prompt = "/goal"
ui.classify(echo()); check("R1a quiet turn tidak mencabut jeda", ui.goal.paused)
ui.quiet_turn = False; ui.turn_prompt = "lanjutkan"; ui.classify(echo())
check("R1b echo prompt user mencabut jeda", not ui.goal.paused and ui.goal.pause_cause == "")
# R2: kepala 'diakhiri paksa' hanya di giliran yang kena batas
ui = mkui(); ui.goal = ng.Goal(condition="g2"); ui.fg_active = False
capture(lambda: ui.render(notif())); check("R2a cap -> turn_capped", ui.turn_capped and ui.goal.paused)
ui.result_ours = True; out = capture(lambda: ui.render(result(num_turns=3, text="")))
check("R2b kepala diakhiri paksa di giliran cap", "Giliran diakhiri paksa" in out)
ui.begin_turn("lanjutkan"); ui.result_ours = True
out = capture(lambda: ui.render(result(num_turns=2, text="beres")))
check("R2c giliran berikutnya normal -> ✓ Selesai", "✓ Selesai" in out and "diakhiri paksa" not in out, out)
# R3: hasil giliran otomatis tidak menghapus goal_cmd; teks otomatis tidak ditelan cabang 'set'
ui = mkui(); ui.goal_cmd, ui.goal_why = "set", None; ui.result_ours = False; ui.turn_future = loop.create_future()
out = capture(lambda: ui.render(asst("Hasil tes: 3 gagal karena timeout")))
check("R3a teks lain saat menunggu 'Goal set' dicetak biasa", "3 gagal" in out and ui.goal_cmd == "set" and ui.goal is None, out)
out = capture(lambda: ui.render(result(num_turns=2, text="x", origin={"kind": "task-notification"})))
check("R3b hasil otomatis tidak menghapus goal_cmd", ui.goal_cmd == "set")
out = capture(lambda: ui.render(asst("Goal set: semua test lulus")))
check("R3c 'Goal set' setelahnya tetap dikenali", ui.goal is not None and ui.goal.condition == "semua test lulus" and ui.goal_cmd is None)
# R4: 'No goal set' pada /goal yang diketik user membuang goal lokal yang basi
ui = mkui(); ui.goal = ng.Goal(condition="basi"); ui.goal_cmd, ui.goal_why = "status", None
out = capture(lambda: ui.render(asst("No goal set. Usage: `/goal <condition>`")))
check("R4a status: goal basi dibuang + catatan", ui.goal is None and ui.last_goal and ui.last_goal.condition == "basi" and "ternyata sudah tidak aktif" in out, out)
ui.goal = ng.Goal(condition="basi2"); ui.goal_cmd = "clear"
out = capture(lambda: ui.render(asst("No goal set")))
check("R4b clear: goal basi dibuang", ui.goal is None and "Tidak ada goal aktif" in out, out)
# R5: subtype error dibawa ke pesan 'dihapus otomatis'
ui = mkui(); ui.goal = ng.Goal(condition="g5"); ui.goal_err = "error_max_budget_usd"; ui.goal_cmd, ui.goal_why = "status", "after_error"
out = capture(lambda: ui.render(asst("No goal set")))
check("R5 pesan dihapus otomatis memuat subtype", "setelah error (error_max_budget_usd)" in out and ui.goal is None, out)
# R6: kondisi dengan markup rich tidak bikin crash
ui = mkui(); ui.goal = ng.Goal(condition="endpoint [/api/health] balas 200 [bold]x[/bold]")
try:
    out = capture(lambda: loop.run_until_complete(ng.handle_command("/goal tes lain", None, ui)))
    ok = "Goal sebelumnya akan diganti" in out and "[/api/health]" in out
except Exception as e:
    ok = False; out = repr(e)
check("R6a ganti goal: kondisi dengan [/tag] aman", ok, out)
try:
    row = ng.goal_status_row(ui); capture(lambda: ng.console.print(f"  🎯 Goal {row}")); ok = "[/api/health]" in row or "\\[" in row
except Exception as e:
    ok = False
check("R6b /status: kondisi dengan [/tag] aman", ok)
# R7: hasil lokal dengan biaya (mis. /compact) tetap menampilkan ✓ Selesai + biaya; tanpa biaya tidak
ui = mkui(); ui.result_ours = True; ui.cost_proc = 0.0
out = capture(lambda: ui.render(result(num_turns=0, text="")))
check("R7a hasil lokal berbiaya -> ✓ Selesai", "✓ Selesai" in out and "biaya: $0.0100" in out, out)
ui.result_ours = True
out = capture(lambda: ui.render(result(num_turns=0, text="")))
check("R7b hasil lokal seketika tanpa biaya -> diam", "Selesai" not in out, out)
# R8: jawaban /goal terlambat tidak dianggap hasil prompt user
ui = mkui(); ui.goal_late = True; ui.turn_future = loop.create_future(); ui.echo_seen = False; ui.turn_prompt = "tulis esai"
ui.classify(result(num_turns=0, text="No goal set")); check("R8a hasil lokal terlambat bukan milik prompt user", not ui.result_ours)
ui.turn_prompt = "/goal"; ui.classify(result(num_turns=0, text="No goal set")); check("R8b tapi /goal yang diketik user tetap dapat jawabannya", ui.result_ours)
print("\nFAILS (review additions):", fails or "none")

# ===== tambahan setelah review ke-2 =====
fails.clear()
check("same_goal: sama", ng.same_goal("a b c", "a  b c"))
longc = "kondisi " * 80
check("same_goal: terpotong 500 + …", ng.same_goal(longc, longc[:500] + "…"))
check("same_goal: prefix pendek tidak cocok", not ng.same_goal("abc", "abcdef"))
# S1: feedback dengan kondisi terpotong tidak mengganti goal
ui = mkui(); ui.goal = ng.Goal(condition=longc); ui.goal.checks = 1
out = capture(lambda: ui.render(user_text("Stop hook feedback:\n[" + longc[:500] + "…]: masih kurang")))
check("S1 feedback terpotong -> goal sama, cek +1", ui.goal.condition == longc and ui.goal.checks == 2 and ui.goal.last_reason == "masih kurang", out)
# S2: 'Goal cleared:' tanpa goal lokal tetap 'dibatalkan'
ui = mkui(); ui.goal_cmd = "clear"
out = capture(lambda: ui.render(asst("Goal cleared: tests pass")))
check("S2 Goal cleared tanpa goal lokal", "Goal dibatalkan: tests pass" in out, out)
# S3: penolakan saat cmd status / teks lain saat status tidak ditelan
ui = mkui(); ui.goal_cmd = "status"
out = capture(lambda: ui.render(asst("/goal can't run while hooks are restricted")))
check("S3a penolakan saat status -> /goal ditolak", "/goal ditolak" in out and ui.goal_cmd is None, out)
ui.goal_cmd = "status"
out = capture(lambda: ui.render(asst("Jawaban Claude untuk tugas background yang masih jalan")))
check("S3b teks lain saat status: dicetak biasa, cmd tetap", "tugas background" in out and ui.goal_cmd == "status", out)
# S4: 'Goal active' menghidupkan last_goal dengan hitungan tetap; atau catatan 'mulai dari nol'
ui = mkui(); lg = ng.Goal(condition="kondisi lama yang panjangnya lebih dari empat puluh karakter ya"); lg.checks = 5; lg.end(0.3); ui.last_goal = lg
ui.goal_cmd, ui.goal_why = "status", None
out = capture(lambda: ui.render(asst("Goal active: kondisi lama yang panjangnya lebih dari empat puluh karakter ya (5 turns)")))
check("S4a last_goal dihidupkan lagi", ui.goal is lg and ui.goal.checks == 5 and "dicek 5x" in out and "mulai dari nol" not in out, out)
ui = mkui(); ui.goal_cmd, ui.goal_why = "status", None
out = capture(lambda: ui.render(asst("Goal active: kondisi baru (not yet evaluated)")))
check("S4b goal baru dari status -> catatan mulai dari nol", ui.goal is not None and "mulai dari nol" in out, out)
# S5: auto_error: aktif -> diam; tidak ada -> dihapus setelah error
ui = mkui(); ui.goal = ng.Goal(condition="g5"); ui.goal_cmd, ui.goal_why = "status", "auto_error"
out = capture(lambda: ui.render(asst("Goal active: g5 (1 turn)")))
check("S5a auto_error + aktif -> diam", out.strip() == "" and ui.goal is not None, out)
ui.goal_cmd, ui.goal_why, ui.goal_err = "status", "auto_error", "error_during_execution"
out = capture(lambda: ui.render(asst("No goal set")))
check("S5b auto_error + tidak ada -> dihapus setelah error + goal_failed", ui.goal is None and "setelah error (error_during_execution)" in out and ui.goal_failed, out)
# S6: giliran otomatis error saat goal aktif -> goal_auto_err tercatat
ui = mkui(); ui.goal = ng.Goal(condition="g6"); ui.result_ours = False
capture(lambda: ui.render(result(num_turns=2, subtype="error_during_execution", is_error=True, origin={"kind": "task-notification"})))
check("S6 goal_auto_err dicatat", ui.goal_auto_err == "error_during_execution" and ui.goal.paused)
# S7: pengecualian jawaban terlambat hanya untuk /goal lokal
ui = mkui(); ui.goal_late = True; ui.turn_future = loop.create_future(); ui.echo_seen = False
ui.turn_prompt = "/goal buat file x"; ui.classify(result(num_turns=0, text="No goal set"))
check("S7a '/goal <kondisi>' tidak kena pengecualian", not ui.result_ours)
ui.turn_prompt = "/goal clear"; ui.classify(result(num_turns=0, text="No goal set")); check("S7b '/goal clear' tetap dapat jawaban", ui.result_ours)
# S8: giliran otomatis terdeteksi saat giliran quiet (notifikasi tugas) -> header + status otomatis
ui = mkui(); ui.goal = ng.Goal(condition="g8"); ui.goal.paused = True; ui.turn_future = loop.create_future(); ui.quiet_turn = True
m = parse_message({"type": "user", "message": {"role": "user", "content": "<task-notification>…</task-notification>"}, "parent_tool_use_id": None, "session_id": S, "uuid": "tn", "origin": {"kind": "task-notification"}})
ui.classify(m); check("S8a notifikasi tugas saat quiet -> auto_during_quiet + jeda dicabut", ui.auto_during_quiet and ui.auto_header and not ui.goal.paused)
out = capture(lambda: ui.render(m)); check("S8b header giliran otomatis dicetak", "melanjutkan goal secara otomatis" in out, out)
print("\nFAILS (review-2 additions):", fails or "none")

# ============ T) kolom chat saat Claude bekerja: steer / antrean / perintah ringan / giliran lanjutan ============
asyncio.set_event_loop(loop)
class FakeClient:
    def __init__(self): self.sent = []; self.interrupts = 0; self.modes = []
    async def query(self, text): self.sent.append(text)
    async def interrupt(self): self.interrupts += 1
    async def set_permission_mode(self, m): self.modes.append(m)
def user_echo(text, uuid="u3"):
    return parse_message({"type": "user", "message": {"role": "user", "content": text}, "parent_tool_use_id": None, "session_id": S, "uuid": uuid, "origin": None})
async def settle(n=6):
    for _ in range(n): await asyncio.sleep(0)
def busy_ui():
    ui = mkui(); ui.client = FakeClient(); ui.turn_task = loop.create_future(); ui.fg_active = True; ui.tui_turn = True
    ui.turn_future = loop.create_future(); ui.turn_prompt = "prompt utama"; return ui
# T1: pesan biasa saat sibuk -> langsung dikirim (steer) + dicatat sebagai pending
ui = busy_ui()
check("T1a busy()/can_steer()", ui.busy() and ui.can_steer())
async def t1():
    ui.submit_while_busy("halo susulan"); await settle()
loop.run_until_complete(t1())
check("T1b steer: dikirim ke mesin + pending", ui.client.sent == ["halo susulan"] and list(ui.sent_pending) == [["halo susulan", "halo susulan"]], repr((ui.client.sent, list(ui.sent_pending))))
check("T1c queue_rows: dibaca Claude setelah langkah ini", any("dibaca Claude setelah langkah ini: halo susulan" in r.plain for r in ui.queue_rows()))
# T2: gema pesan susulan -> dicetak "› …" + checkpoint; gema prompt utama tidak mengganggu pending
ui.checkpoint_label = "prompt utama"
out = capture(lambda: ui.render(user_echo("prompt utama", "u-main")))
check("T2a gema prompt utama: checkpoint, pending tetap", ui.checkpoints[-1] == ("u-main", "prompt utama") and len(ui.sent_pending) == 1 and "›" not in out, out)
out = capture(lambda: ui.render(user_echo("halo susulan")))
check("T2b gema pesan susulan dicetak + checkpoint + pending kosong", "› halo susulan" in out and ui.checkpoints[-1] == ("u3", "halo susulan") and not ui.sent_pending, out)
# T3: perintah lokal & !command antre, urutan dijaga; perintah ringan langsung jalan (kalau antrean kosong)
ui = busy_ui()
out = capture(lambda: loop.run_until_complete((lambda: (ui.submit_while_busy("/cost"), settle())[1])()))
check("T3a /cost langsung dijalankan saat sibuk", "› /cost" in out and "Total biaya sesi ini" in out, out)
ui.submit_while_busy("/clear"); ui.submit_while_busy("halo setelah clear"); ui.submit_while_busy("/cost")
check("T3b /clear antre, pesan & /cost sesudahnya ikut antre (urutan dijaga)", list(ui.prompt.queue) == ["/clear", "halo setelah clear", "/cost"] and not ui.client.sent, repr(list(ui.prompt.queue)))
rows = ui.queue_rows(); check("T3c queue_rows: antrean + petunjuk ↑", any("setelah giliran selesai: /clear" in r.plain for r in rows) and "ambil kembali" in rows[-1].plain and "+1 lagi" in rows[-1].plain, repr([r.plain for r in rows]))
ui.prompt.queue.clear()
out = capture(lambda: loop.run_until_complete((lambda: (ui.submit_while_busy("/mode plan"), settle())[1])()))
check("T3d /mode saat sibuk: mode diganti tanpa menunggu", ui.args.mode == "plan" and ui.client.modes == ["plan"] and "Mode izin diganti ke plan" in out, out)
# T4: saat cek status goal (quiet) pesan tidak di-steer tapi antre
ui = busy_ui(); ui.quiet_turn = True
ui.submit_while_busy("pesan saat cek goal"); check("T4 quiet turn: pesan antre, tidak dikirim", list(ui.prompt.queue) == ["pesan saat cek goal"] and not ui.sent_pending)
# T5: hasil giliran datang saat masih ada pending -> giliran berlanjut (continue_turn); pengaman waktu melepasnya
ui = busy_ui(); ui.sent_pending.append([None, "pesan tertunda"]); ui.interrupted = True; fut = ui.turn_future
out = capture(lambda: loop.run_until_complete(ui.dispatch(result(num_turns=1, text="ok"))))
check("T5a hasil pertama: 'lanjut ke pesan susulan', future belum selesai", "lanjut ke pesan susulan" in out and not fut.done() and ui.cont_seq == 1, out)
check("T5b begin_turn ulang: interrupted/stopping reset, label = pesan susulan", not ui.interrupted and not ui.stopping and ui.checkpoint_label == "pesan tertunda")
out = capture(lambda: ui._continuation_check(fut, 1))
check("T5c pengaman: mesin tidak memulai giliran -> peringatan + future selesai + pending kosong", "tidak diproses Claude" in out and fut.done() and not ui.sent_pending, out)
ui = busy_ui(); ui.sent_pending.append(["x", "x"]); fut = ui.turn_future; ui.cli_busy = True
ui._continuation_check(fut, 99); check("T5d pengaman tidak jalan kalau seq beda / mesin sibuk", not fut.done() and ui.sent_pending)
# T6: interrupt_turn
ui = busy_ui(); fut = ui.turn_future
out = capture(lambda: (ui.interrupt_turn(), loop.run_until_complete(settle())))
check("T6a Esc saat sibuk: interrupted + interrupt() ke mesin + pesan", ui.interrupted and ui.stopping and ui.client.interrupts == 1 and "Menghentikan Claude" in out, out)
check("T6b Esc kedua tidak mengulang", ui.interrupt_turn() is False and ui.client.interrupts == 1)
ui = busy_ui(); ui.quiet_turn = True; fut = ui.turn_future
out = capture(lambda: ui.interrupt_turn()); check("T6c Esc saat cek goal: berhenti menunggu saja", fut.done() and fut.result() is None and ui.goal_late and not ui.interrupted and ui.client.interrupts == 0, out)
ui = mkui(); check("T6d Esc saat idle: tidak terjadi apa-apa", ui.interrupt_turn() is False)
ui = mkui(); ui.client = FakeClient(); ui.cli_busy = True
out = capture(lambda: (ui.interrupt_turn(), loop.run_until_complete(settle())))
check("T6e Esc saat giliran otomatis: interrupt_auto", ui.auto_interrupted and ui.client.interrupts == 1 and "respons otomatis" in out, out)
# T7: confirm_drop_tasks menyebut giliran yang jalan
qs = []; ng.ask = lambda q: (qs.append(q), "n")[1]
ui = busy_ui(); check("T7a konfirmasi saat sibuk", confirm_drop_tasks_r := ng.confirm_drop_tasks(ui, "keluar") is False and "Claude masih bekerja" in qs[-1], qs[-1] if qs else "")
ui = mkui(); check("T7b idle tanpa tugas: tanpa pertanyaan", ng.confirm_drop_tasks(ui, "keluar") is True and len(qs) == 1)
# T8: drain hanya menutup prompt kalau ada antrean & tidak sibuk (tanpa app: tidak crash)
ui = mkui(); ui.prompt.queue.append("/help"); ui.prompt.drain(); check("T8 drain tanpa prompt aktif: aman", list(ui.prompt.queue) == ["/help"])
# T9: toolbar saat sibuk memuat spinner + status, tanpa crash
ui = busy_ui(); tb = ui.toolbar(); check("T9 toolbar sibuk: spinner + 'esc untuk berhenti'", "esc untuk berhenti" in tb.value and "shift+tab" in tb.value, tb.value[:200])
print("\nFAILS (steer additions):", fails or "none")

sys.exit(1 if fails else 0)
