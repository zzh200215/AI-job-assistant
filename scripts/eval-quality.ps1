# Agent floors are set to beat the model-free baseline that scripts/eval_agent.py now prints.
# On the current 25-pair set: best constant + deterministic cap = MAE 16.44, hit_tol10 11 (44%),
# rho 0.554; the 95th percentile of a random ranking is 0.349. The floors below clear all three.
# They are a bar to clear, not a claim about the current model - if a real-provider run goes red,
# that is information, not a broken gate. hit_tol10 is a count, so it scales with the fixture.
param(
    [switch]$ImportSeeds,
    [double]$MinRagRecall = 0.85,
    [double]$MinRagMrr = 0.85,
    [double]$MinRagKeywordHit = 0.75,
    [double]$MaxAgentMae = 8.0,
    [double]$MinAgentSpearman = 0.85,
    [int]$MinAgentHitTol10 = 17
)

$ErrorActionPreference = "Stop"

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
        --min-keyword-hit $MinRagKeywordHit

    python scripts\eval_agent.py `
        --output $agentTimestamped `
        --max-mae $MaxAgentMae `
        --min-spearman $MinAgentSpearman `
        --min-hit-tol10 $MinAgentHitTol10

    Copy-Item -LiteralPath $ragTimestamped -Destination $ragLatest -Force
    Copy-Item -LiteralPath $agentTimestamped -Destination $agentLatest -Force
}
finally {
    Pop-Location
}
