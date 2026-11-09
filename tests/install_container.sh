#!/usr/bin/env bash
# Tes install.sh di container Ubuntu yang masih bersih (tanpa Python), dipanggil dari .github/workflows/tests.yml:
#   root: sebagai root -> installer memasang python3 + python3-venv + git lewat apt-get
#   user: sebagai user biasa tanpa sudo -> installer memasang Python lewat uv (tanpa sudo)
# Sesudahnya perintah claude-code-mini yang terpasang dipakai dengan API palsu (tests/fakeapi.py), lewat shell
# interaktif baru yang memuat ~/.bashrc hasil installer.
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
rc=0
out="$(ANTHROPIC_API_KEY=sk-ant-fake-container-key ANTHROPIC_BASE_URL=http://127.0.0.1:8899 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 bash -ic 'cd "$HOME/proyek" && claude-code-mini --model haiku -p "[[say:halo dari container]]"' 2>&1)" || rc=$?
printf '%s\n' "$out" | tail -n 4
[ "$rc" = 0 ] && printf '%s\n' "$out" | grep -q "halo dari container"
echo "OK: claude-code-mini dari PATH ($(bash -ic 'command -v claude-code-mini' 2>/dev/null))"
EOF

if [ "$mode" = root ]; then
    bash /tmp/run.sh
else
    useradd -m dev
    su dev -c "bash /tmp/run.sh"
fi
