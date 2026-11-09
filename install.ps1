# claude-code-mini: installer sekali jalan untuk Windows 11 (PowerShell).
#
#     irm https://raw.githubusercontent.com/imransetiadi/claude-code-mini/main/install.ps1 | iex
#
# Yang dikerjakan:
#   1. Mencari Python 3.10+ (py / python). Kalau belum ada, memasangnya lewat winget (Python.Python.3.13).
#   2. Menawarkan Git for Windows lewat winget kalau belum ada: Claude Code menjalankan command lewat Git Bash.
#   3. Mengunduh claude-code-mini.py ke %USERPROFILE%\.local\share\claude-code-mini\ lalu menjalankan --setup:
#      virtualenv, library, dan perintah %USERPROFILE%\.local\bin\claude-code-mini.exe.
#   4. Menambahkan %USERPROFILE%\.local\bin ke PATH user.
#   5. Meminta API key (tidak tampil di layar), mengeceknya ke Anthropic (GET /v1/models, gratis), lalu
#      menyimpannya sebagai environment variable user ANTHROPIC_API_KEY.
# Lewat `irm ... | iex`, claude-code-mini langsung bisa dipakai di jendela yang sama. Menjalankan installer ini lagi
# = update ke versi terbaru; API key yang sudah tersimpan tidak ditanya lagi.
#
# Variabel opsional: $env:CCMINI_NEW_KEY = "1" (minta API key baru), $env:CCMINI_PYTHON (python.exe yang dipakai),
# $env:CCMINI_REF (branch/tag/commit, bawaan main), $env:CCMINI_REPO (bawaan imransetiadi/claude-code-mini),
# $env:CCMINI_SOURCE (file claude-code-mini.py lokal; dipakai otomatis kalau installer dijalankan dari clone repo).
# Tanpa konsol (input dialihkan, mis. CI) installer tidak bertanya: Python dipasang kalau perlu, Git dan API key
# dilewati.
#
# Catatan: file ini sengaja hanya berisi karakter ASCII (Windows PowerShell 5.1 membaca .ps1 tanpa BOM sebagai
# ANSI) dan tidak memakai `exit` (lewat iex, exit akan menutup jendela PowerShell pengguna).

