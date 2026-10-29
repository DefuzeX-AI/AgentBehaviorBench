param([ValidateSet('before','after')][string]$Arm)
$ErrorActionPreference = 'Stop'
$experimentRoot = $PSScriptRoot
$repositoryRoot = Split-Path (Split-Path $experimentRoot -Parent) -Parent
Set-Location $repositoryRoot
& '.\.venv\Scripts\python.exe' -m agentbench evaluate "verify-reasonix14403-$Arm" --registry "$experimentRoot\registry.toml" --env-file "$repositoryRoot\.env" --sdk native --case-file "$experimentRoot\case.json" --cases 1 --max-steps 1 --case-retries 0 --no-view --results-dir "$experimentRoot\$Arm-results" -y *> "$experimentRoot\$Arm.log"
exit $LASTEXITCODE
