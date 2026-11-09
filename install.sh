#!/usr/bin/env bash
# claude-code-mini: installer sekali jalan untuk macOS dan Linux (Ubuntu/Debian).
#
#     curl -fsSL https://raw.githubusercontent.com/imransetiadi/claude-code-mini/main/install.sh | bash
#
# Yang dikerjakan:
#   1. Mencari Python 3.10+ yang bisa membuat virtualenv. Kalau belum ada, memasangnya setelah bertanya:
#      lewat Homebrew (macOS), apt-get (Ubuntu/Debian, butuh sudo), atau uv (tanpa sudo, ke ~/.local).
#   2. Mengunduh claude-code-mini.py ke ~/.local/share/claude-code-mini/ lalu menjalankan --setup:
#      virtualenv, library, dan perintah ~/.local/bin/claude-code-mini.
#   3. Menambahkan blok kecil ke file startup shell (~/.zshrc, ~/.bashrc atau ~/.bash_profile) yang menaruh
#      ~/.local/bin di PATH dan memuat API key.
#   4. Meminta API key (tidak tampil di layar), mengeceknya ke Anthropic (GET /v1/models, gratis), lalu
#      menyimpannya di ~/.config/claude-code-mini/api_key, yang hanya bisa dibaca akunmu.
# Menjalankan installer ini lagi = update ke versi terbaru; API key yang sudah tersimpan tidak ditanya lagi.
#
# Variabel opsional:
#   CCMINI_NEW_KEY=1  minta API key baru walaupun sudah ada yang tersimpan
#   CCMINI_PYTHON     Python yang dipakai (path lengkap), kalau tidak mau dicari otomatis
#   CCMINI_REF        branch/tag/commit yang diunduh (bawaan: main); CCMINI_REPO (bawaan: imransetiadi/claude-code-mini)
#   CCMINI_SOURCE     file claude-code-mini.py lokal; dipakai otomatis kalau installer dijalankan dari clone repo
# Tanpa terminal (CI, Docker) installer tidak bertanya: yang perlu dipasang langsung dipasang, API key dilewati.
#
# Semua langkah ada di dalam fungsi dan baru dijalankan di baris terakhir, jadi unduhan yang terputus tidak
# menjalankan apa pun. Ditulis untuk bash 3.2 (bawaan macOS).

if [ -z "${BASH_VERSION:-}" ]; then
    echo "Jalankan installer ini dengan bash:" >&2
    echo "  curl -fsSL https://raw.githubusercontent.com/imransetiadi/claude-code-mini/main/install.sh | bash" >&2
    exit 1
fi

RC_BEGIN="# >>> claude-code-mini >>>"
RC_END="# <<< claude-code-mini <<<"
KEY_RE='^sk-ant-[A-Za-z0-9_-]{10,}$'

