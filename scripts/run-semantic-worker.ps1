param([Parameter(ValueFromRemainingArguments=$true)][string[]]$WorkerArgs)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$py=Join-Path $root '.venv-semantic\Scripts\python.exe'
if(!(Test-Path -LiteralPath $py)){ throw 'SEMANTIC_WORKER_RUNTIME_MISSING' }
$cfg=Join-Path $root 'config\semantic-search\kdi_semantic_analyzer_v1.json'
if(!(Test-Path -LiteralPath $cfg)){ throw 'SEMANTIC_WORKER_CONFIG_MISSING' }
if(!$WorkerArgs -or !$WorkerArgs[0]){ throw 'SEMANTIC_WORKER_ENTRYPOINT_REQUIRED' }
$target=Join-Path $root $WorkerArgs[0]
if(!(Test-Path -LiteralPath $target)){ throw 'SEMANTIC_WORKER_ENTRYPOINT_NOT_FOUND' }
$logDir=Join-Path $root 'reports\semantic-search\rollout\phase-08\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$env:KDI_SEMANTIC_CONFIG=$cfg
$env:KDI_SEMANTIC_PYTHON=$py
$env:PIP_ONLY_BINARY=':all:'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$rest=@($WorkerArgs | Select-Object -Skip 1)
$priorErrorPreference=$ErrorActionPreference
$ErrorActionPreference='Continue'
& $py $target @rest 2>&1 | Tee-Object -FilePath (Join-Path $logDir "semantic-worker-$stamp.log")
$workerExit=$LASTEXITCODE
$ErrorActionPreference=$priorErrorPreference
if($workerExit -ne 0){ throw "SEMANTIC_WORKER_FAILED_$workerExit" }
