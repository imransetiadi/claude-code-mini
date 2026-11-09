"""Terminal virtual untuk tes interaktif lintas platform.

Proses dijalankan di pseudo-terminal (ConPTY lewat pywinpty di Windows, ptyprocess di macOS/Linux) dan output-nya
digambar oleh emulator VT (pyte), jadi layar + scrollback bisa dibaca seperti `tmux capture-pane`. Permintaan posisi
kursor (ESC[6n, dipakai prompt_toolkit dan ConPTY) dijawab oleh pyte.
"""
import os
import re
import threading
import time

import pyte

KEYS = {"Enter": "\r", "Escape": "\x1b", "C-c": "\x03", "C-d": "\x04", "C-u": "\x15", "Up": "\x1b[A",
        "Down": "\x1b[B", "BTab": "\x1b[Z", "Backspace": "\x7f"}


class Term:
    def __init__(self, argv, rows=40, cols=150, env=None, cwd=None, log=None):
        self.rows, self.cols = rows, cols
        self.screen = pyte.HistoryScreen(cols, rows, history=20000, ratio=0.5)
        self.screen.write_process_input = self._respond
        self.stream = pyte.Stream(self.screen)
        self.lock = threading.Lock()
        self.log = open(log, "w", encoding="utf-8", newline="") if log else None
        if os.name == "nt":
            from winpty import PtyProcess
        else:
            from ptyprocess import PtyProcessUnicode as PtyProcess
        self.proc = PtyProcess.spawn(argv, dimensions=(rows, cols), env=env, cwd=cwd)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _respond(self, data):
        try:
            self.proc.write(data)
        except Exception:
            pass

    def _read(self):
        while True:
            try:
                data = self.proc.read(4096)
            except EOFError:
                break
            except Exception:
                if not self.proc.isalive():
                    break
                time.sleep(0.02)
                continue
            if not data:
                if not self.proc.isalive():
                    break
                time.sleep(0.01)
                continue
            with self.lock:
                if self.log:
                    self.log.write(data)
                    self.log.flush()
                self.stream.feed(data)

    # ---------- membaca layar ----------
    def _text(self, line):
        return "".join(line[x].data for x in range(self.cols)).rstrip()

    def screen_text(self):
        with self.lock:
            return "\n".join(self._text(self.screen.buffer[y]) for y in range(self.rows)).rstrip()

    def history(self):
        with self.lock:
            top = [self._text(line) for line in self.screen.history.top]
            return "\n".join(top + [self._text(self.screen.buffer[y]) for y in range(self.rows)])

    def count(self, pat):
        return len(re.findall(pat, self.history()))

    def has(self, pat):
        return re.search(pat, self.screen_text()) is not None

    def wait(self, pat, after=0, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            if self.count(pat) > after:
                return True
            if not self.alive() and self.count(pat) <= after:
                time.sleep(0.5)
                if self.count(pat) > after:
                    return True
                raise TimeoutError(f"proses sudah berhenti sebelum muncul {pat!r}\n----- layar -----\n{self.screen_text()}")
            time.sleep(0.2)
        raise TimeoutError(f"timeout menunggu {pat!r}\n----- layar -----\n{self.screen_text()}")

    def wait_screen(self, pat, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            if self.has(pat):
                return True
            time.sleep(0.2)
        raise TimeoutError(f"timeout menunggu di layar {pat!r}\n----- layar -----\n{self.screen_text()}")

    # ---------- mengetik ----------
    def type(self, s):
        self.proc.write(s)

    def key(self, *names):
        for n in names:
            self.proc.write(KEYS[n])
            time.sleep(0.05)

    # ---------- proses ----------
    def alive(self):
        return self.proc.isalive()

    def wait_exit(self, timeout=20):
        end = time.time() + timeout
        while time.time() < end and self.proc.isalive():
            time.sleep(0.2)
        return not self.proc.isalive()

    def exitstatus(self):
        return getattr(self.proc, "exitstatus", None)

    def kill(self):
        try:
            if self.proc.isalive():
                self.proc.terminate(force=True)
        except Exception:
            pass
        if self.log:
            self.log.close()
            self.log = None
