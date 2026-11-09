"""Fake Anthropic Messages API untuk menguji claude-code-mini tanpa API key (jawaban deterministik).

Mesin Claude Code yang asli diarahkan ke sini lewat ANTHROPIC_BASE_URL. Skenario dipicu penanda di teks user
(penanda TERAKHIR yang dipakai, jadi pesan susulan di tengah giliran langsung mengambil alih):
  [[say:TEKS]]       jawab TEKS (\n di TEKS = baris baru)
  [[sh:CMD]]         1x tool shell (Bash kalau ada, kalau tidak PowerShell) dengan CMD, lalu jawab "SELESAI"
  [[ps:CMD]]         sama, tapi memakai tool PowerShell kalau tersedia
  [[sleep:N:K]]      K x tool shell "sleep N" (PowerShell: Start-Sleep -Seconds N), lalu jawab "SELESAI"
  [[read:PATH]]      tool Read PATH, lalu jawab "DIBACA"
  [[edit:PATH|LAMA|BARU]]  Read PATH, lalu Edit (LAMA -> BARU), lalu jawab "SELESAI"
  [[plan:TEKS]]      ExitPlanMode dengan rencana TEKS (di plan mode), lalu jawab "SELESAI"
  (tanpa penanda)    jawab "OK"

Jalankan: python fakeapi.py PORT LOGFILE
"""
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARK = re.compile(r"\[\[(say|sh|ps|sleep|read|edit|plan):(.*?)\]\]", re.S)
LOG_LOCK = threading.Lock()
SEQ = [0]
RUN = os.urandom(3).hex()  # ID unik per proses: restart server tiruan tidak membuat ID tool bentrok di percakapan lama


