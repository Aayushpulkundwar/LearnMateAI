param(
  [string]$AdminToken,
  [Microsoft.PowerShell.Commands.WebRequestSession]$WebSession,
  [string]$ApiBaseUrl = 'http://127.0.0.1:8000/api/v1',
  [string]$Archive = (Join-Path (Get-Location) 'ScienceCS10.zip')
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$results = Join-Path $root 'research\results'
$manifestPath = Join-Path $results 'sciencecs10_ingestion_manifest.json'
Add-Type -AssemblyName System.Net.Http
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (-not $AdminToken -and -not $WebSession) { throw 'Provide an authenticated admin bearer token or WebSession.' }
$headers = @{}
if ($AdminToken) { $headers.Authorization = "Bearer $AdminToken" }
$httpHandler = [Net.Http.HttpClientHandler]::new()
if ($WebSession) { $httpHandler.UseCookies = $true; $httpHandler.CookieContainer = $WebSession.Cookies }
$httpClient = [Net.Http.HttpClient]::new($httpHandler)
$chapters = [ordered]@{
  1='Chemical Reactions and Equations'; 2='Acids, Bases and Salts'; 3='Metals and Non-metals'; 4='Carbon and its Compounds'; 5='Life Processes'; 6='Control and Coordination'; 7='How do Organisms Reproduce?'; 8='Heredity and Evolution'; 9='Light - Reflection and Refraction'; 10='The Human Eye and the Colourful World'; 11='Electricity'; 12='Magnetic Effects of Electric Current'; 13='Our Environment'
}

# Identity gate: inspect, do not migrate or upload until the operator confirms this is LearnMateAI staging.
docker compose -f (Join-Path $root 'docker-compose.yml') ps
docker compose -f (Join-Path $root 'docker-compose.yml') exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT current_database() || ''|'' || current_user;"'
Read-Host 'Confirm the database identity above is the intended LearnMateAI staging database; press Enter to continue'
docker compose -f (Join-Path $root 'docker-compose.yml') exec api python -m alembic current
docker compose -f (Join-Path $root 'docker-compose.yml') exec api python -m alembic heads
docker compose -f (Join-Path $root 'docker-compose.yml') exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT extname FROM pg_extension WHERE extname = ''vector''; SELECT indexname FROM pg_indexes WHERE tablename = ''chunks'' AND indexname = ''ix_chunks_content_fts'';"'
docker compose -f (Join-Path $root 'docker-compose.yml') exec ollama ollama list

# Registration uses existing curriculum models and refuses title conflicts.
$curriculum = docker compose -f (Join-Path $root 'docker-compose.yml') exec -T api python -m scripts.seed_class10_science_chapters | Select-Object -Last 1 | ConvertFrom-Json
New-Item -ItemType Directory -Force $results | Out-Null
$zip = [IO.Compression.ZipFile]::OpenRead((Resolve-Path $Archive))
try {
  $pdfs = @($zip.Entries | Where-Object { $_.FullName -match '^ScienceCS10/ch(\d+)\.pdf$' })
  if ($pdfs.Count -ne 13) { throw "Expected exactly 13 ScienceCS10/chN.pdf entries; found $($pdfs.Count)." }
  $existing = if ($WebSession) { Invoke-RestMethod "$ApiBaseUrl/documents/" -Headers $headers -WebSession $WebSession } else { Invoke-RestMethod "$ApiBaseUrl/documents/" -Headers $headers }
  $previous = if (Test-Path $manifestPath) { Get-Content $manifestPath -Raw | ConvertFrom-Json } else { @() }
  $work = Join-Path ([IO.Path]::GetTempPath()) ('learnmate-sciencecs10-' + [guid]::NewGuid())
  New-Item -ItemType Directory -Force $work | Out-Null
  $records = @()
  foreach ($number in 1..13) {
    $entry = $pdfs | Where-Object { $_.FullName -eq "ScienceCS10/ch$number.pdf" }
    if ($entry.Length -le 0) { throw "ch$number.pdf is empty." }
    $path = Join-Path $work "ch$number.pdf"; [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $path)
    $bytes = [IO.File]::ReadAllBytes($path); if ([Text.Encoding]::ASCII.GetString($bytes,0,5) -ne '%PDF-') { throw "ch$number.pdf lacks PDF signature." }
    $hash = (Get-FileHash $path -Algorithm SHA256).Hash
    $chapter = $curriculum.chapters."$number"
    $prior = @($previous | Where-Object { $_.sha256 -eq $hash }) | Select-Object -First 1
    $collision = @($existing | Where-Object { $_.chapter_id -eq $chapter.id -and $_.processing_status -eq 'completed' }) | Select-Object -First 1
    if ($prior -or $collision) { $records += [pscustomobject]@{chapter=$number;title=$chapter.name;sha256=$hash;document_id=if($prior){$prior.document_id}else{$collision.id};status='skipped_existing'}; continue }
    $form = [Net.Http.MultipartFormDataContent]::new(); $stream = $null; $request = $null; $response = $null
    try {
      $form.Add([Net.Http.StringContent]::new("Class 10 Science - Chapter $number - $($chapter.name) (ch$number.pdf)"), 'title')
      $form.Add([Net.Http.StringContent]::new('Science'), 'subject'); $form.Add([Net.Http.StringContent]::new('10'), 'grade'); $form.Add([Net.Http.StringContent]::new($chapter.name), 'chapter')
      $form.Add([Net.Http.StringContent]::new($curriculum.grade_id), 'grade_id'); $form.Add([Net.Http.StringContent]::new($curriculum.subject_id), 'subject_id'); $form.Add([Net.Http.StringContent]::new($chapter.id), 'chapter_id')
      $stream = [IO.File]::OpenRead($path); $file = [Net.Http.StreamContent]::new($stream); $file.Headers.ContentType = 'application/pdf'; $form.Add($file, 'file', "ch$number.pdf")
      $request = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Post, "$ApiBaseUrl/documents/upload"); if($AdminToken){$request.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer',$AdminToken)}; $request.Content=$form
      $response=$httpClient.SendAsync($request).GetAwaiter().GetResult(); $body=$response.Content.ReadAsStringAsync().GetAwaiter().GetResult(); if(-not $response.IsSuccessStatusCode){throw "Upload ch$number failed: $($response.StatusCode) $body"}; $doc=$body|ConvertFrom-Json
    } finally { if($response){$response.Dispose()}; if($request){$request.Dispose()}; if($form){$form.Dispose()}; if($stream){$stream.Dispose()} }
    do { Start-Sleep -Seconds 5; $state=if($WebSession){Invoke-RestMethod "$ApiBaseUrl/documents/$($doc.id)/status" -Headers $headers -WebSession $WebSession}else{Invoke-RestMethod "$ApiBaseUrl/documents/$($doc.id)/status" -Headers $headers} } while($state.processing_status -in @('pending','processing'))
    $records += [pscustomobject]@{chapter=$number;title=$chapter.name;sha256=$hash;document_id=$doc.id;status=$state.processing_status}
  }
  $records | ConvertTo-Json -Depth 4 | Set-Content $manifestPath
} finally { if($zip){$zip.Dispose()}; if($httpClient){$httpClient.Dispose()}; if($httpHandler){$httpHandler.Dispose()} }
docker compose -f (Join-Path $root 'docker-compose.yml') exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --csv -c "SELECT d.id AS document_id,d.title,d.chapter,d.processing_status,count(c.id) AS chunks,min(c.page_number) AS first_source_page,max(c.page_number) AS last_source_page,min(vector_dims(c.embedding)) AS min_embedding_dim,max(vector_dims(c.embedding)) AS max_embedding_dim FROM documents d LEFT JOIN chunks c ON c.document_id=d.id WHERE d.subject=''Science'' AND d.grade IN (''10'',''Class 10'') GROUP BY d.id ORDER BY d.chapter;"' | Set-Content (Join-Path $results 'sciencecs10_provenance.csv')
Write-Output "Manifest: $manifestPath"
