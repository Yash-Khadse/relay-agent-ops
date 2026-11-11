param([ValidateSet('api','worker','web','test')][string]$Service = 'api')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($Service -eq 'web') { pnpm.cmd --dir apps/web dev; exit $LASTEXITCODE }
if (Test-Path '.venv-runtime/Scripts/python.exe') { $taskPython = '.venv-runtime/Scripts/python.exe' }
elseif (Test-Path '.venv/Scripts/python.exe') { $taskPython = '.venv/Scripts/python.exe' }
else { throw 'Run uv sync --extra crew first.' }
switch ($Service) {
  'api' { & $taskPython -m uvicorn relay.api:app --host 127.0.0.1 --port 8000 }
  'worker' { & $taskPython -m relay.worker }
  'test' { & $taskPython -m pytest -q --basetemp ('data/tests-' + [guid]::NewGuid().ToString('N')) }
}
exit $LASTEXITCODE
