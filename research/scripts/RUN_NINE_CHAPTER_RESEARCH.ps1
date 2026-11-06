param(
  [Parameter(Mandatory=$true)][ValidateSet('Prepare','Evaluate','ScoreAnswers','Report')][string]$Phase,
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$RunId,
  [string]$ReviewedDataset,
  [ValidateSet('dev','test')][string]$Split = 'test',
  [switch]$GenerateAnswers
)
$ErrorActionPreference = 'Stop'
$dockerInvoker = Join-Path $PSScriptRoot 'Invoke-ResearchDocker.ps1'
. $dockerInvoker
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$output = Join-Path $root "research\results\$RunId"
$containerRun = "/tmp/learnmate-nine-$RunId"
$compose = @('compose','-f',(Join-Path $root 'docker-compose.yml'))
New-Item -ItemType Directory -Force $output | Out-Null

function Invoke-ResearchDocker([string[]]$DockerArguments) {
  Invoke-ResearchProcess -DockerArguments $DockerArguments -LogPath (Join-Path $output 'execution.log')
}

# This runner never invokes ingestion, migrations, retries, or document updates.
if ($Phase -eq 'Prepare') {
  Invoke-ResearchDocker ($compose + @('ps'))
  $candidates = Join-Path $root 'research\datasets\nine_chapters\questions.candidates.jsonl'
  Invoke-ResearchDocker ($compose + @('cp',$candidates,"api:/tmp/nine-$RunId.candidates.jsonl"))
  Invoke-ResearchDocker ($compose + @('exec','-T','api','python','-m','scripts.nine_chapter_research','freeze','--output',$containerRun,'--dataset',"/tmp/nine-$RunId.candidates.jsonl"))
  Invoke-ResearchDocker ($compose + @('exec','-T','api','python','-m','scripts.nine_chapter_research','smoke','--output',$containerRun))
  & git -C $root rev-parse HEAD | Set-Content (Join-Path $output 'host-code-revision.txt')
  & git -C $root diff -- backend/app/evaluation backend/app/services/retrieval_service.py backend/scripts/nine_chapter_research.py | Set-Content (Join-Path $output 'research-code.diff')
} elseif ($Phase -eq 'Evaluate' -or $Phase -eq 'ScoreAnswers') {
  if (-not $ReviewedDataset -or -not (Test-Path -LiteralPath $ReviewedDataset)) { throw 'Supply the independently reviewed JSONL path.' }
  Invoke-ResearchDocker ($compose + @('cp',(Resolve-Path $ReviewedDataset).Path,"api:/tmp/nine-$RunId.reviewed.jsonl"))
  $action = if ($Phase -eq 'Evaluate') { 'run' } else { 'score-answers' }
  $arguments = $compose + @('exec','-T','api','python','-m','scripts.nine_chapter_research',$action,'--output',$containerRun,'--dataset',"/tmp/nine-$RunId.reviewed.jsonl",'--split',$Split)
  if ($GenerateAnswers -and $Phase -eq 'Evaluate') { $arguments += '--answers' }
  Invoke-ResearchDocker $arguments
} else {
  Invoke-ResearchDocker ($compose + @('exec','-T','api','python','-m','scripts.nine_chapter_research','report','--output',$containerRun))
}
Invoke-ResearchDocker ($compose + @('cp',"api:$containerRun/.",$output))
Write-Host "Nine-chapter evidence: $output"
