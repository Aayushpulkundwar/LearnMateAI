param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunId
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runDir = Join-Path $root 'research\results\nine_science_03'
$experiment = Join-Path $root 'research\experiments\rag_comparison'
$dataset = Join-Path $experiment 'datasets\questions.jsonl'
$runs = Join-Path $experiment 'runs'
$log = Join-Path $experiment 'execution.log'
$compose = @('compose','-f',(Join-Path $root 'docker-compose.yml'))
$container = "/tmp/learnmate-rag-$RunId"

. (Join-Path $PSScriptRoot 'Invoke-ResearchDocker.ps1')

$frozenArtifacts = @('corpus.json','environment.json','ollama_models.json')
$requiredFiles = @($frozenArtifacts | ForEach-Object { Join-Path $runDir $_ })
$requiredFiles += @($dataset,
  (Join-Path $experiment 'system_configuration.json'),
  (Join-Path $experiment 'datasets\dataset_report.json'),
  (Join-Path $runDir 'questions.candidates.jsonl'))
$missing = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($missing.Count -gt 0) {
  throw ("Missing required research files:`n - " + ($missing -join "`n - ") +
    "`nUse the original nine_science_03 preparation artifacts; do not regenerate frozen metadata.")
}
foreach ($mode in @('dense','fts','hybrid')) {
  if (Test-Path -LiteralPath (Join-Path $runs "$mode.json")) { throw "Refusing to overwrite existing retrieval evidence: $mode.json" }
}
New-Item -ItemType Directory -Force -Path $runs | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

# Retrieval uses existing API-container code and opens the frozen database read-only.
Invoke-ResearchProcess -DockerArguments ($compose + @('exec','-T','api','mkdir','-p',"$container/frozen","$container/output/runs")) -LogPath $log
foreach ($artifact in $frozenArtifacts) {
  Invoke-ResearchProcess -DockerArguments ($compose + @('cp',(Join-Path $runDir $artifact),"api:$container/frozen/$artifact")) -LogPath $log
}
Invoke-ResearchProcess -DockerArguments ($compose + @('cp',$dataset,"api:$container/frozen/questions.jsonl")) -LogPath $log
Invoke-ResearchProcess -DockerArguments ($compose + @('exec','-T','api','python','-m','scripts.rag_comparison','retrieve',
  '--run-dir',"$container/frozen",'--dataset',"$container/frozen/questions.jsonl",'--output-dir',"$container/output")) -LogPath $log
# Recheck before copying back, and copy each file into runs (no nested runs directory).
foreach ($mode in @('dense','fts','hybrid')) {
  if (Test-Path -LiteralPath (Join-Path $runs "$mode.json")) { throw "Refusing to overwrite existing retrieval evidence: $mode.json" }
}
foreach ($mode in @('dense','fts','hybrid')) {
  Invoke-ResearchProcess -DockerArguments ($compose + @('cp',"api:$container/output/runs/$mode.json",(Join-Path $runs "$mode.json"))) -LogPath $log
}
foreach ($mode in @('dense','fts','hybrid')) {
  if (-not (Test-Path -LiteralPath (Join-Path $runs "$mode.json"))) { throw "Retrieval output missing: $mode.json" }
}
Push-Location (Join-Path $root 'backend')
try {
  Invoke-ResearchProcess -Executable 'python' -DockerArguments @('-m','scripts.rag_comparison','manifest',
    '--run-dir','../research/results/nine_science_03','--experiment-dir','../research/experiments/rag_comparison',
    '--source-dataset','../research/results/nine_science_03/questions.candidates.jsonl',
    '--subset-dataset','../research/experiments/rag_comparison/datasets/questions.jsonl','--refresh') -LogPath $log
}
finally { Pop-Location }
Write-Host "Retrieval outputs are in $runs; inspect query statuses before pooling."
