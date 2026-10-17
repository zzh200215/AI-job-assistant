# Agent floors are set to beat the model-free baseline that scripts/eval_agent.py now prints.
# On the current 25-pair set: best constant + deterministic cap = MAE 16.44, hit_tol10 11 (44%),
# rho 0.554; the 95th percentile of a random ranking is 0.349. The floors below clear all three.
# They are a bar to clear, not a claim about the current model - if a real-provider run goes red,
# that is information, not a broken gate. hit_tol10 is a count, so it scales with the fixture.
param(
    [switch]$ImportSeeds,
    [switch]$AllowReal,
    [double]$MinRagRecall = 0.85,
    [double]$MinRagMrr = 0.85,
    [double]$MinRagKeywordHit = 0.75,
    [double]$MaxAgentMae = 8.0,
    [double]$MinAgentSpearman = 0.85,
    [int]$MinAgentHitTol10 = 17
)

$ErrorActionPreference = "Stop"

# eval_rag.py / eval_agent.py each call scripts/provider_guard.py::require_mock first: a non-mock
# provider without an explicit --allow-real exits with code 2. backend/.env pins the real provider,
# so this script has produced no report since that gate landed (d84291c, 2026-10-06).
# Note the failure is NOT a stop at the first command: $ErrorActionPreference="Stop" does not catch
# a native command's non-zero exit code (measured on PowerShell 5.1), so both evals get rejected,
# the script keeps going, and it dies in Copy-Item below (the timestamped file never exists, so
# ItemNotFoundException). Symptom on screen: "path not found", not "blocked by the provider gate".
# Default = pin mock, which is exactly CI's job env (ci.yml:23-24) and costs nothing. A real run has
# to be named with -AllowReal.
# Keep this file ASCII-only: PowerShell 5.1 reads a BOM-less .ps1 with the ANSI codepage (cp936
# here), and a multi-byte character at the end of a line swallows the following newline, silently
# merging statements into the comment above them.
$allowRealArgs = @()
if ($AllowReal) {
    Write-Warning "-AllowReal: calls the real provider (costs money); the fused arm also drifts run-to-run, so do not use these numbers as a before/after control."
    $allowRealArgs = @("--allow-real")
} else {
    $env:LLM_PROVIDER = "mock"
    $env:EMBEDDING_PROVIDER = "mock"
    Write-Host "provider pinned to mock (zero cost, CI parity). Add -AllowReal for a real run."
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"
$reportsDir = Join-Path $backendRoot "reports"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ragTimestamped = Join-Path $reportsDir ("rag_eval_{0}.json" -f $timestamp)
$agentTimestamped = Join-Path $reportsDir ("agent_eval_{0}.json" -f $timestamp)
$ragLatest = Join-Path $reportsDir "rag_eval.json"
$agentLatest = Join-Path $reportsDir "agent_eval.json"

if (-not (Test-Path -LiteralPath $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir | Out-Null
}

Push-Location $backendRoot
try {
    if ($ImportSeeds) {
        python scripts\import_knowledge_seeds.py
    }

    python scripts\eval_rag.py `
        --top-k 5 `
        --output $ragTimestamped `
        --min-recall $MinRagRecall `
        --min-mrr $MinRagMrr `
        --min-keyword-hit $MinRagKeywordHit `
        @allowRealArgs

    python scripts\eval_agent.py `
        --output $agentTimestamped `
        --max-mae $MaxAgentMae `
        --min-spearman $MinAgentSpearman `
        --min-hit-tol10 $MinAgentHitTol10 `
        @allowRealArgs

    Copy-Item -LiteralPath $ragTimestamped -Destination $ragLatest -Force
    Copy-Item -LiteralPath $agentTimestamped -Destination $agentLatest -Force
}
finally {
    Pop-Location
}
