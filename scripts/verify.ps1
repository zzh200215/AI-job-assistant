param(
    [string]$Python = "python",
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonUtf8 = $env:PYTHONUTF8
$env:PYTHONUTF8 = "1"

try {
    Push-Location (Join-Path $repoRoot "backend")
    try {
        & $Python -m pytest

        $migrationDb = Join-Path $env:TEMP "recruit_platform_migration_check.sqlite3"
        if (Test-Path -LiteralPath $migrationDb) {
            Remove-Item -LiteralPath $migrationDb -Force
        }

        $previousDatabaseUrl = $env:DATABASE_URL
        $env:DATABASE_URL = "sqlite:///$($migrationDb -replace '\\', '/')"
        try {
            & $Python -m alembic -c alembic.ini upgrade head
            & $Python -m alembic -c alembic.ini current
        }
        finally {
            if ($null -eq $previousDatabaseUrl) {
                Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
            }
            else {
                $env:DATABASE_URL = $previousDatabaseUrl
            }
            if (Test-Path -LiteralPath $migrationDb) {
                Remove-Item -LiteralPath $migrationDb -Force
            }
        }
    }
    finally {
        Pop-Location
    }

    if (-not $SkipFrontend) {
        Push-Location (Join-Path $repoRoot "frontend")
        try {
            npm run test
            npm run build
        }
        finally {
            Pop-Location
        }
    }
}
finally {
    if ($null -eq $previousPythonUtf8) {
        Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONUTF8 = $previousPythonUtf8
    }
}
