# Exercise the proposed initializer against a new disposable QA volume only.
$ErrorActionPreference = 'Stop'
$token = [Guid]::NewGuid().ToString('N')
$volume = 'techbullionhub-qa-publishing-' + $token
$root = Split-Path -Parent $PSScriptRoot
$image = 'techworld-django:development-publishing'
$configText = docker compose -f (Join-Path $root 'deploy/compose.production.yaml') config --no-interpolate --format json
if ($LASTEXITCODE -ne 0) { throw 'Production configuration could not be parsed' }
$config = $configText | ConvertFrom-Json
$initializer = $config.services.'publishing-storage-init'.command[0]
$null = docker volume create --label "techbullionhub.qa-token=$token" $volume
if ($LASTEXITCODE -ne 0) { throw 'QA volume creation failed' }
try {
    docker run --rm --pull never --network none --read-only --cap-drop ALL --cap-add CHOWN --cap-add FOWNER --user 0:0 --mount "type=volume,source=$volume,target=/app/private_publishing" --entrypoint python $image -c $initializer
    if ($LASTEXITCODE -ne 0) { throw 'Production initializer failed on disposable storage' }
    $check = "import os,stat; p='/app/private_publishing'; s=os.stat(p); assert (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(10001,10002,0o700); f=p+'/qa-write-test'; open(f,'wb').write(b'synthetic'); os.unlink(f); print('PASS: production publishing ownership, private mode and non-root write access')"
    docker run --rm --pull never --network none --read-only --cap-drop ALL --user 10001:10002 --mount "type=volume,source=$volume,target=/app/private_publishing" --entrypoint python $image -c $check
    if ($LASTEXITCODE -ne 0) { throw 'Non-root private storage probe failed' }
} finally {
    $labelJson = docker volume inspect --format '{{json .Labels}}' $volume
    if ($LASTEXITCODE -ne 0) { throw 'QA volume inspection failed; cleanup refused' }
    $labels = $labelJson | ConvertFrom-Json
    if ($labels.'techbullionhub.qa-token' -ne $token) { throw 'QA volume ownership not confirmed; cleanup refused' }
    $null = docker volume rm $volume
    if ($LASTEXITCODE -ne 0) { throw 'QA volume cleanup failed' }
}
