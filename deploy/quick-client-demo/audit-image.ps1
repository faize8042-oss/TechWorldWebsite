# Read-only image audit. Run in the operator's authorized Windows PowerShell.
# Requires Docker CLI and trusted host Python 3.6+ within major version 3 (stdlib only).
# Never imports image code, extracts tar members, or creates/starts a container.
[CmdletBinding()]
param([string]$Python = 'python.exe', [switch]$TestPythonOffline)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Shared by the prerequisite probe, offline tests and filesystem helper.
# Match subscripting and pathlib paths passed to tarfile require Python 3.6.
$pythonPolicy = @'
import sys
def audit_python_supported(version):
    return version[0] == 3 and version[:2] >= (3, 6)
'@
$pythonProbe = $pythonPolicy + "`n" + @'
if len(sys.argv) == 2 and sys.argv[1] == '--self-test':
    for version, supported in (((2, 7), False), ((3, 5), False), ((3, 6), True),
                               ((3, 12), True), ((3, 14), True), ((3, 99), True), ((4, 0), False)):
        if audit_python_supported(version) != supported:
            sys.exit(4)
if not audit_python_supported(sys.version_info):
    sys.exit(3)
# Check the actual isolated interpreter's stdlib; no image/application imports.
import ast, collections, hashlib, io, json, pathlib, re, tarfile
assert re.search(b'x', b'x')[0] == b'x'
ast.parse(b'x = 1')
with tarfile.open(fileobj=io.BytesIO(), mode='w'):
    pass
