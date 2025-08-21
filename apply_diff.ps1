<# 
Skrypt: apply_diff.ps1
Cel: Nałożyć diff/patch skopiowany do schowka (clipboard) i od razu zrobić commit.

Użycie:
  ./apply_diff.ps1 "Opis commita"
  # lub z pliku diff:
  ./apply_diff.ps1 -FromFile .\zmiany.diff -Message "Opis"

Wymagania:
  - zainstalowany Git
  - uruchomienie w folderze repo (tam gdzie jest .git)
#>

param(
  [Parameter(Position=0)]
  [string]$Message = "Commit z diffem z clipboardu",

  [Parameter()]
  [string]$FromFile
)

# 1) Sprawdź, czy jest Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "❌ Nie znaleziono 'git' w PATH. Zainstaluj Git i spróbuj ponownie." -ForegroundColor Red
  exit 1
}

# 2) Sprawdź, czy jesteśmy w repo (czy istnieje .git)
$inRepo = (git rev-parse --is-inside-work-tree 2>$null)
if ($LASTEXITCODE -ne 0 -or $inRepo -ne "true") {
  Write-Host "❌ To nie wygląda na folder repozytorium Gita (brak .git)." -ForegroundColor Red
  exit 1
}

# 3) Pobierz diff: ze schowka albo z pliku (jeśli podano -FromFile)
$tempFile = New-TemporaryFile
try {
  if ($FromFile) {
    if (-not (Test-Path $FromFile)) {
      Write-Host "❌ Nie znaleziono pliku: $FromFile" -ForegroundColor Red
      exit 1
    }
    Get-Content -Raw -Path $FromFile | Set-Content -Path $tempFile -Encoding UTF8
  } else {
    $clip = Get-Clipboard -Raw
    if (-not $clip -or $clip.Trim().Length -eq 0) {
      Write-Host "❌ Schowek jest pusty. Skopiuj diff (blok zaczynający się od '---' lub 'diff --git')." -ForegroundColor Red
      exit 1
    }
    $clip | Set-Content -Path $tempFile -Encoding UTF8
  }
} catch {
  Write-Host "❌ Problem z odczytem diffu: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}

# 4) Szybka walidacja formatu (nie blokuje, tylko ostrzega)
$head = (Get-Content -Path $tempFile -TotalCount 5) -join "`n"
if ($head -notmatch '^(--- |\+\+\+ |diff --git)') {
  Write-Host "⚠️  Uwaga: plik nie wygląda jak standardowy diff/patch. Spróbuję nałożyć mimo to..." -ForegroundColor Yellow
}

# 5) Normalizacja: usuń BOM i CRLF -> LF
$raw = [System.IO.File]::ReadAllText($tempFile)
if ($raw.StartsWith([char]0xFEFF)) { $raw = $raw.Substring(1) }
$raw = $raw -replace "`r`n", "`n"
# Dedup: zostaw jeden blok 'diff --git' na plik (ostatni wygrywa)
$lines = $raw -split "`n"
$blocks = @()
$cur = @()
foreach ($ln in $lines) {
  if ($ln -match '^diff --git a/(.+?) b/\1$') {
    if ($cur.Count) { $blocks += ,(@($cur)) ; $cur = @() }
  }
  $cur += $ln
}
if ($cur.Count) { $blocks += ,(@($cur)) }

# grupuj po nazwie pliku i zostaw ostatni blok
$byFile = @{}
foreach ($b in $blocks) {
  $hdr = $b | Where-Object { $_ -match '^diff --git a/(.+?) b/\1$' } | Select-Object -First 1
  if ($hdr -match '^diff --git a/(.+?) b/\1$') {
    $file = $Matches[1]
    $byFile[$file] = $b
  }
}
$norm = ($byFile.GetEnumerator() | ForEach-Object { $_.Value }) -join "`n"
[IO.File]::WriteAllText($tempFile, $norm, (New-Object System.Text.UTF8Encoding($false)))

# 6) Dry-run
git -c core.autocrlf=false apply --check --ignore-space-change --whitespace=nowarn "$tempFile"
if ($LASTEXITCODE -ne 0) {
  Write-Host "⚠️  Try zwykły się nie udał, próbuję 3-way merge..." -ForegroundColor Yellow
  git -c core.autocrlf=false apply --3way --ignore-space-change --whitespace=nowarn "$tempFile"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Diff nie nakłada się czysto. Zobacz plik i popraw ręcznie:" -ForegroundColor Red
    Write-Host "   $tempFile"
    exit 1
  }
} else {
  # 7) Zastosuj patch
  git -c core.autocrlf=false apply --ignore-space-change --whitespace=nowarn "$tempFile"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Błąd podczas nakładania patcha." -ForegroundColor Red
    exit 1
  }
}

# ... (tu zostaje Twój blok z git add / commit i parsowaniem '# commit:')


# 8) Podsumowanie
Write-Host "✅ Diff nałożony i zacommitowany." -ForegroundColor Green
git log -1 --stat
