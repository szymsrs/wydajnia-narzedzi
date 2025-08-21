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

# 5) Sprawdź, czy patch się nałoży (dry-run)
git apply --check --whitespace=warn "$tempFile"
if ($LASTEXITCODE -ne 0) {
  Write-Host "❌ Diff nie nakłada się czysto. Zobacz plik tymczasowy (poniżej) i popraw ręcznie:" -ForegroundColor Red
  Write-Host "   $tempFile"
  exit 1
}

# 6) Zastosuj patch (z automatyczną korektą białych znaków)
git apply --whitespace=fix "$tempFile"
if ($LASTEXITCODE -ne 0) {
  Write-Host "❌ Błąd podczas nakładania patcha." -ForegroundColor Red
  exit 1
}

# 7) Dodaj zmiany i zrób commit
git add -A
# Spróbuj znaleźć linijkę "# commit: ..."
$commitLine = (Select-String -Path $tempFile -Pattern "^# commit:" | Select-Object -First 1)

if ($commitLine) {
    $commitMsg = $commitLine.ToString().Substring(9).Trim()  # wytnij "# commit:" i spacje
} else {
    $commitMsg = $Message  # fallback, jeśli nie było komentarza
}

git commit -m "$commitMsg"
if ($LASTEXITCODE -ne 0) {
  Write-Host "❌ Commit nie powiódł się. Cofam nałożony patch (git reset --hard)." -ForegroundColor Red
  git reset --hard
  exit 1
}

# 8) Podsumowanie
Write-Host "✅ Diff nałożony i zacommitowany." -ForegroundColor Green
git log -1 --stat