def log(path, entry):
    with LOG_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def texts_of(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return [c]
    out = []
    for b in c or []:
        if isinstance(b, dict) and b.get("type") == "text":
            out.append(b.get("text", ""))
    return out


def tool_uses_of(msg):
    c = msg.get("content")
    if not isinstance(c, list):
        return []
    return [b for b in c if isinstance(b, dict) and b.get("type") == "tool_use"]


def all_texts(body):
    sysp = body.get("system")
    out = [sysp] if isinstance(sysp, str) else [b.get("text", "") for b in sysp or [] if isinstance(b, dict)]
    for m in body.get("messages") or []:
        out += texts_of(m)
    return out


def plan_path(body):
    """Lokasi file rencana yang diberikan Claude Code di prompt plan mode."""
    for text in reversed(all_texts(body)):
        m = re.search(r"(?:create your plan at|plan file already exists at) (\S+?\.md)", text)
        if m:
            return m.group(1)
    return None


def decide(body):
    """-> ("text", str) | ("tool", name, input)"""
    tools = [t.get("name") for t in body.get("tools") or [] if isinstance(t, dict)]
    msgs = body.get("messages") or []
    # cari penanda terakhir di pesan user (pesan susulan di tengah giliran dikirim mesin sebagai pesan role "system")
    where, mark = None, None
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") not in ("user", "system"):
            continue
        found = []
        for t in texts_of(msgs[i]):
            found += MARK.findall(t)
        if found:
            where, mark = i, found[-1]
            break
    if mark is None:
        return ("text", "OK")
    kind, arg = mark
    done = sum(len(tool_uses_of(m)) for m in msgs[where + 1:] if m.get("role") == "assistant")
    shell = "Bash" if "Bash" in tools else ("PowerShell" if "PowerShell" in tools else None)
    if kind == "say":
        return ("text", arg.replace("\\n", "\n"))  # \n = baris baru (mis. untuk blok kode)
    if kind in ("sh", "ps"):
        tool = "PowerShell" if kind == "ps" and "PowerShell" in tools else shell
        if done == 0 and tool:
            return ("tool", tool, {"command": arg, "description": "Perintah tes"})
        return ("text", "SELESAI")
    if kind == "sleep":
        n, _, k = arg.partition(":")
        k = int(k or 1)
        if done < k and shell:
            cmd = f"sleep {n}" if shell == "Bash" else f"Start-Sleep -Seconds {n}"
            return ("tool", shell, {"command": cmd, "description": f"Tidur {n} detik ({done + 1} dari {k})"})
        return ("text", "SELESAI")
    if kind == "read":
        if done == 0 and "Read" in tools:
            return ("tool", "Read", {"file_path": arg})
        return ("text", "DIBACA")
    if kind == "edit":
        path, old, new = (arg.split("|") + ["", ""])[:3]
        if done == 0:
            return ("tool", "Read", {"file_path": path})
        if done == 1:
            return ("tool", "Edit", {"file_path": path, "old_string": old, "new_string": new})
        return ("text", "SELESAI")
    if kind == "plan":  # seperti model sungguhan: tulis file rencana, muat ExitPlanMode (tool tertunda), lalu panggil
        used = [b.get("name") for m in msgs[where + 1:] if m.get("role") == "assistant" for b in tool_uses_of(m)]
        if "ExitPlanMode" in used:
            return ("text", "SELESAI")
        path = plan_path(body)
        if path and "Write" not in used and "Write" in tools:
            return ("tool", "Write", {"file_path": path, "content": arg.replace("\\n", "\n") + "\n"})
        if "ExitPlanMode" in tools:
            return ("tool", "ExitPlanMode", {"plan": arg.replace("\\n", "\n")})
        if "ToolSearch" in tools and "ToolSearch" not in used:
            return ("tool", "ToolSearch", {"query": "select:ExitPlanMode", "max_results": 1})
        return ("text", "SELESAI")
    return ("text", "OK")


def sse(handler, event, data):
    handler.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
    handler.wfile.flush()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    logfile = "fakeapi.log"

    def log_message(self, fmt, *args):  # stdout bersih
        pass

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            return {}

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.send_header("request-id", "req_fake")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        log(self.logfile, {"method": "GET", "path": self.path})
        if self.path.split("?")[0].endswith("/v1/models"):  # cek API key oleh installer: hanya key tes yang diterima
            if (self.headers.get("x-api-key") or "").startswith("sk-ant-fake"):
                return self._json(200, {"data": [{"type": "model", "id": "claude-haiku-5-5"}], "has_more": False})
            return self._json(401, {"type": "error", "error": {"type": "authentication_error",
                                                              "message": "invalid x-api-key"}})
        self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "fake"}})

    def do_HEAD(self):
        log(self.logfile, {"method": "HEAD", "path": self.path})
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        body = self._body()
        path = self.path.split("?")[0]
        if path.endswith("/count_tokens"):
            log(self.logfile, {"method": "POST", "path": self.path, "count_tokens": True})
            return self._json(200, {"input_tokens": 2000})
        if not path.endswith("/v1/messages"):
            log(self.logfile, {"method": "POST", "path": self.path})
            return self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "fake"}})
        SEQ[0] += 1
        seq = SEQ[0]
        decision = decide(body)
        last_user = next((m for m in reversed(body.get("messages") or []) if m.get("role") == "user"), {})
        log(self.logfile, {
            "seq": seq, "path": self.path, "model": body.get("model"), "stream": body.get("stream"),
            "tools": [t.get("name") for t in body.get("tools") or [] if isinstance(t, dict)][:60],
            "n_messages": len(body.get("messages") or []), "max_tokens": body.get("max_tokens"),
            "system_head": (json.dumps(body.get("system"))[:300] if body.get("system") else None),
            "last_user": json.dumps(last_user.get("content"), ensure_ascii=False)[-600:],
            "tail": [(m.get("role"), json.dumps(m.get("content"), ensure_ascii=False)[-260:])
                     for m in (body.get("messages") or [])[-4:]],
            "decision": decision,
        })
        model = body.get("model") or "claude-haiku-5-5"
        msg_id = f"msg_fake{RUN}{seq:04d}"
        if decision[0] == "text":
            content = [{"type": "text", "text": decision[1]}]
            stop = "end_turn"
        else:
            content = [{"type": "tool_use", "id": f"toolu_fake{RUN}{seq:04d}", "name": decision[1], "input": decision[2]}]
            stop = "tool_use"
        # cukup besar supaya biaya per giliran terlihat di tampilan 4 desimal (± $0.002)
        usage = {"input_tokens": 12000, "output_tokens": 1200, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        if not body.get("stream"):
            return self._json(200, {"id": msg_id, "type": "message", "role": "assistant", "model": model,
                                    "content": content, "stop_reason": stop, "stop_sequence": None, "usage": usage})
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("request-id", "req_fake")
        self.end_headers()
        sse(self, "message_start", {"type": "message_start", "message": {
            "id": msg_id, "type": "message", "role": "assistant", "model": model, "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {**usage, "output_tokens": 1}}})
        block = content[0]
        if block["type"] == "text":
            sse(self, "content_block_start", {"type": "content_block_start", "index": 0,
                                              "content_block": {"type": "text", "text": ""}})
            text = block["text"]
            for i in range(0, len(text), 24):
                sse(self, "content_block_delta", {"type": "content_block_delta", "index": 0,
                                                  "delta": {"type": "text_delta", "text": text[i:i + 24]}})
                time.sleep(0.02)
        else:
            sse(self, "content_block_start", {"type": "content_block_start", "index": 0, "content_block": {
                "type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}})
            sse(self, "content_block_delta", {"type": "content_block_delta", "index": 0,
                                              "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}})
        sse(self, "content_block_stop", {"type": "content_block_stop", "index": 0})
        sse(self, "message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                                    "usage": {"output_tokens": 1200}})
        sse(self, "message_stop", {"type": "message_stop"})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    Handler.logfile = sys.argv[2] if len(sys.argv) > 2 else "fakeapi.log"
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"fakeapi listening on {port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
