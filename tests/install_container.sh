#!/usr/bin/env bash
# Tes install.sh di container Ubuntu yang masih bersih (tanpa Python), dipanggil dari .github/workflows/tests.yml:
#   root: sebagai root -> installer memasang python3 + python3-venv + git lewat apt-get
#   user: user biasa tanpa sudo, dibuat dengan useradd (shell login /bin/sh) -> installer memasang Python lewat uv
# Sesudahnya perintah claude-code-mini yang terpasang dipakai dengan API palsu (tests/fakeapi.py), lewat dua shell
# baru: bash interaktif (seperti jendela terminal, membaca ~/.bashrc) dan shell login milik user itu (seperti sesi
# SSH, membaca ~/.profile). Keduanya harus menemukan perintahnya lewat blok yang ditambahkan installer.
#
#     docker run --rm -v "$PWD:/src:ro" ubuntu:26.04 bash /src/tests/install_container.sh user
set -euo pipefail
mode="${1:-root}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates >/dev/null # sudah ada kalau orang memakai `curl … | bash`
if command -v python3 >/dev/null 2>&1; then
    echo "image ini sudah punya python3, jadi tes ini tidak menguji pemasangan Python" >&2
    exit 1
fi

cat >/tmp/run.sh <<'EOF'
set -euo pipefail
cd "$HOME"
# installer dari checkout, tanpa terminal: tidak bertanya; key dari environment supaya tidak diminta
ANTHROPIC_API_KEY=sk-ant-fake-container-key bash /src/install.sh
"$HOME/.local/share/claude-code-mini/venv/bin/python" /src/tests/fakeapi.py 8899 /tmp/fakeapi.log >/dev/null 2>&1 &
for _ in $(seq 1 50); do (echo >/dev/tcp/127.0.0.1/8899) 2>/dev/null && break; sleep 0.1; done
mkdir -p "$HOME/proyek"
login_shell="$(getent passwd "$(id -un)" | cut -d: -f7)"
for sh in "bash -ic" "$login_shell -ilc"; do
    rc=0
    # shellcheck disable=SC2016,SC2086 # $HOME diperluas oleh shell baru; $sh sengaja dipecah jadi perintah + opsi
    out="$(ANTHROPIC_API_KEY=sk-ant-fake-container-key ANTHROPIC_BASE_URL=http://127.0.0.1:8899 \
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
        $sh 'cd "$HOME/proyek" && claude-code-mini --model haiku -p "[[say:halo dari container]]"' 2>&1)" || rc=$?
    printf '[%s] exit %s\n%s\n' "$sh" "$rc" "$(printf '%s\n' "$out" | tail -n 3)"
    if [ "$rc" != 0 ] || ! printf '%s\n' "$out" | grep -q "halo dari container"; then
        echo "GAGAL: claude-code-mini tidak jalan lewat $sh" >&2
        exit 1
    fi
done
echo "OK: shell login $login_shell dan bash interaktif menemukan claude-code-mini"
EOF

if [ "$mode" = root ]; then
    bash /tmp/run.sh
else
    useradd -m dev # tanpa -s: shell login /bin/sh, seperti user yang dibuat lewat useradd biasa
    su dev -c "bash /tmp/run.sh"
fi