# ---------------------------------------------------------------- tampilan
step() { printf '→ %s\n' "$*"; }
ok() { printf '%s✓%s %s\n' "$C_OK" "$C_0" "$*"; }
warn() { printf '%s!%s %s\n' "$C_WARN" "$C_0" "$*"; }
fail() {
    printf '%s✗%s %s\n' "$C_ERR" "$C_0" "$*" >&2
    exit 1
}
tilde() { # /home/budi/.zshrc -> ~/.zshrc (untuk pesan)
    case "$1" in
        "$HOME"/*) printf '%s/%s' "~" "${1#"$HOME"/}" ;;
        *) printf '%s' "$1" ;;
    esac
}

# ask "pertanyaan" -> 0 kalau ya. Tanpa terminal: otomatis ya.
ask() {
    [ "$HAVE_TTY" = 1 ] || return 0
    local a
    printf '%s [Y/n] ' "$1" >/dev/tty
    IFS= read -r a </dev/tty || a=""
    case "$a" in
        "" | y | Y | ya | Ya | YA | yes | Yes | YES) return 0 ;;
        *) return 1 ;;
    esac
}

download() { # download URL FILE
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 2 -o "$2" "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$2" "$1"
    elif [ -n "${PY:-}" ]; then
        "$PY" -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$1" "$2"
    else
        return 1
    fi
}

# ---------------------------------------------------------------- Python
py_ver() { "$1" -c 'import platform; print(platform.python_version())' 2>/dev/null; }

# Isi PY dengan Python >= 3.10 yang bisa membuat virtualenv (modul venv + ensurepip). PY_NOVENV = Python yang
# versinya cukup tapi belum punya venv (Ubuntu/Debian: paket python3-venv belum terpasang).
find_python() {
    local c cands=() uvbin
    PY=""
    PY_NOVENV=""
    [ -n "${CCMINI_PYTHON:-}" ] && cands+=("$CCMINI_PYTHON")
    for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        c="$(command -v "$c" 2>/dev/null)" && cands+=("$c")
    done
    uvbin="${XDG_BIN_HOME:-$HOME/.local/bin}"
    cands+=(/opt/homebrew/bin/python3 /usr/local/bin/python3 "$uvbin/python3.13" "$uvbin/python3")
    for c in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
        cands+=("$c")
    done
    for c in "${cands[@]}"; do
        [ -x "$c" ] || continue
        # macOS tanpa Command Line Tools: /usr/bin/python3 memunculkan dialog instalasi, jadi dilewati
        if [ "$c" = /usr/bin/python3 ] && [ "$OS" = macos ] && ! xcode-select -p >/dev/null 2>&1; then
            continue
        fi
        "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1 || continue
        if "$c" -c 'import venv, ensurepip' >/dev/null 2>&1; then
            PY="$c"
            return 0
        fi
        [ -n "$PY_NOVENV" ] || PY_NOVENV="$c"
    done
    return 1
}

SUDO=""
can_sudo() { # root: tanpa sudo. Tanpa terminal: hanya kalau sudo tidak minta password.
    if [ "$(id -u)" = 0 ]; then
        SUDO=""
        return 0
    fi
    command -v sudo >/dev/null 2>&1 || return 1
    if [ "$HAVE_TTY" = 1 ]; then
        SUDO="sudo"
        return 0
    fi
    sudo -n true 2>/dev/null || return 1
    SUDO="sudo -n"
}

apt_install() {
    step "apt-get install $* …"
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get update -qq </dev/null &&
        $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" </dev/null
}

install_uv_python() {
    local uv="" c
    for c in "$(command -v uv 2>/dev/null)" "${XDG_BIN_HOME:-$HOME/.local/bin}/uv" "$HOME/.cargo/bin/uv"; do
        if [ -n "$c" ] && [ -x "$c" ]; then
            uv="$c"
            break
        fi
    done
    if [ -z "$uv" ]; then
        step "Memasang uv (pengelola Python dari Astral, https://docs.astral.sh/uv/) ke ~/.local/bin …"
        download https://astral.sh/uv/install.sh "$TMP/uv-install.sh" || {
            warn "Gagal mengunduh installer uv."
            return 1
        }
        UV_NO_MODIFY_PATH=1 sh "$TMP/uv-install.sh" --quiet </dev/null || {
            warn "Gagal memasang uv."
            return 1
        }
        uv="${XDG_BIN_HOME:-$HOME/.local/bin}/uv"
        [ -x "$uv" ] || {
            warn "uv tidak ditemukan setelah dipasang."
            return 1
        }
    fi
    step "uv python install 3.13 …"
    "$uv" python install 3.13 </dev/null || return 1
    CCMINI_PYTHON="$("$uv" python find 3.13 2>/dev/null)" || return 1
}

ensure_python() {
    if find_python; then
        ok "Python $(py_ver "$PY") ($PY)"
        return 0
    fi
    if [ -n "$PY_NOVENV" ]; then
        warn "Python $(py_ver "$PY_NOVENV") sudah ada, tapi modul venv-nya belum (paket python3-venv)."
    else
        warn "Python 3.10 atau yang lebih baru belum ada."
    fi
    if [ "$OS" = linux ] && command -v apt-get >/dev/null 2>&1 && can_sudo; then
        local pkgs=(python3 python3-venv)
        command -v git >/dev/null 2>&1 || pkgs+=(git)
        if ask "Pasang ${pkgs[*]} lewat apt-get${SUDO:+ (butuh sudo)}?"; then
            if apt_install "${pkgs[@]}" && find_python; then
                ok "Python $(py_ver "$PY") ($PY)"
                return 0
            fi
            warn "Lewat apt-get belum berhasil, coba cara lain."
        fi
    elif [ "$OS" = macos ] && command -v brew >/dev/null 2>&1; then
        if ask "Pasang Python lewat Homebrew (brew install python)?"; then
            step "brew install python …"
            if brew install python </dev/null && find_python; then
                ok "Python $(py_ver "$PY") ($PY)"
                return 0
            fi
            warn "Lewat Homebrew belum berhasil, coba cara lain."
        fi
    fi
    if ask "Pasang Python 3.13 lewat uv ke ~/.local (tanpa sudo)?"; then
        if install_uv_python && find_python; then
            ok "Python $(py_ver "$PY") ($PY)"
            return 0
        fi
    fi
    if [ "$OS" = macos ]; then
        fail "Butuh Python 3.10+. Pasang dulu (mis. brew install python, atau dari https://www.python.org/downloads/macos/), lalu jalankan installer ini lagi."
    fi
    fail "Butuh Python 3.10+ dengan venv. Ubuntu/Debian: sudo apt install -y python3 python3-venv, lalu jalankan installer ini lagi."
}

# ---------------------------------------------------------------- claude-code-mini
fetch_script() {
    local src="${CCMINI_SOURCE:-}" new="$DATA_DIR/.claude-code-mini.py.new" here url
    if [ -z "$src" ] && [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
        here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        [ -f "$here/claude-code-mini.py" ] && src="$here/claude-code-mini.py"
    fi
    mkdir -p "$DATA_DIR" || fail "Tidak bisa membuat folder $DATA_DIR"
    if [ -n "$src" ]; then
        step "Memakai $src"
        cp "$src" "$new" || fail "Gagal menyalin $src"
    else
        url="https://raw.githubusercontent.com/$REPO_SLUG/$REF/claude-code-mini.py"
        step "Mengunduh claude-code-mini.py ($REF) …"
        download "$url" "$new" || fail "Gagal mengunduh $url"
    fi
    # unduhan yang terpotong atau halaman error tidak boleh menggantikan versi yang sudah terpasang
    if ! "$PY" -c 'import ast, sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$new" 2>/dev/null ||
        ! grep -q "def bootstrap" "$new"; then
        rm -f "$new"
        fail "File claude-code-mini.py yang didapat tidak utuh. Coba jalankan installer ini lagi."
    fi
    mv -f "$new" "$DATA_DIR/claude-code-mini.py" || fail "Gagal memasang $DATA_DIR/claude-code-mini.py"
}

run_setup() {
    step "Menjalankan claude-code-mini --setup …"
    CCMINI_INSTALLER=1 "$PY" "$DATA_DIR/claude-code-mini.py" --setup </dev/null ||
        fail "--setup gagal (lihat pesan di atas). Perbaiki penyebabnya lalu jalankan installer ini lagi."
}

# ---------------------------------------------------------------- shell: PATH + API key
detect_rc() {
    SHELL_NAME="$(basename "${SHELL:-bash}")"
    RC=""
    case "$SHELL_NAME" in
        zsh) RC="${ZDOTDIR:-$HOME}/.zshrc" ;;
        bash)
            if [ "$OS" = macos ]; then # shell login: bash membaca file pertama yang ada dari ketiganya
                RC="$HOME/.bash_profile"
                [ -f "$HOME/.bash_profile" ] || { [ -f "$HOME/.bash_login" ] && RC="$HOME/.bash_login"; } ||
                    { [ -f "$HOME/.profile" ] && RC="$HOME/.profile"; } || true
            else
                RC="$HOME/.bashrc"
            fi
            ;;
        fish) RC="" ;;
        *) RC="$HOME/.profile" ;;
    esac
}

write_rc_block() {
    if [ -z "$RC" ]; then
        warn "Shell $SHELL_NAME: tambahkan sendiri ~/.local/bin ke PATH dan muat API key-nya, misalnya:"
        printf '    fish_add_path ~/.local/bin\n'
        printf '    echo %s >> ~/.config/fish/config.fish\n' \
            "'test -r ~/.config/claude-code-mini/api_key; and read -gx ANTHROPIC_API_KEY < ~/.config/claude-code-mini/api_key'"
        return 0
    fi
    if [ -f "$RC" ] && grep -qF "$RC_BEGIN" "$RC"; then
        ok "PATH dan API key sudah dimuat oleh $(tilde "$RC")"
        return 0
    fi
    # shellcheck disable=SC2016 # sengaja tanpa ekspansi: $PATH dan $HOME dibaca saat shell baru dimulai
    {
        printf '\n%s\n' "$RC_BEGIN"
        printf '%s\n' 'case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac'
        printf '%s\n' 'if [ -r "$HOME/.config/claude-code-mini/api_key" ]; then read -r ANTHROPIC_API_KEY < "$HOME/.config/claude-code-mini/api_key"; export ANTHROPIC_API_KEY; fi'
        printf '%s\n' "$RC_END"
    } >>"$RC" || fail "Gagal menulis $RC"
    ok "$(tilde "$RC"): ~/.local/bin masuk PATH dan API key dimuat otomatis di terminal baru"
}

# Cetak kode HTTP GET /v1/models dengan key ini (200 = diterima), 0 kalau tidak tersambung.
# Key dikirim lewat stdin/env, bukan argumen command, supaya tidak terlihat di daftar proses.
check_key() {
    local code
    if command -v curl >/dev/null 2>&1; then
        code="$(printf 'x-api-key: %s\n' "$1" | curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
            -H @- -H 'anthropic-version: 2023-06-01' "$API_URL/v1/models" 2>/dev/null)" || code=0
    else
        code="$(CCM_KEY="$1" CCM_URL="$API_URL/v1/models" "$PY" -c '
import os, urllib.error, urllib.request
req = urllib.request.Request(os.environ["CCM_URL"], headers={"x-api-key": os.environ["CCM_KEY"], "anthropic-version": "2023-06-01"})
try:
    print(urllib.request.urlopen(req, timeout=20).status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception:
    print(0)' 2>/dev/null)" || code=0
    fi
    case "$code" in
        "" | 000) code=0 ;;
    esac
    printf '%s' "$code"
}

# Minta key sampai 3 kali; KEY kosong kalau dilewati.
prompt_key() {
    local k code tries=0
    KEY=""
    printf '\nAPI key dari %shttps://platform.claude.com/settings/keys%s (awalnya sk-ant-…).\n' "$C_B" "$C_0"
    while [ "$tries" -lt 3 ]; do
        tries=$((tries + 1))
        printf 'Tempel API key (tidak tampil di layar; Enter kosong = lewati): ' >/dev/tty
        IFS= read -rs k </dev/tty || k=""
        printf '\n' >/dev/tty
        k="$(printf '%s' "$k" | tr -d '[:space:][:cntrl:]')"
        [ -n "$k" ] || return 0
        if ! [[ $k =~ $KEY_RE ]]; then
            warn "Itu bukan API key Anthropic (harus diawali sk-ant-). Coba lagi."
            continue
        fi
        step "Mengecek key ke Anthropic …"
        code="$(check_key "$k")"
        case "$code" in
            200)
                ok "Key diterima Anthropic"
                KEY="$k"
                return 0
                ;;
            401 | 403) warn "Key ditolak Anthropic ($code): salah ketik, sudah dihapus, atau dari workspace lain. Coba lagi." ;;
            *)
                warn "Key belum bisa dicek (tidak tersambung ke $API_URL, kode $code). Key tetap disimpan."
                KEY="$k"
                return 0
                ;;
        esac
    done
    warn "Tiga kali gagal."
}

save_key() {
    if ! { mkdir -p "$CONF_DIR" && chmod 700 "$CONF_DIR"; }; then
        fail "Tidak bisa membuat folder $CONF_DIR"
    fi
    if ! { (umask 077 && printf '%s\n' "$1" >"$KEY_FILE.new") && mv -f "$KEY_FILE.new" "$KEY_FILE" &&
        chmod 600 "$KEY_FILE"; }; then
        fail "Gagal menyimpan API key ke $KEY_FILE"
    fi
    ok "API key disimpan di $(tilde "$KEY_FILE") (hanya bisa dibaca akunmu)"
}

key_in_startup_files() { # key yang ditulis manual (export ANTHROPIC_API_KEY=…) di file startup shell
    local f
    for f in "${ZDOTDIR:-$HOME}/.zshrc" "${ZDOTDIR:-$HOME}/.zshenv" "${ZDOTDIR:-$HOME}/.zprofile" "$HOME/.bashrc" \
        "$HOME/.bash_profile" "$HOME/.profile"; do
        [ -f "$f" ] && grep -q '^[[:space:]]*export[[:space:]][[:space:]]*ANTHROPIC_API_KEY=' "$f" && return 0
    done
    return 1
}

setup_key() {
    KEY_STATE=missing
    if [ -z "${CCMINI_NEW_KEY:-}" ]; then
        if [ -s "$KEY_FILE" ]; then
            ok "API key sudah tersimpan ($(tilde "$KEY_FILE"))"
            KEY_STATE=saved
            return 0
        fi
        if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
            KEY_STATE="env"
            if key_in_startup_files; then
                ok "ANTHROPIC_API_KEY sudah di-set di file startup shell"
                return 0
            fi
            ok "ANTHROPIC_API_KEY sudah di-set di terminal ini"
            if [ "$HAVE_TTY" = 1 ] && ask "Simpan juga supaya terminal baru langsung memakainya?"; then
                save_key "$ANTHROPIC_API_KEY"
            fi
            return 0
        fi
    fi
    if [ "$HAVE_TTY" != 1 ]; then
        warn "API key belum disimpan: jalankan installer ini lagi di terminal untuk memasukkannya."
        return 0
    fi
    prompt_key
    if [ -n "$KEY" ]; then
        save_key "$KEY"
        KEY_STATE=saved
    else
        warn "API key dilewati. Jalankan installer ini lagi kapan saja untuk memasukkannya."
    fi
}

finish() {
    local src_cmd=""
    [ -n "$RC" ] && src_cmd="source $(tilde "$RC")"
    printf '\n%s✓ claude-code-mini siap dipakai.%s\n' "$C_OK$C_B" "$C_0"
    if [ -n "$src_cmd" ]; then
        printf '  Buka terminal baru (atau jalankan  %s ), masuk ke folder proyekmu, lalu ketik:\n' "$src_cmd"
    else
        printf '  Buka terminal baru, masuk ke folder proyekmu, lalu ketik:\n'
    fi
    printf '    %sclaude-code-mini%s          (di terminal)\n' "$C_B" "$C_0"
    printf '    %sclaude-code-mini --gui%s    (di browser)\n' "$C_B" "$C_0"
    if [ "$KEY_STATE" = missing ]; then
        printf '  Belum ada API key: jalankan installer ini lagi untuk memasukkannya.\n'
    fi
    if ! command -v git >/dev/null 2>&1 || { [ "$OS" = macos ] && ! xcode-select -p >/dev/null 2>&1; }; then
        if [ "$OS" = macos ]; then
            printf '  Opsional: git belum ada. Pasang dengan  xcode-select --install\n'
        else
            printf '  Opsional: git belum ada. Pasang dengan  sudo apt install -y git\n'
        fi
    fi
    printf '  Update ke versi terbaru: jalankan perintah instalasi yang sama lagi.\n'
}

main() {
    set -u
    set -o pipefail
    if [ -t 1 ]; then
        C_OK=$'\033[32m' C_WARN=$'\033[33m' C_ERR=$'\033[31m' C_B=$'\033[1m' C_0=$'\033[0m'
    else
        C_OK="" C_WARN="" C_ERR="" C_B="" C_0=""
    fi
    HAVE_TTY=0
    if (exec </dev/tty) 2>/dev/null; then HAVE_TTY=1; fi
    case "$(uname -s)" in
        Darwin) OS=macos ;;
        Linux) OS=linux ;;
        *) fail "Installer ini untuk macOS dan Linux. Di Windows (PowerShell): irm https://raw.githubusercontent.com/imransetiadi/claude-code-mini/main/install.ps1 | iex" ;;
    esac
    REPO_SLUG="${CCMINI_REPO:-imransetiadi/claude-code-mini}"
    REF="${CCMINI_REF:-main}"
    DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/claude-code-mini"
    CONF_DIR="$HOME/.config/claude-code-mini"
    KEY_FILE="$CONF_DIR/api_key"
    API_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
    API_URL="${API_URL%/}"
    TMP="$(mktemp -d 2>/dev/null || mktemp -d -t ccmini)" || fail "Tidak bisa membuat folder sementara"
    trap 'rm -rf "$TMP"' EXIT

    printf '%s✻ claude-code-mini%s · installer (%s)\n' "$C_B" "$C_0" "$OS"
    ensure_python
    fetch_script
    run_setup
    detect_rc
    write_rc_block
    setup_key
    finish
}

main "$@"
