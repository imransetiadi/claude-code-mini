"""Fake Anthropic Messages API untuk menguji claude-code-mini tanpa API key (jawaban deterministik).

Mesin Claude Code yang asli diarahkan ke sini lewat ANTHROPIC_BASE_URL. Skenario dipicu penanda di teks user
(penanda TERAKHIR yang dipakai, jadi pesan susulan di tengah giliran langsung mengambil alih):
  [[say:TEKS]]       jawab TEKS
  [[sh:CMD]]         1x tool shell (Bash kalau ada, kalau tidak PowerShell) dengan CMD, lalu jawab "SELESAI"
  [[ps:CMD]]         sama, tapi memakai tool PowerShell kalau tersedia
  [[sleep:N:K]]      K x tool shell "sleep N" (PowerShell: Start-Sleep -Seconds N), lalu jawab "SELESAI"
  [[read:PATH]]      tool Read PATH, lalu jawab "DIBACA"
  (tanpa penanda)    jawab "OK"

Jalankan: python fakeapi.py PORT LOGFILE
"""
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARK = re.compile(r"\[\[(say|sh|ps|sleep|read):(.*?)\]\]", re.S)
LOG_LOCK = threading.Lock()
SEQ = [0]


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
        return ("text", arg)
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
        msg_id = f"msg_fake{seq:04d}"
        if decision[0] == "text":
            content = [{"type": "text", "text": decision[1]}]
            stop = "end_turn"
        else:
            content = [{"type": "tool_use", "id": f"toolu_fake{seq:04d}", "name": decision[1], "input": decision[2]}]
            stop = "tool_use"
        usage = {"input_tokens": 120, "output_tokens": 12, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
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
                                    "usage": {"output_tokens": 12}})
        sse(self, "message_stop", {"type": "message_stop"})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    Handler.logfile = sys.argv[2] if len(sys.argv) > 2 else "fakeapi.log"
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"fakeapi listening on {port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
