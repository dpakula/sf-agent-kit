# SF Agent Kit — instalacja jednym poleceniem na Windows, bez WSL (ADVERTPR-987).
#
#   irm https://raw.githubusercontent.com/dpakula/sf-agent-kit/main/install.ps1 | iex
#
# v0.1 (29.09.2026) - APro Agents / borys-sf
#
# Działa w PowerShell (także w terminalu aplikacji Claude Code na Windows). Git NIE jest
# potrzebny, uprawnienia administratora NIE są potrzebne. Robi tylko to, czego Python nie
# zrobi, zanim go znajdziemy: szuka Pythona 3.9+, pobiera ZIP wydania i rozpakowuje go.
# Resztę (katalog %LOCALAPPDATA%\sf-kit, polecenie sf-kit, PATH) robi `sf-kit instaluj`.
#
# Wszystko w bloku skryptowym: przez `iex` błąd nie może zamknąć okna człowiekowi (`exit`
# zamknąłby CAŁĄ sesję PowerShell), więc wychodzimy przez `return`.
& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'      # pasek postępu Invoke-WebRequest spowalnia pobieranie kilkukrotnie
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $ref = if ($env:SF_KIT_REF) { $env:SF_KIT_REF } else { 'v0.17.0' }
    $adres = "https://codeload.github.com/dpakula/sf-agent-kit/zip/$ref"

    # Python: najpierw `py -3` (instalator z python.org), potem `python`/`python3`.
    # `python` z katalogu WindowsApps to ATRAPA Sklepu Microsoft — otwiera Sklep zamiast
    # uruchomić Pythona, więc ją pomijamy.
    $py = $null
    $sprawdz = 'import sys; print(sys.executable) if sys.version_info >= (3, 9) else sys.exit(1)'
    foreach ($nazwa in @('py', 'python', 'python3')) {
        $cmd = Get-Command $nazwa -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $cmd) { continue }
        if ($cmd.Source -like '*\WindowsApps\*') { continue }
        $argumenty = @()
        if ($nazwa -eq 'py') { $argumenty = @('-3') }
        try {
            $wynik = & $cmd.Source @argumenty -c $sprawdz 2>$null
            if ($LASTEXITCODE -eq 0 -and $wynik) { $py = ($wynik | Select-Object -Last 1).Trim(); break }
        } catch {}
    }
    if (-not $py) {
        Write-Host ''
        Write-Host 'Kit potrzebuje Pythona 3.9 lub nowszego, a nie znalazłem go na tym komputerze.' -ForegroundColor Yellow
        Write-Host 'Zainstaluj go jednym z dwóch sposobów:'
        Write-Host '  1) wklej tutaj:  winget install -e --id Python.Python.3.12'
        Write-Host '  2) albo pobierz ze strony https://www.python.org/downloads/ i przy instalacji'
        Write-Host '     zaznacz „Add python.exe to PATH”.'
        Write-Host 'Potem ZAMKNIJ to okno, otwórz nowe PowerShell i wklej polecenie instalacji Kita jeszcze raz.'
        return
    }

    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("sf-kit-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Write-Host "Pobieram SF Agent Kit $ref…"
        $zip = Join-Path $tmp 'kit.zip'
        try {
            Invoke-WebRequest -Uri $adres -OutFile $zip -UseBasicParsing
        } catch {
            Write-Host "Nie udało się pobrać Kita ($adres). Sprawdź połączenie z internetem." -ForegroundColor Red
            return
        }

        # Rozpakowanie Pythonem (zipfile): ta sama ochrona ścieżek co na macOS/Linuksie,
        # a komentarz archiwum = SHA commita do znacznika instalacji.
        $rozpakuj = @'
import sys, zipfile
from pathlib import Path
arch, cel = sys.argv[1], Path(sys.argv[2]).resolve()
with zipfile.ZipFile(arch) as z:
    for n in z.namelist():
        d = (cel / n).resolve()
        if d != cel and cel not in d.parents:
            sys.exit("archiwum zawiera ścieżkę spoza katalogu: " + n)
    z.extractall(cel)
    print(z.comment.decode("ascii", "replace").strip())
'@
        $plikRozpakuj = Join-Path $tmp 'rozpakuj.py'
        Set-Content -Path $plikRozpakuj -Value $rozpakuj -Encoding UTF8
        $src = Join-Path $tmp 'src'
        $commit = & $py $plikRozpakuj $zip $src
        if ($LASTEXITCODE -ne 0) { Write-Host 'Nie udało się rozpakować Kita.' -ForegroundColor Red; return }
        $katalog = Get-ChildItem -Path $src -Directory | Select-Object -First 1
        $skrypt = Join-Path $katalog.FullName 'sf-kit'
        if (-not (Test-Path $skrypt)) { Write-Host 'Pobrane archiwum nie wygląda na Kita.' -ForegroundColor Red; return }

        $env:PYTHONUTF8 = '1'
        & $py $skrypt instaluj --ref $ref --commit "$commit"
        if ($LASTEXITCODE -ne 0) { return }

        # PATH w rejestrze zobaczą NOWE okna; to okno dostaje go od razu tutaj.
        $bin = Join-Path $env:LOCALAPPDATA 'sf-kit\bin'
        if (($env:Path -split ';') -notcontains $bin) { $env:Path = "$env:Path;$bin" }
        Write-Host ''
        Write-Host 'Gotowe. W tym oknie możesz od razu wpisać:  sf-kit init' -ForegroundColor Green
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}
