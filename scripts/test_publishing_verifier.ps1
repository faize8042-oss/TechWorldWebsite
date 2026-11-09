# Exercise the actual mount-validation block under Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$path = Join-Path $PSScriptRoot 'verify-publishing.ps1'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Verifier syntax errors' }
$block = $ast.FindAll({ param($node)
    $node -is [System.Management.Automation.Language.TryStatementAst] -and
    $node.Body.Extent.Text.Contains("throw 'missing mount inspection'")
}, $true) | Sort-Object { $_.Extent.Text.Length } | Select-Object -First 1
$check = [scriptblock]::Create($block.Extent.Text)
function Record($Status, $Name, $Detail) { $script:actual = $Status; $script:detail = $Detail }
$config = '{"services":{"web":{"volumes":[{"type":"volume","source":"private_publishing","target":"/app/private_publishing"}]},"nginx":{"volumes":[{"source":"./media","target":"/srv/media"}]}},"volumes":{"private_publishing":{"name":"project_private"}}}' | ConvertFrom-Json
$webJson = '[{"Destination":"/app/media","Type":"bind","RW":true,"Source":"/host/media"},{"Destination":"/app/private_publishing","Type":"volume","RW":true,"Source":"/volumes/private/_data","Name":"project_private"}]'
$parsed = $webJson | ConvertFrom-Json
$mounts = @{web = @($parsed); nginx = @()}
& $check
if ($actual -ne 'PASS') { throw "Valid mixed mounts failed: $detail" }
foreach ($source in @('/volumes/private/_data', '/volumes')) {
    $mounts.nginx = @([pscustomobject]@{Source=$source; Destination='/srv/data'})
    & $check
    if ($actual -ne 'FAIL') { throw 'Nginx exposure was accepted' }
}
$mounts.nginx = @()
$mounts.web[1].Name = 'wrong_volume'
& $check
if ($actual -ne 'FAIL') { throw 'Compose/runtime mismatch was accepted' }
$mounts.web[1].Name = 'project_private'
$mounts.web[1].RW = $false
& $check
if ($actual -ne 'FAIL') { throw 'Read-only private volume was accepted' }
Write-Host 'PASS: five mount validation cases; valid mixed mounts, Nginx volume/ancestor exposure, Compose mismatch, read-only volume'

# Exercise actual disposable Probe argument construction without Docker.
$probe = $ast.FindAll({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Probe'
}, $true) | Select-Object -First 1
Invoke-Expression $probe.Extent.Text
$root = Split-Path -Parent $PSScriptRoot
$compose = @('compose')
$DiagnoseStartup = $false
function Native($Command, $Arguments, $InputText) {
    $script:captured = $Arguments
    return [pscustomobject]@{Code=0; Text=('QA_COMPLETE:' + $script:mode)}
}
foreach ($mode in @('drift', 'tests')) {
    Probe 'Disposable test' $mode $true
    if ($actual -ne 'PASS') { throw 'Disposable probe did not complete' }
    foreach ($file in @('scripts/publishing_verify.py', 'scripts/publishing_test_runner.py',
        'config/verification_test_settings.py', 'config/test_development_csrf.py',
        'publishing/test_security.py', 'core/test_seo.py', 'nginx/default.conf', 'deploy/gunicorn.production.py')) {
        if (-not ($captured | Where-Object { $_ -like "*:/app/${file}:ro" })) {
            throw "Missing read-only file mount: $file"
        }
    }
    if ($captured -contains "${root}:/app:ro") { throw 'Broad source overlay' }
    if ($captured -contains '--no-build') { throw 'Unsupported compose run --no-build option' }
    foreach ($flag in @('--rm', '--no-deps', '--pull', 'never')) {
        if ($captured -notcontains $flag) { throw "Missing safety flag: $flag" }
    }
}
Write-Host 'PASS: drift/tests mount current helpers and security tests without replacing application packages'

# Run the exact bootstrap through Windows PowerShell native argument passing.
$bootstrapIndex = [Array]::IndexOf($captured, '-c')
$bootstrap = $captured[$bootstrapIndex + 1]
if ($bootstrap.Contains('"')) { throw 'Embedded double quote risks PS 5.1 native marshalling' }
# Substitute only the helper path, leaving actual startup/argv handling intact.
$temporary = Join-Path $root 'scripts/.publishing-bootstrap-test.py'
try {
    [IO.File]::WriteAllText($temporary, "import sys`nprint('QA_COMPLETE:' + sys.argv[1])`n")
    $bootstrap = $bootstrap.Replace('/app/scripts/publishing_verify.py', $temporary.Replace('\', '/'))
    $output = & python -c $bootstrap tests 2>&1
    if ($LASTEXITCODE -ne 0 -or $output -notcontains 'QA_COMPLETE:tests') { throw 'Native bootstrap failed' }
} finally { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }
Write-Host 'PASS: Python bootstrap native argument passing and helper mode preserved'

$diagnostics = $ast.FindAll({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'StartupDiagnostics'
}, $true) | Select-Object -First 1
Invoke-Expression $diagnostics.Extent.Text
$messages = @(StartupDiagnostics 'ModuleNotFoundError: synthetic-secret-do-not-print' 6>&1) -join "`n"
if ($messages -notmatch 'Python import failed' -or $messages -match 'synthetic-secret') { throw 'Unsafe or missing startup classification' }
$DiagnoseStartup = $true
$messages = @(Probe 'Startup only' 'tests' $true 6>&1) -join "`n"
if ($captured -notcontains '/app/config/verification_test_settings.py') { throw 'Startup mount check missing' }
$bootstrap = $captured[[Array]::IndexOf($captured, '-c') + 1]
if ($bootstrap -match 'run_path|django.setup|call_command') { throw 'Diagnostic mode can execute database probes' }
if ($messages -notmatch 'Docker argv') { throw 'Exact argument array missing' }
Write-Host 'PASS: sanitized startup classification and database-free diagnostic command'
