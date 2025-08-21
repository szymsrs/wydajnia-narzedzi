<#
Skrypt: apply_diff.ps1
Cel: Nalozyc diff/patch skopiowany do schowka (clipboard) i od razu zrobic commit.

Uzycie:
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

# 1) Sprawdz czy jest Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "BLAD: Nie znaleziono 'git' w PATH." -ForegroundColor Red
  exit 1
}

# 2) Sprawdz czy jestesmy w repo
$inRepo = (git rev-parse --is-inside-work-tree 2>$null)
if ($LASTEXITCODE -ne 0 -or $inRepo -ne "true") {
  Write-Host "BLAD: To nie wyglada na folder repozytorium (brak .git)." -ForegroundColor Red
  exit 1
}

# 3) Pobierz diff: ze schowka albo z pliku
$tempFile = New-TemporaryFile
try {
  if ($FromFile) {
    if (-not (Test-Path $FromFile)) {
      Write-Host "BLAD: Nie znaleziono pliku: $FromFile" -ForegroundColor Red
      exit 1
    }
    Get-Content -Raw -Path $FromFile | Set-Content -Path $tempFile -Encoding UTF8
  } else {
    $clip = Get-Clipboard -Raw
    if (-not $clip -or $clip.Trim().Length -eq 0) {
      Write-Host "BLAD: Schowek jest pusty. Skopiuj diff (blok zaczynajacy sie od '---' lub 'diff --git')." -ForegroundColor Red
      exit 1
    }
    $clip | Set-Content -Path $tempFile -Encoding UTF8
  }
} catch {
  Write-Host "BLAD: Problem z odczytem diffu: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}

# 4) Walidacja formatu (ostrzezenie)
$head = (Get-Content -Path $tempFile -TotalCount 5) -join "`n"
if ($head -notmatch '^(--- |\+\+\+ |diff --git)') {
  Write-Host "UWAGA: Plik nie wyglada jak standardowy diff/patch. Sprobuje mimo to..." -ForegroundColor Yellow
}

# 5) Normalizacja: usun BOM i CRLF -> LF, dedup blokow; zachowaj naglowek (np. # commit:)
$raw = [System.IO.File]::ReadAllText($tempFile)
if ($raw.StartsWith([char]0xFEFF)) { $raw = $raw.Substring(1) }
$raw = $raw -replace "`r`n", "`n"

$lines = $raw -split "`n"

# Zbierz linie poprzedzajace pierwszy "diff --git" (np. # commit:, # body:)
$preface = @()
$startIdx = ($lines | Select-String -Pattern '^[ ]*diff --git a/.+ b/.+' | Select-Object -First 1).LineNumber
if ($startIdx) {
  $preface = $lines[0..($startIdx-2)]
} else {
  $preface = $lines
}

# Podziel na bloki diff
$blocks = @()
$cur = @()
foreach ($ln in $lines) {
  if ($ln -match '^[ ]*diff --git a/(.+) b/(.+)$') {
    if ($cur.Count) { $blocks += ,(@($cur)) ; $cur = @() }
  }
  $cur += $ln
}
if ($cur.Count) { $blocks += ,(@($cur)) }

# Zbuduj mapa blokow po kluczu pliku docelowego:
# - jesli bPath != /dev/null -> klucz = bPath (nowy/zmieniony/rename)
# - w przeciwnym razie klucz = aPath (usuwany plik)
$byKey = [ordered]@{}
foreach ($b in $blocks) {
  $hdr = $b | Where-Object { $_ -match '^[ ]*diff --git a/(.+) b/(.+)$' } | Select-Object -First 1
  if ($hdr) {
    $null = $hdr -match '^[ ]*diff --git a/(.+) b/(.+)$'
    $aPath = $Matches[1]
    $bPath = $Matches[2]
    $key = if ($bPath -ne "/dev/null") { $bPath } else { $aPath }
    # ostatni blok o tym samym kluczu wygrywa
    $byKey[$key] = $b
  }
}

# Sklej z powrotem: preface (bez pustych koncow) + wszystkie unikalne bloki
$prefaceText = ($preface -join "`n").Trim()
$normBlocks = ($byKey.GetEnumerator() | ForEach-Object { $_.Value }) -join "`n"
$final = if ($prefaceText) { "$prefaceText`n$normBlocks" } else { $normBlocks }

[IO.File]::WriteAllText($tempFile, $final, (New-Object System.Text.UTF8Encoding($false)))


# 6) Dry-run
git -c core.autocrlf=false apply --check --ignore-space-change --whitespace=nowarn "$tempFile"
if ($LASTEXITCODE -ne 0) {
  Write-Host "UWAGA: Zwykle nakladanie diffu nie powiodlo sie, sprobuje 3-way merge..." -ForegroundColor Yellow
  git -c core.autocrlf=false apply --3way --ignore-space-change --whitespace=nowarn "$tempFile"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "BLAD: Diff nie naklada sie czysto. Sprawdz plik tymczasowy:" -ForegroundColor Red
    Write-Host "   $tempFile"
    exit 1
  }
} else {
  # 7) Zastosuj patch
  git -c core.autocrlf=false apply --ignore-space-change --whitespace=nowarn "$tempFile"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "BLAD: Problem podczas nakladania diffu." -ForegroundColor Red
    exit 1
  }
}

# 7b) Dodaj i zrob commit
git add -A
$commitLine = (Select-String -Path $tempFile -Pattern "^# commit:" | Select-Object -First 1)
if ($commitLine) {
    $commitMsg = $commitLine.ToString().Substring(9).Trim()
} else {
    $commitMsg = $Message
}
git commit -m "$commitMsg"
if ($LASTEXITCODE -ne 0) {
  Write-Host "BLAD: Commit nie powiodl sie. Resetuje zmiany." -ForegroundColor Red
  git reset --hard
  exit 1
}

# 8) Podsumowanie
Write-Host "OK: Diff zostal nalozony i zacommitowany." -ForegroundColor Green
git log -1 --stat
