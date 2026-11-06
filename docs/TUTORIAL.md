# Tutorial Lengkap claude-code-mini

Panduan ini membawamu dari nol sampai memakai fitur lanjutan: agent background, `/goal`, dan mode sekali
jalan untuk script/CI. Contoh-contohnya diambil dari pemakaian nyata di macOS dan Ubuntu 26.04.

> Mau langsung coba? Bagian 2–4 sudah cukup (± 10 menit). Bagian lain bisa dibaca sambil jalan.

## Daftar isi

1. [Kenalan dulu](#1-kenalan-dulu)
2. [Persiapan](#2-persiapan)
3. [Instalasi](#3-instalasi)
4. [Sesi pertama](#4-sesi-pertama)
5. [Membaca layar](#5-membaca-layar)
6. [Izin dan mode izin](#6-izin-dan-mode-izin)
7. [Cara mengetik pesan](#7-cara-mengetik-pesan)
8. [Mengendalikan Claude saat bekerja](#8-mengendalikan-claude-saat-bekerja)
9. [Mengelola percakapan](#9-mengelola-percakapan)
10. [Model, effort, dan biaya](#10-model-effort-dan-biaya)
11. [Agent dan command di background](#11-agent-dan-command-di-background)
12. [/goal: kerja terus sampai beres](#12-goal-kerja-terus-sampai-beres)
13. [Mode sekali jalan (-p) untuk script dan CI](#13-mode-sekali-jalan--p-untuk-script-dan-ci)
14. [Perintah bawaan Claude Code dan perintah custom](#14-perintah-bawaan-claude-code-dan-perintah-custom)
15. [Konfigurasi per proyek](#15-konfigurasi-per-proyek)
16. [Memakai di server Ubuntu lewat SSH](#16-memakai-di-server-ubuntu-lewat-ssh)
17. [Update dan uninstall](#17-update-dan-uninstall)
18. [Troubleshooting](#18-troubleshooting)
19. [FAQ](#19-faq)
20. [Lampiran](#20-lampiran)

---

## 1. Kenalan dulu

**claude-code-mini** adalah asisten coding di terminal yang memakai mesin Claude Code (lewat
[Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/)), dengan beberapa perbedaan:

- **Selalu memakai API key** (`ANTHROPIC_API_KEY`), jadi biayanya dibayar per pemakaian lewat Claude Console. Kalau
  ternyata mesin Claude memakai sumber login lain (mis. langganan Claude Pro/Max), claude-code-mini langsung
  berhenti supaya tagihan tidak nyasar ke kuota langganan.
- **Tampilan berbahasa Indonesia.**
- **Satu file Python.** Library-nya dipasang ke virtualenv sendiri, tanpa sudo dan tanpa pip global.

Di dalamnya Claude bisa melakukan hal yang sama seperti di Claude Code: membaca dan mengedit file (dengan diff
bernomor baris), menjalankan command, membuat todo list, memakai sub-agent, menjalankan agent/command di
background, plan mode, `/goal`, `/rewind`, dan melanjutkan percakapan lama. Token, biaya, dan pemakaian konteks
selalu terlihat.

Alurnya:

```text
kamu ─▶ claude-code-mini ─▶ Claude Agent SDK ─▶ mesin Claude Code ─▶ API Anthropic
        (tampilan, izin,     (library Python)    (ikut terpasang)
         status, biaya)
```

## 2. Persiapan

| Kebutuhan | Keterangan |
|---|---|
| Sistem operasi | macOS atau Linux (diuji di macOS dan Ubuntu 26.04). Windows: pakai WSL. |
| Python | 3.10 atau lebih baru |
| git | untuk mengambil kode dan update |
| API key Anthropic | dari Claude Console (bagian 2.3) |
| Internet | ke `api.anthropic.com`, dan ke PyPI saat instalasi |

### 2.1 macOS

Python bawaan macOS (`/usr/bin/python3`) masih versi 3.9, terlalu lama. Pasang Python baru lewat
[Homebrew](https://brew.sh):

```bash
brew install python git
python3 --version   # harus 3.10 ke atas
```

Kalau `python3 --version` masih menunjukkan 3.9, panggil Python Homebrew langsung: `/opt/homebrew/bin/python3`
(Apple Silicon) atau `/usr/local/bin/python3` (Intel).

### 2.2 Ubuntu / Debian

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
```

`python3-venv` wajib di Ubuntu; tanpa itu pembuatan virtualenv gagal. `tmux` tidak wajib, tapi berguna di
server (bagian 16).

### 2.3 Membuat API key

1. Buka [Claude Console](https://platform.claude.com) (alamat lama `console.anthropic.com` otomatis diarahkan ke
   sana), lalu masuk atau daftar.
2. Isi kredit atau atur billing. API dibayar per token.
3. Buka halaman [API keys](https://platform.claude.com/settings/keys), buat key baru, lalu salin key-nya (diawali
   `sk-ant-`). Key hanya ditampilkan sekali.

> Perlakukan API key seperti password: jangan di-commit ke git, jangan ditempel di chat, issue, atau screenshot.

## 3. Instalasi

### 3.1 Ambil kode dan pasang

```bash
git clone https://github.com/imransetiadi/claude-code-mini.git
cd claude-code-mini
python3 claude-code-mini.py --setup
```

`--setup` mengerjakan semuanya sekaligus:

1. Membuat virtualenv di `~/.local/share/claude-code-mini/venv`.
2. Memasang `claude-agent-sdk` (sudah membawa mesin Claude Code), `rich`, dan `prompt_toolkit` (plus `gnureadline`
   di macOS).
3. Menyalin script ke `~/.local/share/claude-code-mini/claude-code-mini.py`.
4. Membuat perintah `~/.local/bin/claude-code-mini`.
5. Mengecek PATH dan API key. Kalau ada yang belum beres, ditampilkan perintah untuk membereskannya.

Contoh output di Ubuntu 26.04 yang masih bersih:

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

### 3.2 Tambahkan `~/.local/bin` ke PATH (kalau diminta)

Jalankan perintah yang ditampilkan `--setup`. Untuk macOS (zsh):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

Untuk Ubuntu (bash):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

### 3.3 Simpan API key (sekali saja)

Perintah ini membaca key tanpa menampilkannya di layar, lalu menyimpannya ke file konfigurasi shell. Untuk macOS
(zsh):

```bash
read -rs "K?API key: "; echo; echo "export ANTHROPIC_API_KEY=\"$K\"" >> ~/.zshrc; unset K; source ~/.zshrc
```

Untuk Ubuntu (bash):

```bash
read -rsp "API key: " K; echo; echo "export ANTHROPIC_API_KEY=\"$K\"" >> ~/.bashrc; unset K; source ~/.bashrc
```

Kalau kamu memakai bash di macOS, ganti `~/.zshrc` dengan `~/.bash_profile`. Untuk mengecek tanpa membuka seluruh
key:

```bash
echo "${ANTHROPIC_API_KEY:0:7}…"   # harus muncul: sk-ant-…
```

### 3.4 Cek instalasi

```bash
claude-code-mini --help
```

Kalau muncul `usage: claude-code-mini …`, instalasi selesai.

> **Tanpa `--setup`?** `python3 claude-code-mini.py` juga bisa dijalankan langsung. Kalau library belum ada, kamu
> akan ditawari memasangnya (`Pasang otomatis ke …? [Y/n]`). Hanya saja, perintah `claude-code-mini` baru dibuat
> oleh `--setup`.

> Perintah `claude-code-mini` menjalankan **salinan** script di `~/.local/share/claude-code-mini/`. Setelah
> `git pull` atau mengedit file di folder clone, jalankan `python3 claude-code-mini.py --setup` lagi (bagian 17).

## 4. Sesi pertama

Masuk ke folder proyek, lalu jalankan:

```bash
cd ~/proyek/kalkulator
claude-code-mini
```

Bisa juga `claude-code-mini ~/proyek/kalkulator` dari folder mana saja. Folder itu menjadi wilayah kerja Claude:
isinya bebas dibaca, sedangkan akses ke luar folder ditanyakan dulu.

Contoh sesi nyata di Ubuntu 26.04, pada proyek kecil berisi `kalkulator.py` dan file test-nya (sebagian baris
dipotong):

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

Yang terjadi:

1. Claude menjalankan test. Karena itu command Bash, kamu ditanya dulu. Jawaban `2` berarti izinkan dan jangan
   tanya lagi untuk command itu; aturannya disimpan di `.claude/settings.local.json`.
2. Test gagal. Claude membaca `kalkulator.py`, menemukan bug, lalu mengeditnya. Mode awalnya `acceptEdits`, jadi
   edit langsung diterapkan, tapi diff-nya tetap ditampilkan.
3. Claude menjalankan test lagi tanpa bertanya (sudah diizinkan), dan kali ini lulus.
4. Baris `✓ Selesai` merangkum giliran itu: jumlah langkah, durasi, token, biaya giliran, dan total biaya sesi.

Untuk keluar, tekan **Ctrl+D**, ketik `/exit`, atau tekan **Ctrl+C dua kali**. claude-code-mini lalu menampilkan
total biaya dan perintah untuk melanjutkan percakapan ini nanti:

```text
Total biaya: $0.0379 · Lanjutkan nanti dengan:
  claude-code-mini /home/dev/proyek/kalkulator --resume 93d57805-c135-45ea-88ae-2744df32bf27
```

## 5. Membaca layar

### 5.1 Baris aktivitas

| Tampilan | Arti |
|---|---|
| `● Read(kalkulator.py)` | Claude membaca file |
| `● Bash(python3 -m unittest -v)` | Claude menjalankan command |
| `● Update(kalkulator.py)` + diff | Claude mengedit file (`-` dihapus, `+` ditambah, lengkap dengan nomor baris) |
| `● Write(…)` | Claude membuat atau menimpa file |
| `● Update Todos` + daftar centang | Claude memperbarui todo list-nya |
| `⎿ …` | hasil tool di atasnya; yang panjang dipotong (`… +27 baris`) |
| `●` berwarna ungu dan menjorok | aktivitas sub-agent |

### 5.2 Spinner saat Claude bekerja

```text
⠋ Mengulik… Bash (12s · ↓ 1.2k token · esc untuk berhenti)
```

Kata kerjanya berganti-ganti (Berpikir, Mengulik, Meracik, Ngoding, …). Isinya adalah tool yang sedang
berjalan, lama giliran, token keluaran, dan pengingat bahwa **Esc** menghentikan Claude. Kalau sub-agent sedang
bekerja, progresnya (jumlah tool, token, aktivitas terakhir) ikut ditampilkan.

### 5.3 Toolbar di bawah prompt

```text
  ⏵⏵ auto-terima edit (shift+tab)  ·  sonnet-5-5 · konteks 12% · $0.0379 · ? untuk bantuan
```

Dari kiri: mode izin (ganti dengan Shift+Tab), model, pemakaian konteks, dan total biaya sesi. Kalau ada goal
aktif atau tugas background, muncul tambahan seperti `🎯 goal · 2m 10s · 3 cek (/goal)` dan
`⧗ 1 background (/tasks)`, plus satu baris progres untuk tiap tugas background. Toolbar diperbarui tiap detik,
termasuk saat kamu sedang mengetik.

### 5.4 Status akhir giliran

| Baris | Arti |
|---|---|
| `✓ Selesai · 8 langkah · 14.6 detik · ↓ 818 token · biaya: $0.0379 · total sesi: $0.0379` | giliran selesai normal |
| `⏹ Dihentikan oleh user · ketik instruksi baru, atau 'lanjutkan'` | kamu menekan Esc atau Ctrl+C |
| `✗ Berhenti: batas budget $5 tercapai.` | batas `--budget` tercapai |
| `✗ Berhenti (…)` | giliran berakhir karena error |
| `🔄 Menyambung ulang (1/3)…` | mesin Claude crash atau koneksi putus, sedang dipulihkan otomatis |

## 6. Izin dan mode izin

### 6.1 Apa saja yang perlu izin?

| Jenis tool | Perlakuan |
|---|---|
| Baca-saja dan catatan: `Read`, `Glob`, `Grep`, `TodoWrite`, `WebSearch`, `WebFetch` | selalu langsung jalan (termasuk membuka halaman web) |
| Edit file: `Edit`, `Write`, … | langsung diterapkan di mode `acceptEdits` (mode awal); ditanya di mode `default` |
| `Bash` dan tool lain | ditanya, kecuali sudah diizinkan |
| `AskUserQuestion` | dimatikan; Claude bertanya lewat teks biasa |

### 6.2 Panel izin

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

| Jawaban | Efek |
|---|---|
| `1` atau Enter | izinkan sekali ini |
| `2` | izinkan, lalu simpan aturan yang disarankan Claude Code ke `.claude/settings.local.json` proyek (berlaku seterusnya di proyek itu). Kalau tidak ada saran aturan, izin berlaku untuk tool tersebut sampai claude-code-mini ditutup. |
| `3` | tolak, lalu (opsional) ketik instruksi untuk Claude, mis. "pakai pytest -q saja" |
| Ctrl+C | batalkan: permintaan ditolak dan giliran dihentikan |

Hati-hati: Enter tanpa angka berarti **Ya**.

Kalau permintaan datang dari sub-agent atau agent background, judul panelnya menyebut agent tersebut, misalnya
`Agent #2 “cari pemakaian fungsi X” (background) · Claude minta izin`.

### 6.3 Mode izin

| Mode | Label di toolbar | Perilaku |
|---|---|---|
| `default` | `? tanya dulu sebelum edit & command` | edit file dan command ditanya |
| `acceptEdits` (**mode awal**) | `⏵⏵ auto-terima edit` | edit file langsung diterapkan; command tetap ditanya |
| `plan` | `⏸ plan mode` | Claude hanya menyelidiki dan menyusun rencana, tanpa mengubah apa pun sampai rencananya kamu setujui |
| `bypassPermissions` (`--yolo`) | `⚠ YOLO: tanpa izin` | semua tool jalan tanpa bertanya |
| `dontAsk` | `dontAsk` | tidak pernah bertanya: yang belum diizinkan langsung ditolak |
| `auto` | `⏵ auto mode` | keputusan izin diserahkan ke pemeriksa otomatis Claude Code (fitur baru; tergantung versi Claude Code) |

Cara mengganti mode:

- **Shift+Tab** di prompt: berputar `default → acceptEdits → plan → default`. Teks yang sedang diketik tidak hilang.
- `/mode <nama>`, misalnya `/mode plan`. `/mode` tanpa nama menampilkan mode sekarang.
- Saat start: `--mode plan`, atau `--yolo` (sama dengan `--mode bypassPermissions`).

### 6.4 Plan mode

Plan mode cocok untuk perubahan besar: Claude menyelidiki dulu, lalu menyodorkan rencana untuk kamu setujui.

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

`1` menjalankan rencana dalam mode `acceptEdits`, `2` dalam mode `default`. `3` memintamu menulis apa yang perlu
diubah, lalu Claude merevisi rencananya.

Contoh: `claude-code-mini ~/proyek --mode plan`, lalu ketik `rancang fitur ekspor laporan ke CSV`.

### 6.5 Mode YOLO

`--yolo` membuat semua tool jalan tanpa bertanya, termasuk `rm`, `git push`, dan sejenisnya. Pakai hanya di
container/VM sekali pakai, atau di repo yang aman di-reset.

Claude Code menolak mode YOLO kalau dijalankan sebagai root/sudo. Jalankan sebagai user biasa. Khusus untuk
container/VM sekali pakai, ada jalan pintas: `IS_SANDBOX=1 claude-code-mini . --yolo`.

### 6.6 Melihat dan mencabut izin

- `/allow` menampilkan tool yang otomatis diizinkan, izin sesi, dan aturan yang tersimpan di `.claude/settings*.json`.
- `/allow reset` menghapus izin sesi (file aturan tidak diubah).
- Aturan permanen dicabut dengan mengedit `.claude/settings.local.json` di proyek (bagian `permissions.allow`).

## 7. Cara mengetik pesan

| Ketik | Fungsi |
|---|---|
| Enter | kirim pesan |
| `\` di akhir baris lalu Enter, atau Alt+Enter | baris baru (pesan multi-baris) |
| ↑ / ↓ | riwayat pesan (tersimpan di `~/.claude-code-mini_history`) |
| Tab | lengkapi `/perintah` dan `@path` |
| `?` | sama dengan `/help` |
| `!command` | jalankan command shell langsung |
| `@path` | lampirkan file atau folder |
| `# catatan` | simpan catatan ke `CLAUDE.md` |

Teks multi-baris yang di-paste otomatis jadi satu pesan. Di Terminal macOS, Alt (Option)+Enter baru berfungsi
setelah opsi "Use Option as Meta key" diaktifkan (di iTerm2: Option key → Esc+). Kalau tidak, pakai `\` lalu
Enter.

### 7.1 `!command`: jalankan command sendiri

```text
› !git status --short
! git status --short
  ⎿ M kalkulator.py
  (output akan ikut dikirim ke Claude bersama pesan berikutnya)
› rangkum perubahan ini dan usulkan pesan commit
```

- Dijalankan di folder proyek memakai shell-mu, dengan batas waktu 10 menit.
- Layar menampilkan maksimal 30 baris output; yang dikirim ke Claude maksimal 30.000 karakter terakhir.
- Tidak perlu izin, karena kamu sendiri yang mengetiknya.

### 7.2 `@path`: lampirkan file atau folder

```text
› jelaskan alur fungsi utama di @src/app.py dan @src/utils/
  ⎿ Melampirkan @src/app.py (120 baris)
  ⎿ Melampirkan isi folder @src/utils/ (5 item)
```

- Isi file ikut dilampirkan (maksimal 200 KB; sisanya dipotong). File biner dilewati.
- Untuk folder, yang dilampirkan adalah daftar isinya (tanpa `.git`, `node_modules`, `__pycache__`).
- Tab melengkapi path. Untuk path berspasi, tulis `\ `, misalnya `@laporan\ akhir.md`.

### 7.3 `# catatan`: memori proyek

```text
› # selalu jalankan test dengan python3 -m unittest
✓ Disimpan ke memori proyek (CLAUDE.md)
```

Catatan ditambahkan sebagai butir `- …` ke `CLAUDE.md` (dibuat kalau belum ada). Claude membaca file ini di setiap
sesi, dan langsung diberi tahu tentang catatan baru. Baris yang diawali `##` tidak dianggap catatan.

### 7.4 Mengetik saat Claude bekerja

Kamu boleh mulai mengetik pesan berikutnya selagi Claude bekerja. Ketikanmu tidak hilang: begitu giliran
selesai, teksnya sudah ada di prompt, tinggal tekan Enter.

## 8. Mengendalikan Claude saat bekerja

| Tombol atau perintah | Efek |
|---|---|
| Esc atau Ctrl+C (saat Claude bekerja) | hentikan giliran sekarang. Konteks tetap ada; ketik instruksi baru atau `lanjutkan`. |
| Ctrl+C dua kali dalam 2 detik (di prompt) | keluar |
| Ctrl+D (di prompt) | keluar |
| `/rewind` | kembalikan file ke kondisi sebelum prompt tertentu |

### 8.1 `/rewind`

```text
› /rewind
Kembalikan file ke kondisi sebelum prompt:
   1 tambahkan validasi input
   2 jalankan test-nya, lalu perbaiki kalau ada yang gagal
Pilih nomor (Enter untuk batal) › 1
✓ File dikembalikan ke kondisi sebelum: tambahkan validasi input
```

- Daftarnya berisi sampai 10 prompt terakhir di percakapan ini; nomor 1 adalah yang paling baru.
- Yang dikembalikan hanya perubahan lewat tool edit Claude (`Edit`, `Write`, …). Efek command Bash (mis. `rm`,
  `git commit`, `npm install`) **tidak** ikut dikembalikan; pakai git untuk itu.
- Claude diberi tahu bahwa kamu melakukan rewind, jadi ia tidak bingung di pesan berikutnya.

### 8.2 Pemulihan otomatis

Kalau mesin Claude crash atau koneksi putus, claude-code-mini menyambung ulang sendiri (maksimal 3 kali
berturut-turut) dan melanjutkan percakapan yang sama:

```text
🔄 Menyambung ulang (1/3)… percakapan dilanjutkan, konteks tetap ada.
Tugas terakhir terhenti. Ketik 'lanjutkan' untuk meneruskan, atau beri instruksi lain.
```

### 8.3 Mac tidak tidur

Di macOS, selama claude-code-mini berjalan, Mac dicegah tidur (seperti `caffeinate -i`) supaya pekerjaan panjang
tidak terputus. Pencegahan ini berhenti otomatis saat kamu keluar. Kalau tidak mau, jalankan dengan
`CCMINI_NO_CAFFEINATE=1 claude-code-mini`.

## 9. Mengelola percakapan

Setiap percakapan tersimpan otomatis per folder oleh Claude Code, di `~/.claude/projects/`.

| Cara | Fungsi |
|---|---|
| `claude-code-mini -c` | lanjutkan percakapan terakhir di folder ini |
| `claude-code-mini -r` | pilih dari daftar percakapan lama |
| `claude-code-mini --resume <ID>` | lanjutkan percakapan tertentu (ID-nya ditampilkan saat keluar) |
| `/resume` | pindah ke percakapan lama tanpa keluar |
| `/clear` | mulai percakapan baru (konteks lama dibuang) |
| `/compact [instruksi]` | ringkas percakapan supaya konteks lega (perintah Claude Code) |
| `/context` | lihat pemakaian konteks dan rinciannya per kategori |

Contoh daftar di `/resume` atau `-r`:

```text
Percakapan lama di folder ini:
   1    5 menit lalu  jalankan test-nya, lalu perbaiki kalau ada yang gagal ⎇ main
   2      2 jam lalu  tambahkan fitur ekspor CSV ⎇ fitur/csv
Pilih nomor (Enter untuk batal) ›
```

Saat percakapan dilanjutkan, beberapa pesan terakhirnya ditampilkan sebagai pengingat. Auto-compact Claude Code
tetap aktif: kalau konteks hampir penuh, percakapan diringkas otomatis.

## 10. Model, effort, dan biaya

| Alias | Model |
|---|---|
| `opus` (bawaan) | `claude-opus-5-5` |
| `sonnet` | `claude-sonnet-5-5` |
| `haiku` | `claude-haiku-5-5` |
| `fable` | `claude-fable-5-1` |

- Saat start: `claude-code-mini --model sonnet` (atau ID lengkap model lain).
- Di tengah sesi: `/model` menampilkan model sekarang, `/model haiku` menggantinya.
- `--effort low|medium|high|xhigh|max` mengatur seberapa keras Claude berpikir (bawaan: setelan model).
- `--budget 5` membatasi biaya sesi ini sampai $5. Kalau tercapai, Claude berhenti dengan pesan
  `✗ Berhenti: batas budget $5 tercapai.`
- `/cost` menampilkan total biaya. `/status` merangkum sesi: folder, model, mode, sumber auth, session ID, versi
  Claude Code, tugas background, goal, dan biaya.

Tips hemat:

- Pakai `haiku` untuk tugas ringan (penjelasan singkat, rename), `sonnet`/`opus` untuk pekerjaan berat.
- `/clear` saat ganti topik, `/compact` kalau percakapan sudah panjang.
- Lampirkan file seperlunya saja.
- Selalu pasang `--budget` untuk pekerjaan panjang atau otomatis.

## 11. Agent dan command di background

Claude bisa menjalankan command yang lama (server dev, build, test suite) atau sub-agent di background, sambil
tetap melayanimu. Cukup minta, misalnya:

- `jalankan npm run dev di background, lalu cek apakah halaman utama bisa dibuka`
- `pakai agent background untuk mencari semua pemakaian fungsi hitung_pajak; sementara itu jelaskan struktur foldernya`

Selama tugas berjalan, toolbar kira-kira terlihat seperti ini:

```text
  ⏵⏵ auto-terima edit (shift+tab)  ·  opus-5-5 · konteks 9% · $0.0412  ·  ⧗ 2 background (/tasks)
  ⧗ #1 Jalankan server dev · bash · 1m 05s · ⎿ ready on http://localhost:3000
  ⧗ #2 Cari pemakaian hitung_pajak · agent · 40s · 12 tool · 8.1k token · Grep(hitung_pajak)
```

- Progres tampil live di bawah prompt dan diperbarui tiap detik, bahkan saat kamu sedang mengetik. Untuk command,
  yang tampil adalah baris output terakhirnya; untuk agent, aktivitas terakhirnya.
- Log aktivitas agent dicetak di atas prompt. `/tasks log` mematikan atau menyalakannya.
- Begitu tugas selesai, claude-code-mini mengumumkannya dan Claude **otomatis menanggapi hasilnya**
  (`✓ Respons otomatis selesai`). Esc menghentikan respons otomatis itu.
- Permintaan izin dari agent background muncul di atas prompt, lengkap dengan nama agent-nya.

| Perintah | Fungsi |
|---|---|
| `/tasks` | daftar semua agent dan tugas background (yang berjalan maupun yang selesai) |
| `/tasks 2` | detail tugas #2: tugasnya, aktivitas terakhir, dan output terakhir (command) atau laporan (agent) |
| `/tasks log` | nyalakan/matikan log aktivitas di layar |
| `/stop 2` | hentikan tugas #2 (`/kill 2` juga bisa) |
| `/stop all` | hentikan semua tugas background |

Tugas background ikut berhenti kalau proses Claude ditutup (`/exit`, `/clear`, `/resume`); claude-code-mini
menanyakannya dulu. Di mode `-p`, claude-code-mini menunggu semua tugas background (dan tanggapan Claude atas
hasilnya) selesai sebelum keluar.

## 12. /goal: kerja terus sampai beres

`/goal` membuat Claude terus bekerja sampai kondisi yang kamu tentukan terpenuhi. Fitur ini memakai `/goal`
bawaan Claude Code: setiap kali Claude hendak berhenti, sebuah pemeriksa (model kecil) membaca percakapan dan
menilai apakah kondisinya sudah terpenuhi. Kalau belum, Claude lanjut bekerja di giliran yang sama.

Contoh tampilan:

```text
› /goal semua test lulus (python3 -m unittest exit 0) dan git status bersih, maksimal 20 giliran
🎯 Goal ditetapkan: semua test lulus (python3 -m unittest exit 0) dan git status bersih, maksimal 20 giliran
   Claude langsung mengerjakannya. Tiap kali ia mau berhenti, pemeriksa (model kecil, kena biaya per cek) …
   …
🎯 Cek goal #1 · belum terpenuhi · git status masih menunjukkan perubahan yang belum di-commit
   …
🎯 Goal berakhir: semua test lulus (…) · 1 cek · 1m 12s · biaya $0.0831
   pemeriksa menilai kondisinya terpenuhi — atau mustahil dicapai; lihat jawaban terakhir Claude di atas.
```

| Perintah | Fungsi |
|---|---|
| `/goal <kondisi>` | set goal (mengganti goal sebelumnya) dan langsung mulai |
| `/goal` | status: kondisi, durasi, jumlah cek, alasan cek terakhir, biaya sejak goal diset |
| `/goal clear` | batalkan goal (juga bisa: `stop`, `off`, `reset`, `none`, `cancel`, `batal`, `hapus`) |

Yang perlu diketahui:

- Selama goal aktif, toolbar menampilkan `🎯 goal · 2m 10s · 3 cek` (dengan `⏸` kalau dijeda), dan `/status`
  punya baris Goal.
- Goal tetap aktif untuk pesan-pesan berikutnya, sampai pemeriksa menilainya selesai atau kamu membatalkannya.
- **Esc** hanya menjeda goal (`⏸ Goal dijeda · dihentikan user`). Kirim pesan apa pun (mis. `lanjutkan`) untuk
  meneruskan.
- Kalau Claude berkali-kali berturut-turut dinilai belum memenuhi goal tanpa memakai tool sama sekali, gilirannya
  dihentikan paksa dan goal dijeda. Biasanya ini tanda kondisinya tidak bisa dibuktikan dari percakapan, atau
  Claude butuh input darimu. Batasnya bawaan Claude Code (8x) dan bisa diubah dengan
  `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`.
- `🎯 Goal berakhir` sengaja netral: Claude Code tidak memberi tahu apakah kondisinya **terpenuhi** atau pemeriksa
  menilainya **mustahil**. Baca jawaban terakhir Claude untuk memastikan.
- Melanjutkan percakapan (`--resume`, `-c`) ikut memulihkan goal yang belum selesai; `/clear` membatalkannya.
- Di mode `plan`, Claude tidak bisa mengedit file, jadi goal yang butuh perubahan file tidak akan tercapai
  (claude-code-mini memperingatkannya). Di mode `default`/`acceptEdits`, command yang belum diizinkan tetap
  ditanya; jawab `2` (jangan tanya lagi), atau pakai `--yolo` di sandbox kalau mau ditinggal.
- Setiap cek adalah satu panggilan API kecil: murah, tapi tetap dihitung. Jumlahnya ikut tampil di statistik
  giliran (`🎯 N cek`).

Menulis kondisi yang baik:

| ✅ Bagus | ❌ Kurang bagus |
|---|---|
| `pytest -q exit 0 dan git status bersih, maksimal 20 giliran` | `kodenya rapi` |
| `curl -s localhost:8000/health mengembalikan {"ok":true}, maksimal 15 giliran` | `server jalan dengan baik` |
| `file docs/API.md ada dan memuat semua endpoint di app/routes.py` | `dokumentasinya lengkap` |

Dua prinsipnya: (1) kondisinya bisa dibuktikan dari output yang terlihat di percakapan, karena pemeriksa tidak
menjalankan apa pun sendiri; (2) beri batas giliran, karena tidak ada batas bawaan.

## 13. Mode sekali jalan (-p) untuk script dan CI

```bash
claude-code-mini ~/proyek -p "jelaskan arsitektur repo ini dalam 10 poin" > ringkasan.txt
claude-code-mini . --model haiku -p "cari TODO yang terlupa dan buat daftarnya"
claude-code-mini . --budget 3 -p "/goal semua test lulus (pytest -q exit 0), maksimal 20 giliran"
```

- Banner tidak ditampilkan; aktivitas dan jawaban Claude dicetak sebagai teks biasa.
- Prompt yang diawali `/` dikirim apa adanya, misalnya `-p "/compact"` atau `-p "/goal …"`.
- claude-code-mini menunggu tugas background selesai sebelum keluar.
- Kalau goal belum selesai, perintah untuk melanjutkannya ikut ditampilkan:
  `claude-code-mini <folder> --resume <ID>`. Lanjutkan secara interaktif, atau tetap otomatis dengan
  `claude-code-mini <folder> --resume <ID> -p "lanjutkan"`.

Exit code:

| Kode | Arti |
|---|---|
| `0` | sukses |
| `1` | gagal: error, budget habis, pertanyaan izin yang tidak bisa dijawab karena tidak ada terminal, API key belum di-set, atau mesin Claude gagal start |
| `3` | goal dari `/goal` belum selesai, ditolak, atau dihapus karena error |
| `130` | dihentikan dengan Ctrl+C di terminal |

Contoh di script:

```bash
if claude-code-mini . --budget 2 -p "/goal pytest -q exit 0, maksimal 15 giliran"; then
  echo "beres"
else
  echo "belum beres (exit $?)"
fi
```

Soal izin: di mode `-p`, pertanyaan izin tetap muncul kalau ada terminal. Di CI atau cron (tanpa terminal),
pertanyaan izin otomatis ditolak (`✗ Izin Bash ditolak: tidak ada terminal untuk menjawab.`), gilirannya
dihentikan, dan exit code-nya 1. Siapkan aturan izin di `.claude/settings.json` (bagian 15), atau jalankan di
container sekali pakai dengan `--yolo`.

## 14. Perintah bawaan Claude Code dan perintah custom

Perintah yang ditangani claude-code-mini sendiri ada di lampiran B. Perintah lain yang dikenal Claude Code
diteruskan apa adanya, misalnya:

- `/compact [instruksi]` untuk meringkas percakapan.
- `/init` untuk membuat `CLAUDE.md` berdasarkan isi proyek.

Daftar lengkapnya (tergantung versi Claude Code dan isi proyekmu) ada di `/help`, di bagian "Perintah Claude Code /
proyek", dan muncul saat kamu menekan Tab setelah `/`.

### Perintah custom

Buat file Markdown di `.claude/commands/` proyek. Nama file menjadi nama perintah:

```bash
mkdir -p .claude/commands
cat > .claude/commands/rilis.md <<'EOF'
Siapkan rilis versi $ARGUMENTS:
1. Perbarui CHANGELOG.md dari commit sejak tag terakhir.
2. Naikkan versi di pyproject.toml.
3. Jalankan test; berhenti kalau ada yang gagal.
EOF
```

Lalu di claude-code-mini ketik `/rilis 1.4.0`. `$ARGUMENTS` diganti dengan teks setelah nama perintah.

## 15. Konfigurasi per proyek

claude-code-mini hanya membaca pengaturan **tingkat proyek**:

| File | Fungsi |
|---|---|
| `CLAUDE.md` | instruksi permanen untuk Claude: cara menjalankan test, gaya kode, larangan. Buat dengan `/init`, tambah dengan `# catatan`. |
| `.claude/settings.json` | aturan izin bersama (boleh di-commit) |
| `.claude/settings.local.json` | aturan izin pribadi; jawaban "2 (jangan tanya lagi)" disimpan di sini. Sebaiknya dimasukkan ke `.gitignore`. |
| `.claude/commands/*.md` | perintah custom (bagian 14) |

Pengaturan tingkat user (`~/.claude/settings.json`, `~/.claude/CLAUDE.md`) tidak dipakai.

Contoh `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["Bash(npm test:*)", "Bash(npm run lint)", "Bash(git status)", "Bash(git diff:*)"],
    "deny": ["Bash(git push:*)", "Read(./.env)"]
  }
}
```

## 16. Memakai di server Ubuntu lewat SSH

```bash
ssh -i kunci.pem ubuntu@ALAMAT-SERVER
sudo apt update && sudo apt install -y python3 python3-venv git tmux
git clone https://github.com/imransetiadi/claude-code-mini.git
python3 claude-code-mini/claude-code-mini.py --setup
```

Lalu simpan API key (bagian 3.3, versi bash) dan, kalau diminta, tambahkan `~/.local/bin` ke PATH.

Pakai **tmux** supaya pekerjaan tidak mati saat koneksi SSH putus:

```bash
tmux new -s ccm              # buka sesi tmux bernama ccm
claude-code-mini ~/proyek    # bekerja seperti biasa
# lepas dari sesi: tekan Ctrl+B lalu D (claude-code-mini tetap berjalan di server)
tmux attach -t ccm           # sambung lagi nanti
```

Tips:

- Jangan jalankan sebagai root. Mode YOLO ditolak Claude Code untuk root (kecuali `IS_SANDBOX=1` di container/VM
  sekali pakai).
- Mau menjalankan langsung dari laptop tanpa masuk shell, misalnya `ssh server 'claude-code-mini … -p …'`?
  `~/.bashrc` bawaan Ubuntu berhenti lebih awal untuk shell non-interaktif, jadi `ANTHROPIC_API_KEY` yang ditaruh di
  bagian bawahnya tidak terbaca. Pindahkan baris `export ANTHROPIC_API_KEY=…` dan PATH ke paling atas `~/.bashrc`,
  atau jalankan lewat `bash -lic '…'`.

## 17. Update dan uninstall

Update ke versi terbaru:

```bash
cd ~/claude-code-mini     # folder hasil git clone
git pull
python3 claude-code-mini.py --setup
```

Kalau hanya ingin memperbarui library (mis. `claude-agent-sdk` yang membawa mesin Claude Code terbaru):

```bash
claude-code-mini --setup
```

Uninstall:

```bash
rm -f ~/.local/bin/claude-code-mini ~/.claude-code-mini_history
rm -rf ~/.local/share/claude-code-mini
```

Hapus juga folder clone dan baris `export ANTHROPIC_API_KEY=…`/PATH di `~/.zshrc` atau `~/.bashrc` kalau tidak
dipakai lagi. Riwayat percakapan ada di `~/.claude/projects/` (dipakai bersama Claude Code resmi); hapus manual
kalau perlu.

## 18. Troubleshooting

| Gejala | Penyebab dan solusi |
|---|---|
| `ANTHROPIC_API_KEY belum di-set.` | Key belum di-export di shell ini. Ulangi bagian 3.3, atau buka terminal baru. |
| `✗ Dihentikan: Claude memakai auth '…', bukan ANTHROPIC_API_KEY.` | Mesin Claude memakai sumber login lain, jadi claude-code-mini sengaja berhenti supaya tidak memotong kuota langganan. Pastikan `ANTHROPIC_API_KEY` ter-export di terminal yang sama. |
| `✗ Butuh Python 3.10 atau lebih baru` | Pasang Python yang lebih baru (bagian 2.1/2.2), lalu jalankan `--setup` dengan Python itu. |
| `✗ Gagal membuat virtualenv`, atau error tentang `ensurepip` | Ubuntu/Debian: `sudo apt install -y python3-venv`, lalu ulangi `--setup`. |
| `✗ pip install gagal` | Cek koneksi internet/proxy ke PyPI, lalu ulangi `--setup`. |
| `claude-code-mini: command not found` | `~/.local/bin` belum ada di PATH (bagian 3.2). Atau buka terminal baru. |
| `Binary Claude Code tidak ditemukan.` | Instalasi library tidak lengkap. Jalankan `python3 claude-code-mini.py --setup`. |
| `✗ Mesin Claude Code gagal start` | Cek internet/proxy ke `api.anthropic.com` dan keabsahan API key, lalu update dengan `--setup`. Detail error dari mesin Claude tampil di atas pesan ini. |
| `Output tool terlalu besar untuk buffer (64 MB)` | Jalankan dengan `--buffer-mb 128`, atau minta Claude membaca file per bagian. |
| `⚠ Rate limit: …` | Batas pemakaian API akunmu tercapai. Tunggu sebentar, atau cek limit di Claude Console. |
| `Claude Code menolak mode YOLO kalau dijalankan sebagai root/sudo` | Jalankan sebagai user biasa. Khusus container/VM sekali pakai: `IS_SANDBOX=1`. |
| Alt+Enter tidak membuat baris baru (macOS) | Aktifkan "Use Option as Meta key" di Terminal, atau akhiri baris dengan `\`. |
| Toolbar atau tombol Esc tidak berfungsi di Windows | Jalankan di WSL. |

## 19. FAQ

**Berapa biayanya?**
Tergantung model dan panjang pekerjaan; Anthropic menghitungnya per token. Biaya per giliran dan total sesi selalu
tampil (di toolbar, di baris `✓ Selesai`, dan lewat `/cost`). Contoh di bagian 4 (Sonnet, 8 langkah) menghabiskan
sekitar $0.04. Batasi dengan `--budget`.

**Apakah memakai kuota langganan Claude Pro/Max?**
Tidak. claude-code-mini hanya mau berjalan dengan `ANTHROPIC_API_KEY`; kalau terdeteksi sumber login lain, ia
berhenti.

**Apa bedanya dengan Claude Code resmi?**
Mesinnya sama. claude-code-mini menambahkan tampilan berbahasa Indonesia, info biaya dan token yang live,
pemantauan tugas background di toolbar, dan pengaman API key. Sebaliknya, beberapa hal tidak tersedia: tool tanya
jawab pilihan ganda (`AskUserQuestion`), integrasi IDE, login langganan, dan pengaturan tingkat user.

**Apakah bisa di Windows?**
Lewat WSL (Ubuntu). Di Windows asli, tombol Esc tidak didukung dan perintah `claude-code-mini` tidak dibuat.

**Di mana percakapan disimpan?**
Di `~/.claude/projects/`, dalam format Claude Code. Riwayat ketikanmu ada di `~/.claude-code-mini_history`.

## 20. Lampiran

### A. Opsi baris perintah

```text
usage: claude-code-mini [-h] [--model MODEL]
                        [--mode {default,acceptEdits,plan,auto,bypassPermissions,dontAsk}]
                        [--effort {low,medium,high,xhigh,max}]
                        [--budget BUDGET] [--yolo] [-c] [-r [SESSION_ID]]
                        [-p PROMPT] [--buffer-mb BUFFER_MB] [--setup]
                        [repo]
```

| Opsi | Fungsi |
|---|---|
| `repo` | folder proyek (bawaan: folder sekarang) |
| `--model MODEL` | model atau alias `opus`/`sonnet`/`haiku`/`fable` (bawaan: `claude-opus-5-5`) |
| `--mode MODE` | mode izin awal (bawaan: `acceptEdits`) |
| `--effort LEVEL` | `low`, `medium`, `high`, `xhigh`, `max` |
| `--budget USD` | batas biaya sesi, misalnya `5` |
| `--yolo` | semua tool tanpa tanya (`bypassPermissions`) |
| `-c`, `--continue` | lanjutkan percakapan terakhir |
| `-r`, `--resume [ID]` | lanjutkan percakapan lama (tanpa ID: pilih dari daftar) |
| `-p`, `--print PROMPT` | sekali jalan lalu keluar (exit code di bagian 13) |
| `--buffer-mb MB` | batas ukuran output tool (bawaan: 64) |
| `--setup` | pasang/update library dan perintah `claude-code-mini` |

### B. Perintah di dalam sesi

| Perintah | Fungsi |
|---|---|
| `/help` (atau `?`) | bantuan |
| `/status` | info sesi: model, mode, folder, session ID, auth, versi Claude Code, background, goal, biaya |
| `/cost` | total biaya sesi |
| `/context` | pemakaian context window |
| `/model [alias atau ID]` | lihat atau ganti model |
| `/mode [nama]` | lihat atau ganti mode izin |
| `/allow` / `/allow reset` | lihat izin / hapus izin sesi |
| `/tasks` / `/tasks <no>` / `/tasks log` | daftar tugas background / detail / log on-off |
| `/stop <no>` / `/stop all` | hentikan tugas background (alias `/kill`) |
| `/goal [kondisi]` / `/goal clear` | set goal atau lihat status / batalkan goal |
| `/resume` | lanjutkan percakapan lama di folder ini |
| `/rewind` | kembalikan file ke kondisi sebelum prompt tertentu |
| `/clear` | mulai percakapan baru |
| `/exit` (atau `/quit`) | keluar |

### C. Tombol

| Tombol | Fungsi |
|---|---|
| Enter | kirim pesan |
| `\` + Enter, Alt+Enter | baris baru |
| Tab | lengkapi `/perintah` dan `@path` |
| ↑ / ↓ | riwayat pesan |
| Shift+Tab | ganti mode izin |
| Esc | hentikan Claude, atau tutup menu pelengkapan |
| Ctrl+C | hentikan Claude; di prompt tekan 2x untuk keluar; di pertanyaan = batal |
| Ctrl+D | keluar |

### D. File dan folder

| Lokasi | Isi |
|---|---|
| `~/.local/bin/claude-code-mini` | perintah peluncur |
| `~/.local/share/claude-code-mini/claude-code-mini.py` | salinan script yang dijalankan |
| `~/.local/share/claude-code-mini/venv/` | library: claude-agent-sdk (dengan mesin Claude Code), rich, prompt_toolkit |
| `~/.claude-code-mini_history` | riwayat ketikan |
| `~/.claude/projects/` | percakapan (format Claude Code) |
| `<proyek>/CLAUDE.md`, `<proyek>/.claude/` | pengaturan proyek (bagian 15) |

Kalau `XDG_DATA_HOME` di-set, folder data pindah ke `$XDG_DATA_HOME/claude-code-mini`.

### E. Environment variable

| Variabel | Fungsi |
|---|---|
| `ANTHROPIC_API_KEY` | API key (wajib) |
| `CCMINI_NO_CAFFEINATE=1` | macOS: jangan cegah Mac tidur |
| `IS_SANDBOX=1` | izinkan mode YOLO sebagai root (hanya untuk container/VM sekali pakai) |
| `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` | batas penolakan beruntun `/goal` (bawaan Claude Code: 8) |
| `XDG_DATA_HOME` | lokasi folder data (bawaan: `~/.local/share`) |