& {
    $ProgressPreference = 'SilentlyContinue'  # progress bar membuat Invoke-WebRequest di PowerShell 5.1 sangat lambat
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    } catch { }

    $Repo = if ($env:CCMINI_REPO) { $env:CCMINI_REPO } else { 'imransetiadi/claude-code-mini' }
    $Ref = if ($env:CCMINI_REF) { $env:CCMINI_REF } else { 'main' }
    $UserHome = $env:USERPROFILE
    $DataDir = if ($env:XDG_DATA_HOME) { Join-Path $env:XDG_DATA_HOME 'claude-code-mini' } else { Join-Path $UserHome '.local\share\claude-code-mini' }
    $BinDir = Join-Path $UserHome '.local\bin'
    $Script = Join-Path $DataDir 'claude-code-mini.py'
    $Api = if ($env:ANTHROPIC_BASE_URL) { $env:ANTHROPIC_BASE_URL.TrimEnd('/') } else { 'https://api.anthropic.com' }
    $InstallCmd = 'irm https://raw.githubusercontent.com/imransetiadi/claude-code-mini/main/install.ps1 | iex'
    $FromFile = [bool]$PSCommandPath
    $Interactive = -not [Console]::IsInputRedirected
    $KeyRe = '^sk-ant-[A-Za-z0-9_-]{10,}$'
    $Tick = [string][char]0x2713
    $Arrow = [string][char]0x2192
    $Cross = [string][char]0x2717
    $Dots = [string][char]0x2026

    function Say-Step($t) { Write-Host "$Arrow $t" }
    function Say-Ok($t) { Write-Host $Tick -ForegroundColor Green -NoNewline; Write-Host " $t" }
    function Say-Warn($t) { Write-Host '!' -ForegroundColor Yellow -NoNewline; Write-Host " $t" }
    function Stop-Install($t) {
        Write-Host $Cross -ForegroundColor Red -NoNewline; Write-Host " $t"
        throw 'ccmini-stop'
    }

    function Ask($q) {
        if (-not $Interactive) { return $true }
        $a = Read-Host "$q [Y/n]"
        return ($a -eq '' -or $a -match '^(y|ya|yes)$')
    }

    # Tambahkan folder PATH dari registry (Machine + User) yang belum ada di sesi ini, mis. setelah winget memasang.
    function Update-SessionPath {
        $have = @($env:Path -split ';' | Where-Object { $_ } | ForEach-Object { $_.TrimEnd('\') })
        foreach ($scope in 'Machine', 'User') {
            foreach ($p in ([string][Environment]::GetEnvironmentVariable('Path', $scope) -split ';')) {
                if ($p -and ($have -notcontains $p.TrimEnd('\'))) {
                    $env:Path = "$env:Path;$p"
                    $have += $p.TrimEnd('\')
                }
            }
        }
    }

    # python.exe (path lengkap) dengan Python >= 3.10 yang bisa membuat virtualenv, atau $null.
    function Find-Python {
        $cands = New-Object System.Collections.ArrayList
        if ($env:CCMINI_PYTHON) { [void]$cands.Add(@($env:CCMINI_PYTHON)) }
        if (Get-Command py -CommandType Application -ErrorAction SilentlyContinue) { [void]$cands.Add(@('py', '-3')) }
        foreach ($n in 'python', 'python3') {
            foreach ($c in @(Get-Command $n -All -CommandType Application -ErrorAction SilentlyContinue)) {
                # ...\WindowsApps\python.exe = alias Microsoft Store: membuka Store, bukan Python
                if ($c.Source -notlike '*\WindowsApps\*') { [void]$cands.Add(@($c.Source)) }
            }
        }
        foreach ($pat in "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe") {
            foreach ($f in @(Get-ChildItem $pat -ErrorAction SilentlyContinue)) { [void]$cands.Add(@($f.FullName)) }
        }
        foreach ($c in $cands) {
            $exe = $c[0]
            $pre = @($c | Select-Object -Skip 1)
            # tanpa tanda kutip ganda: Windows PowerShell 5.1 membuangnya dari argumen untuk program lain
            $out = & $exe @pre -c 'import sys, venv, ensurepip; print(sys.executable if sys.version_info >= (3, 10) else '''')' 2>$null
            if ($LASTEXITCODE -eq 0 -and $out -and (Test-Path ([string]$out).Trim())) { return ([string]$out).Trim() }
        }
        return $null
    }

    function Install-Winget($id) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Say-Warn 'winget tidak ditemukan (pasang "App Installer" dari Microsoft Store).'
            return $false
        }
        Say-Step "winget install -e --id $id $Dots"
        $wargs = @('install', '-e', '--id', $id, '--source', 'winget')
        if (-not $Interactive) { $wargs += '--disable-interactivity' }
        & winget @wargs
        $done = ($LASTEXITCODE -eq 0)
        Update-SessionPath
        return $done
    }

    function Find-GitBash {
        $c = @()
        if ($env:CLAUDE_CODE_GIT_BASH_PATH) { $c += $env:CLAUDE_CODE_GIT_BASH_PATH }
        $c += "$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
        $git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($git) { $c += Join-Path (Split-Path (Split-Path $git.Source)) 'bin\bash.exe' }
        foreach ($p in $c) { if ($p -and (Test-Path $p)) { return $p } }
        return $null
    }

    # Tambah folder ke PATH user lewat registry, dengan jenis REG_EXPAND_SZ supaya entri seperti
    # %USERPROFILE%\AppData\Local\Microsoft\WindowsApps tetap utuh.
    function Add-UserPath($dir) {
        $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
        try {
            $raw = [string]$key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
            $parts = @($raw -split ';' | Where-Object { $_ })
            foreach ($p in $parts) {
                if ([Environment]::ExpandEnvironmentVariables($p).TrimEnd('\') -eq $dir.TrimEnd('\')) { return $false }
            }
            $key.SetValue('Path', ((@($parts) + $dir) -join ';'), [Microsoft.Win32.RegistryValueKind]::ExpandString)
        } finally {
            $key.Close()
        }
        # SetEnvironmentVariable mengumumkan perubahan (WM_SETTINGCHANGE), jadi jendela baru membaca PATH yang baru
        [Environment]::SetEnvironmentVariable('CCMINI_INSTALLER_REFRESH', $null, 'User')
        return $true
    }

    # Kode HTTP GET /v1/models dengan key ini (200 = diterima), 0 kalau tidak tersambung.
    function Test-Key($k) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri "$Api/v1/models" -TimeoutSec 20 -ErrorAction Stop `
                -Headers @{ 'x-api-key' = $k; 'anthropic-version' = '2023-06-01' }
            return [int]$r.StatusCode
        } catch {
            $resp = $_.Exception.Response
            if ($resp) { try { return [int]$resp.StatusCode } catch { return 0 } }
            return 0
        }
    }

    function Read-Key {
        Write-Host ''
        Write-Host "API key dari https://platform.claude.com/settings/keys (awalnya sk-ant-$Dots)."
        for ($i = 1; $i -le 3; $i++) {
            $s = Read-Host 'Tempel API key (tidak tampil di layar; Enter kosong = lewati)' -AsSecureString
            $k = ([Net.NetworkCredential]::new('', $s).Password -replace '\s', '')
            if (-not $k) { return $null }
            if ($k -cnotmatch $KeyRe) { Say-Warn 'Itu bukan API key Anthropic (harus diawali sk-ant-). Coba lagi.'; continue }
            Say-Step "Mengecek key ke Anthropic $Dots"
            $code = Test-Key $k
            if ($code -eq 200) { Say-Ok 'Key diterima Anthropic'; return $k }
            if ($code -eq 401 -or $code -eq 403) {
                Say-Warn "Key ditolak Anthropic ($code): salah ketik, sudah dihapus, atau dari workspace lain. Coba lagi."
                continue
            }
            Say-Warn "Key belum bisa dicek (tidak tersambung ke $Api, kode $code). Key tetap disimpan."
            return $k
        }
        Say-Warn 'Tiga kali gagal.'
        return $null
    }

    function Save-Key($k) {
        [Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', $k, 'User')
        $env:ANTHROPIC_API_KEY = $k
        Say-Ok 'API key disimpan (environment variable user ANTHROPIC_API_KEY)'
    }

    try {
        Write-Host "$([char]0x273B) claude-code-mini $([char]0x00B7) installer (Windows)"

        # 1. Python
        $py = Find-Python
        if (-not $py) {
            Say-Warn 'Python 3.10 atau yang lebih baru belum ada.'
            if (Ask 'Pasang Python 3.13 lewat winget?') {
                [void](Install-Winget 'Python.Python.3.13')
                $py = Find-Python
            }
            if (-not $py) {
                Stop-Install 'Butuh Python 3.10+. Pasang dari https://www.python.org/downloads/windows/ lalu jalankan installer ini lagi di jendela PowerShell baru.'
            }
        }
        $ver = (& $py -c 'import platform; print(platform.python_version())' 2>$null)
        Say-Ok "Python $ver ($py)"

        # 2. Git for Windows (Git Bash)
        $bash = Find-GitBash
        if ($bash) {
            Say-Ok "Git Bash: $bash"
        } elseif ($Interactive -and (Ask 'Git for Windows belum ada (Claude Code paling lancar lewat Git Bash). Pasang lewat winget?')) {
            [void](Install-Winget 'Git.Git')
            $bash = Find-GitBash
            if ($bash) { Say-Ok "Git Bash: $bash" } else { Say-Warn 'Git belum terpasang: Claude akan menjalankan command lewat PowerShell.' }
        } else {
            Say-Warn 'Git for Windows belum ada: Claude akan menjalankan command lewat PowerShell (bisa dipasang nanti: winget install -e --id Git.Git).'
        }

        # 3. claude-code-mini.py
        New-Item -ItemType Directory -Force -Path $DataDir -ErrorAction Stop | Out-Null
        $new = Join-Path $DataDir '.claude-code-mini.py.new'
        $src = $env:CCMINI_SOURCE
        if (-not $src -and $PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'claude-code-mini.py'))) {
            $src = Join-Path $PSScriptRoot 'claude-code-mini.py'
        }
        if ($src) {
            Say-Step "Memakai $src"
            Copy-Item -LiteralPath $src -Destination $new -Force -ErrorAction Stop
        } else {
            $url = "https://raw.githubusercontent.com/$Repo/$Ref/claude-code-mini.py"
            Say-Step "Mengunduh claude-code-mini.py ($Ref) $Dots"
            try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $new -ErrorAction Stop }
            catch { Stop-Install "Gagal mengunduh ${url}: $($_.Exception.Message)" }
        }
        # unduhan yang terpotong atau halaman error tidak boleh menggantikan versi yang sudah terpasang
        & $py -c 'import ast, sys; ast.parse(open(sys.argv[1], encoding=''utf-8'').read())' $new 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath $new -Pattern 'def bootstrap' -SimpleMatch -Quiet)) {
            Remove-Item -LiteralPath $new -Force -ErrorAction SilentlyContinue
            Stop-Install 'File claude-code-mini.py yang didapat tidak utuh. Coba jalankan installer ini lagi.'
        }
        Move-Item -LiteralPath $new -Destination $Script -Force -ErrorAction Stop

        # 4. --setup (library terkunci kalau claude-code-mini masih jalan di jendela lain)
        #    (proses dari folder instalasi: launcher, python.exe venv, mesin claude.exe, atau yang menjalankan script-nya)
        $launcher = Join-Path $BinDir 'claude-code-mini.exe'
        $running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                $_.ProcessId -ne $PID -and (($_.ExecutablePath -and ($_.ExecutablePath -eq $launcher -or
                            $_.ExecutablePath.StartsWith($DataDir, [StringComparison]::OrdinalIgnoreCase))) -or
                    ($_.CommandLine -and $_.CommandLine.IndexOf($DataDir, [StringComparison]::OrdinalIgnoreCase) -ge 0))
            })
        if ($running.Count -gt 0) {
            Say-Warn "claude-code-mini masih jalan ($($running.Count) proses). Tutup dulu jendelanya: Windows tidak bisa memperbarui library yang sedang dipakai."
            if ($Interactive -and -not (Ask 'Sudah ditutup, lanjutkan?')) { Stop-Install 'Dibatalkan.' }
        }
        Say-Step "Menjalankan claude-code-mini --setup $Dots"
        $env:CCMINI_INSTALLER = '1'
        try {
            & $py $Script --setup
            $code = $LASTEXITCODE
        } finally {
            Remove-Item Env:CCMINI_INSTALLER -ErrorAction SilentlyContinue
        }
        if ($code -ne 0) { Stop-Install '--setup gagal (lihat pesan di atas). Perbaiki penyebabnya lalu jalankan installer ini lagi.' }

        # 5. PATH
        if (Add-UserPath $BinDir) { Say-Ok "$BinDir ditambahkan ke PATH user" } else { Say-Ok "$BinDir sudah ada di PATH user" }
        if (-not (@($env:Path -split ';') | Where-Object { $_.TrimEnd('\') -eq $BinDir.TrimEnd('\') })) { $env:Path = "$env:Path;$BinDir" }

        # 6. API key
        $keyState = 'missing'
        $userKey = [Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY', 'User')
        if ($userKey -and -not $env:CCMINI_NEW_KEY) {
            Say-Ok 'API key sudah tersimpan (environment variable user ANTHROPIC_API_KEY)'
            if (-not $env:ANTHROPIC_API_KEY) { $env:ANTHROPIC_API_KEY = $userKey }
            $keyState = 'saved'
        } elseif ($env:ANTHROPIC_API_KEY -and -not $env:CCMINI_NEW_KEY) {
            Say-Ok 'ANTHROPIC_API_KEY sudah di-set di jendela ini'
            $keyState = 'env'
            if ($Interactive -and (Ask 'Simpan juga supaya jendela baru langsung memakainya?')) { Save-Key $env:ANTHROPIC_API_KEY }
        } elseif (-not $Interactive) {
            Say-Warn 'API key belum disimpan: jalankan installer ini lagi di jendela PowerShell untuk memasukkannya.'
        } else {
            $k = Read-Key
            if ($k) { Save-Key $k; $keyState = 'saved' }
            else { Say-Warn 'API key dilewati. Jalankan installer ini lagi kapan saja untuk memasukkannya.' }
        }

        Write-Host ''
        Write-Host "$Tick claude-code-mini siap dipakai." -ForegroundColor Green
        if ($FromFile) { Write-Host '  Buka jendela PowerShell baru, masuk ke folder proyekmu, lalu ketik:' }
        else { Write-Host '  Di jendela ini (atau jendela baru), masuk ke folder proyekmu, lalu ketik:' }
        Write-Host '    claude-code-mini           (di terminal)'
        Write-Host '    claude-code-mini --gui     (di browser)'
        if ($keyState -eq 'missing') { Write-Host '  Belum ada API key: jalankan installer ini lagi untuk memasukkannya.' }
        Write-Host "  Update ke versi terbaru: jalankan lagi  $InstallCmd"
    } catch {
        if ("$_" -ne 'ccmini-stop') {
            Write-Host "$Cross Installer berhenti: $_" -ForegroundColor Red
        }
        if ($FromFile) { exit 1 }  # dijalankan sebagai file (-File): exit code untuk skrip/CI. Lewat iex: jangan exit.
    }
}