sys.exit(0)
'@
function Invoke-PythonProbe([string]$Command, [switch]$Offline) {
    $oldPreference = $ErrorActionPreference
    try {
        # Capture native stderr privately, including under Windows PowerShell.
        $ErrorActionPreference = 'Continue'
        $probeArguments = @('-I', '-S', '-B', '-')
        if ($Offline) { $probeArguments += '--self-test' }
        $captured = @($pythonProbe | & $Command @probeArguments 2>&1)
        $code = $LASTEXITCODE
        if ($captured.Count) { $code = 4 }
    } finally { $ErrorActionPreference = $oldPreference }
    return $code
}
if ($TestPythonOffline) {
    try {
        $command = (Get-Command $Python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
        if ((Invoke-PythonProbe $command -Offline) -ne 0) { throw 'Probe failed' }
        Write-Output 'Offline Python policy and isolated stdlib probe: PASS'
        exit 0
    } catch {
        Write-Output 'Offline Python policy or interpreter probe: FAIL (details suppressed)'
        exit 1
    }
}
$expected = 'sha256:69c0b8cdfa8a03b9517d6bd9a80bb1afc7c024ee355e78ac79effa3c62587cdf'
$report = Join-Path $PSScriptRoot 'image-audit-report.txt'
$stage = 'report-destination'
$category = 'report-io-or-path-policy'
$token = $null
$temp = $null
$reportSafe = $false
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('Codeventra Labs existing image-content audit')
$lines.Add('Image: techworld-django:local')
$lines.Add('Expected image ID: ' + $expected)
$lines.Add('UTC: ' + [DateTime]::UtcNow.ToString('o'))
$lines.Add('Public exposure: NOT APPROVED. No image code is executed by this audit.')
$lines.Add('Scope: configuration, history, all saved layers and reconstructed file inventory.')
$lines.Add('Limits: heuristic detection cannot prove absence of secrets or malicious code; no runtime, dependency integrity, vulnerability or provenance certification.')
$exitCode = 1
function Invoke-DockerPrivate([string[]]$Arguments) {
    $reply = Invoke-NativePrivate $dockerCommand $Arguments
    if ($reply.Code -ne 0) { throw 'Docker inspection failed' }
    return $reply.Output
}
function Invoke-NativePrivate([string]$Command, [string[]]$Arguments) {
    # ProcessStartInfo avoids PowerShell 5.1 native stream/encoding conversion.
    # Drain both pipes concurrently to avoid deadlock; diagnostics never reach reports.
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Command
    $quoted = foreach ($argument in $Arguments) {
        '"' + (($argument -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
    }
    $info.Arguments = $quoted -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.UTF8Encoding]::new($false, $true)
    $info.StandardErrorEncoding = [Text.UTF8Encoding]::new($false, $false)
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    try {
        if ($null -eq ('CodeventraAuditCapture' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Threading.Tasks;
public static class CodeventraAuditCapture {
    public static async Task<string> Read(StreamReader reader, int limit) {
        var result = new StringBuilder();
        var buffer = new char[8192];
        bool overflow = false;
        Exception readError = null;
        int count;
        try {
            while ((count = await reader.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false)) != 0) {
                if (result.Length + count <= limit && !overflow) result.Append(buffer, 0, count);
                else overflow = true;
            }
        } catch (Exception error) { readError = error; }
        if (readError != null) {
            // A decoding failure must not leave a writer blocked on a full pipe.
            await reader.BaseStream.CopyToAsync(Stream.Null).ConfigureAwait(false);
            throw readError;
        }
        if (overflow) throw new IOException("Native output limit");
        return result.ToString();
    }
}
'@
        }
        if (-not $process.Start()) { throw 'Native launch failed' }
        $stdout = [CodeventraAuditCapture]::Read($process.StandardOutput, 64MB)
        $stderr = [CodeventraAuditCapture]::Read($process.StandardError, 1MB)
        $process.WaitForExit()
        $output = $stdout.GetAwaiter().GetResult()
        $errorOutput = $stderr.GetAwaiter().GetResult()
        return [pscustomobject]@{ Code = $process.ExitCode; Output = $output; ErrorPresent = ($errorOutput.Length -ne 0) }
    } finally { $process.Dispose() }
}
try {
    # Replace any stale verdict before inspection. Reject report links/reparse points.
    $ancestor = Get-Item -LiteralPath $PSScriptRoot -Force
    while ($null -ne $ancestor) {
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Report parent rejected' }
        $ancestor = $ancestor.Parent
    }
    if (Test-Path -LiteralPath $report) {
        if ((Get-Item -LiteralPath $report -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Report target rejected' }
    }
    $reportSafe = $true
    $lines.Add('Verdict: FAIL (inspection not yet complete)')
    [IO.File]::WriteAllLines($report, $lines)
    $stage = 'docker-prerequisite'
    $category = 'docker-command-unavailable'
    $dockerCommand = (Get-Command docker -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $stage = 'python-prerequisite'
    $category = 'python-command-unavailable'
    $pythonCommand = (Get-Command $Python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $stage = 'baseline-validation'
    $category = 'baseline-invalid-or-identity-mismatch'
    $stage = 'python-version'
    $category = 'python-launch-or-stdlib-probe-failed'
    $probeCode = Invoke-PythonProbe $pythonCommand
    if ($probeCode -eq 3) { $category = 'python-version-unsupported' }
    if ($probeCode -ne 0) { throw 'Python prerequisite failed' }
    $stage = 'baseline-validation'
    $category = 'baseline-validator-load-error'
    . (Join-Path $PSScriptRoot 'image-baseline.ps1')
    $validation = Read-ImageBaseline (Join-Path $PSScriptRoot 'verified-images.json') $expected
    if ($null -ne $validation.Category) {
        $category = $validation.Category
        if ($validation.Missing.Count) { $lines.Add('Missing baseline fields: ' + ($validation.Missing -join ', ')) }
        throw 'Baseline rejected'
    }
    $stage = 'tag-inspection'
    $category = 'docker-read-or-identity-mismatch'
    $observedJson = Invoke-DockerPrivate @('image', 'inspect', 'techworld-django:local')
    $parsed = ConvertFrom-Json -InputObject $observedJson
    $observed = @($parsed)
    if ($observed.Count -ne 1 -or $observed[0].Id -cne $expected) { throw 'Image identity mismatch' }
    $stage = 'pinned-inspection'
    $category = 'docker-read-or-identity-mismatch'
    $pinnedJson = Invoke-DockerPrivate @('image', 'inspect', $expected)
    $parsed = ConvertFrom-Json -InputObject $pinnedJson
    $pinned = @($parsed)
    if ($pinned.Count -ne 1 -or $pinned[0].Id -cne $expected) { throw 'Pinned identity mismatch' }
    # Private spool lives outside the repository. Set an ACL before storing image bytes.
    $stage = 'private-spool-setup'
    $category = 'temporary-path-acl-or-io'
    $temp = Join-Path ([IO.Path]::GetTempPath()) ('codeventra-image-audit-' + [guid]::NewGuid().ToString('N'))
    $repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..')).TrimEnd('\') + '\'
    if ([IO.Path]::GetFullPath($temp).StartsWith($repo, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe temporary location' }
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl.SetOwner($sid)
    $rule = [Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    $ancestor = Get-Item -LiteralPath ([IO.Path]::GetTempPath()) -Force
    while ($null -ne $ancestor) {
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Spool parent rejected' }
        $ancestor = $ancestor.Parent
    }
    if (Test-Path -LiteralPath $temp) { throw 'Spool already exists' }
    # Windows PowerShell 5.1 / .NET Framework creates with the private ACL atomically.
    $null = [IO.Directory]::CreateDirectory($temp, $acl)
    if ((Get-Acl -LiteralPath $temp).GetOwner([Security.Principal.SecurityIdentifier]) -ne $sid) { throw 'Spool owner rejected' }
    $token = [guid]::NewGuid().ToString('N')
    [IO.File]::WriteAllText((Join-Path $temp '.owner'), $token)
    [IO.File]::WriteAllText((Join-Path $temp 'observed.json'), $pinnedJson)
    # Preserve original JSON bytes: reserialization could conceal duplicate keys.
    [IO.File]::WriteAllBytes((Join-Path $temp 'baseline.json'), [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'verified-images.json')))
    $stage = 'history-read'
    $category = 'docker-history-or-spool-io'
    $history = Invoke-DockerPrivate @('image', 'history', '--no-trunc', '--format', '{{json .}}', $expected)
    [IO.File]::WriteAllText((Join-Path $temp 'history.jsonl'), $history)
    $stage = 'image-save'
    $category = 'docker-save-or-spool-io'
    $null = Invoke-DockerPrivate @('image', 'save', '--output', (Join-Path $temp 'image.tar'), $expected)
    $stage = 'helper-write'
    $category = 'spool-io'
    $helper = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'inspect_image.py'))
    [IO.File]::WriteAllText((Join-Path $temp 'inspect_image.py'), $helper, [Text.UTF8Encoding]::new($false))
    # -I -S bypasses host environment, site packages and startup hooks too.
    $stage = 'filesystem-inspection'
    $category = 'helper-runtime-or-incomplete-output'
    $reply = Invoke-NativePrivate $pythonCommand @('-I', '-S', '-B', (Join-Path $temp 'inspect_image.py'), $temp, $expected)
    $result = @($reply.Output -split '\r?\n' | Where-Object { $_.Length })
    $helperCode = $reply.Code
    if ($reply.ErrorPresent) { throw 'Helper diagnostics rejected' }
    # Only fixed vocabulary and integer counts may enter the repository report.
    $safe = @($result | ForEach-Object { [string]$_ } | Where-Object {
        $_ -cmatch '^(COUNT|FAIL) [a-z0-9-]+: [0-9]+$' -or
        $_ -ceq 'Inspection: COMPLETE (static checks only; manual gates remain unresolved)' -or
        $_ -ceq 'Verdict: FAIL' -or
        $_ -ceq 'Verdict: PASS (static scope only; no public exposure approval)' -or
        $_ -cmatch '^Failure stage: helper-(metadata|history|saved-archive|layer-integrity-and-filesystem|final-inventory)$' -or
        $_ -cmatch '^Error category: (resource-limit|spool-io|invalid-data-or-integrity|helper-runtime)$' -or
        $_ -cmatch '^Failure detail: (missing-archive-member|unsafe-archive-path|invalid-oci-descriptor|unsupported-oci-digest|oci-descriptor-integrity|image-identity-digest-mismatch|oci-index-depth-limit|invalid-oci-document|invalid-oci-index|invalid-oci-manifest|image-identity-config-binding-mismatch|stored-layer-digest-mismatch|unsupported-zstd-layer-compression|layer-expansion-limit|layer-decompression-failed|uncompressed-layer-diffid-mismatch|unsafe-link-target)$'
    })
    $lines.AddRange([string[]]$safe)
    if (@($safe | Where-Object { $_ -like 'Failure stage: helper-*' }).Count) {
        $category = 'helper-aborted-before-complete-evidence'
        throw 'Helper incomplete'
    }
    if ($safe.Count -ne $result.Count -or $helperCode -notin @(0,1) -or
        @($safe | Where-Object { $_ -like 'Inspection: COMPLETE*' }).Count -ne 1 -or
        @($safe | Where-Object { $_ -like 'Verdict: *' }).Count -ne 1 -or
        ($helperCode -eq 0 -and ($safe -contains 'Verdict: FAIL' -or @($safe | Where-Object { $_ -like 'FAIL *' }).Count)) -or
        ($helperCode -eq 1 -and $safe -notcontains 'Verdict: FAIL')) {
        throw 'Filesystem inspection incomplete'
    }
    $evidence = @{}
    foreach ($line in $safe) {
        if ($line -cmatch '^COUNT ([a-z0-9-]+): ([0-9]+)$') {
            if ($evidence.ContainsKey($Matches[1])) { throw 'Duplicate inspection evidence' }
            $evidence[$Matches[1]] = [long]$Matches[2]
        }
    }
    foreach ($name in @('environment-names-inspected','labels-inspected','history-entries-inspected',
        'saved-config-sha256-verified-against-name','saved-image-identity-verified','verified-layers','layer-entries-inspected',
        'historical-files-scanned','final-inventory-entries','template-files','static-source-files',
        'collected-static-files','required-distributions-present')) {
        if (-not $evidence.ContainsKey($name)) { throw 'Missing inspection evidence' }
    }
    if ($evidence['verified-layers'] -ne $pinned[0].RootFS.Layers.Count) { throw 'Incomplete layer evidence' }
    if ($helperCode -eq 0 -and
        ($evidence['saved-config-sha256-verified-against-name'] -ne 1 -or
         $evidence['saved-image-identity-verified'] -ne 1 -or
         $evidence['required-distributions-present'] -ne 13 -or
         @('history-entries-inspected','layer-entries-inspected','historical-files-scanned',
           'final-inventory-entries','template-files','static-source-files','collected-static-files' |
             Where-Object { $evidence[$_] -le 0 }).Count)) { throw 'Insufficient passing evidence' }
    $exitCode = $helperCode
    if ($exitCode -ne 0) {
        $lines.Add('Failure stage: content-policy')
        $lines.Add('Error category: mandatory-security-findings-or-review-evidence-missing')
    }
    $lines.Add('Decision: reuse remains BLOCKED pending independent private review and separate exposure authorization.')
} catch {
    $exitCode = 1
    # Do not print exception messages, native stderr, image paths, values or file contents.
    $lines.Add('Failure stage: ' + $stage)
    $lines.Add('Error category: ' + $category)
    $lines.Add('Inspection: INCOMPLETE or prerequisite failed; details suppressed to protect private data.')
    $lines.Add('Verdict: FAIL')
} finally {
    $null = $lines.Remove('Verdict: FAIL (inspection not yet complete)')
    if ($null -ne $temp -and (Test-Path -LiteralPath $temp)) {
        try {
            $full = [IO.Path]::GetFullPath($temp)
            $allowed = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
            $item = Get-Item -LiteralPath $full -Force
            if (-not $full.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase) -or
                $item.Name -cnotmatch '^codeventra-image-audit-[a-f0-9]{32}$' -or
                ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                (Get-Acl -LiteralPath $full).GetOwner([Security.Principal.SecurityIdentifier]) -ne $sid -or
                -not (Test-Path -LiteralPath (Join-Path $full '.owner')) -or
                ((Get-Item -LiteralPath (Join-Path $full '.owner') -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                [IO.File]::ReadAllText((Join-Path $full '.owner')) -cne $token) { throw 'Ownership verification failed' }
            # No image files were extracted: only our six fixed spool files exist here.
            $children = @(Get-ChildItem -LiteralPath $full -Force)
            foreach ($child in $children) {
                if ($child.PSIsContainer -or ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                    $child.Name -notin @('.owner','observed.json','baseline.json','history.jsonl','image.tar','inspect_image.py')) { throw 'Unexpected temporary entry' }
            }
            foreach ($child in $children) { Remove-Item -LiteralPath $child.FullName -Force }
            Remove-Item -LiteralPath $full -Force
            $lines.Add('Temporary private spool: removed after exact ownership and path verification.')
        } catch {
            $lines.Add('Failure stage: temporary-spool-cleanup')
            $lines.Add('Error category: cleanup-path-ownership-or-io')
            $lines.Add('FAIL temporary-spool-cleanup: 1')
            $exitCode = 1
            $lines.Add('Restricted temporary spool may remain in the operator TEMP directory; manual review required.')
        }
    }
    if ($exitCode -eq 0) { $lines.Add('Final verdict: PASS (audit scope only; public exposure not authorized).') }
    else { $lines.Add('Final verdict: FAIL; no automatic approval of image reuse or public exposure.') }
    if ($reportSafe) {
        try {
            [IO.File]::WriteAllLines($report, $lines, [Text.UTF8Encoding]::new($false))
        } catch {
            $reportSafe = $false
            $exitCode = 1
            Write-Output 'Failure stage: report-write; Error category: report-io; Verdict: FAIL'
        }
    } else {
        Write-Output 'FAIL: unsafe report destination; no report was written.'
    }
}
if ($reportSafe) { Write-Output 'Audit report written to deploy/quick-client-demo/image-audit-report.txt. Reuse remains blocked; review report.' }
exit $exitCode
