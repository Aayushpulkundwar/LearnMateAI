. (Join-Path $PSScriptRoot '..\Invoke-ResearchDocker.ps1')

Describe 'Invoke-ResearchProcess Windows PowerShell native stream handling' {
  BeforeEach {
    $script:testDirectory = Join-Path ([IO.Path]::GetTempPath()) ("learnmate-pwsh-$([Guid]::NewGuid().ToString('N'))")
    New-Item -ItemType Directory -Path $script:testDirectory | Out-Null
    $script:testLog = Join-Path $script:testDirectory 'execution.log'
    $script:testExe = Join-Path $PSHOME 'powershell.exe'
  }

  AfterEach {
    Remove-Item -LiteralPath $script:testDirectory -Recurse -Force -ErrorAction SilentlyContinue
  }

  It 'logs ordinary stderr and succeeds when the process exits zero' {
    $processArgs = @('-NoProfile','-Command',"[Console]::WriteLine('docker stdout'); [Console]::Error.WriteLine('docker progress'); exit 0")
    { Invoke-ResearchProcess -DockerArguments $processArgs -LogPath $script:testLog -Executable $script:testExe } | Should Not Throw
    $log = Get-Content -LiteralPath $script:testLog -Raw
    $log.Contains('[stdout]') | Should Be $true
    $log.Contains('docker stdout') | Should Be $true
    $log.Contains('[stderr]') | Should Be $true
    $log.Contains('docker progress') | Should Be $true
  }

  It 'fails on the actual nonzero process exit code and keeps both streams' {
    $processArgs = @('-NoProfile','-Command',"[Console]::WriteLine('partial output'); [Console]::Error.WriteLine('failure detail'); exit 7")
    $failure = $null
    try { Invoke-ResearchProcess -DockerArguments $processArgs -LogPath $script:testLog -Executable $script:testExe }
    catch { $failure = $_.Exception.Message }
    $failure.Contains('exit code 7') | Should Be $true
    $log = Get-Content -LiteralPath $script:testLog -Raw
    $log.Contains('partial output') | Should Be $true
    $log.Contains('failure detail') | Should Be $true
  }
}
