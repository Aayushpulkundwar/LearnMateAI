param(
  [string]$ApiBaseUrl = 'http://127.0.0.1:8000/api/v1',
  [string]$Archive,
  [switch]$RunReviewedBenchmark
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Archive) { $Archive = Join-Path $root 'ScienceCS10.zip' }
$results = Join-Path $root 'research\results'
New-Item -ItemType Directory -Force $results | Out-Null

# Real FastAPI session login: password/token never appears in output or files.
$email = Read-Host 'Administrator email'
$securePassword = Read-Host 'Administrator password' -AsSecureString
$credential = [pscredential]::new($email, $securePassword)
$plainPassword = $credential.GetNetworkCredential().Password
$session = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
try {
  $login = Invoke-RestMethod "$ApiBaseUrl/auth/login" -Method Post -WebSession $session -ContentType 'application/json' -Body (@{email=$email;password=$plainPassword} | ConvertTo-Json -Compress)
} finally { $plainPassword = $null; $credential = $null; $securePassword = $null }
if (-not $login.student.is_admin) { throw 'The authenticated account is not an administrator.' }

# The importer displays database identity/migration/index state and requires a second explicit confirmation before writes.
Write-Host "Authenticated as administrator $($login.student.email)."
$approval = Read-Host 'Type IMPORT_CLASS10_SCIENCE to authorize curriculum registration and PDF uploads to the identified staging database'
if ($approval -ne 'IMPORT_CLASS10_SCIENCE') { throw 'No database modification was authorized.' }
& (Join-Path $PSScriptRoot 'import_sciencecs10.ps1') -WebSession $session -ApiBaseUrl $ApiBaseUrl -Archive $Archive

# Existing evaluator: execute only if independent human-reviewed labels have been supplied.
$dataset = Join-Path $root 'research\datasets\class10-science\retrieval.jsonl'
if ($RunReviewedBenchmark -and (Test-Path $dataset)) {
  $datasetHash = (Get-FileHash $dataset -Algorithm SHA256).Hash
  $datasetName = 'class10-science-retrieval.jsonl'
  docker compose -f (Join-Path $root 'docker-compose.yml') cp $dataset "tutor_api:/app/$datasetName"
  docker compose -f (Join-Path $root 'docker-compose.yml') exec -T api python -m scripts.review_dataset validate "/app/$datasetName"
  docker compose -f (Join-Path $root 'docker-compose.yml') exec -T api python -m scripts.run_retrieval_benchmark "/app/$datasetName" /app/class10-science-e1.json --split dev --mode all --calibrate
  docker compose -f (Join-Path $root 'docker-compose.yml') cp tutor_api:/app/class10-science-e1.json (Join-Path $results 'class10-science-e1.dev.json')
  [pscustomobject]@{dataset=$dataset;sha256=$datasetHash;split='dev';status='executed_with_human_reviewed_labels'} | ConvertTo-Json | Set-Content (Join-Path $results 'class10-science-e1.manifest.json')
} else {
  [pscustomobject]@{status='not_executed';reason='No human-reviewed benchmark JSONL was supplied, or -RunReviewedBenchmark was omitted.'} | ConvertTo-Json | Set-Content (Join-Path $results 'class10-science-e1.blocked.json')
}

# Candidate material is deliberately not a label or metric. Human reviewers author/adjudicate questions from provenance CSV.
[pscustomobject]@{status='pending_human_review';source=(Join-Path $results 'sciencecs10_provenance.csv');instruction='Create split-separated questions with gold chunk IDs and evidence spans; do not treat generated or smoke data as ground truth.'} | ConvertTo-Json | Set-Content (Join-Path $results 'class10-science-candidate-review-queue.json')
Write-Host "Research outputs written to $results"
