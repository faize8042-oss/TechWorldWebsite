"""Execute the exact generated probe against synthetic Linux procfs metadata."""
import contextlib
import io
from pathlib import Path
import re
import stat
from types import SimpleNamespace
from unittest.mock import patch

source = Path(__file__).with_name('validate-c6-1.ps1').read_text()
probe = re.search(r'Write-Utf8 "\$stage/validation_probe.py" @\x27\n(.*?)\n\x27@', source, re.S).group(1)
compile(probe, 'validation_probe.py', 'exec')


def run_probe(listeners=(), owned=(), bad_mode=False, denied=False, unstable=False):
    def metadata(path):
        directory = path == '/run/codeventra'
        return SimpleNamespace(st_uid=10001, st_gid=10002,
            st_mode=(stat.S_IFDIR | 0o2750) if directory else
                    (stat.S_IFSOCK | (0o666 if bad_mode else 0o660)))

    reads = 0
    def table(path):
        nonlocal reads
        reads += 1
        rows = 'header\n'
        for version, uid, inode in listeners:
            if path == ('/proc/net/tcp' if version == 4 else '/proc/net/tcp6'):
                rows += f'0: 0B00007F:8511 00000000:0000 0A 0:0 0:0 0 {uid} 0 {inode}\n'
        if unstable and reads > 2:
            rows = 'header\n'
        return io.StringIO(rows)

    @contextlib.contextmanager
    def descriptors(path):
        if denied:
            raise PermissionError(13, 'sensitive text must not appear')
        yield [SimpleNamespace(path=str(inode)) for inode in owned]

    output = io.StringIO()
    failed = False
    with patch.dict('os.environ', {'SOCKET_CHECK': '1'}, clear=True), \
         patch('os.stat', side_effect=metadata), \
         patch('os.getuid', return_value=10001, create=True), \
         patch('os.getgid', return_value=10002, create=True), \
         patch('os.listdir', return_value=['1', '12', 'net']), \
         patch('os.scandir', side_effect=descriptors), \
         patch('os.readlink', side_effect=lambda path: f'socket:[{path}]'), \
         patch('builtins.open', side_effect=table), contextlib.redirect_stdout(output):
        try:
            exec(probe, {})
        except (AssertionError, OSError):
            failed = True
    assert 'sensitive' not in output.getvalue()
    return failed, output.getvalue()


cases = [
    ('Gunicorn Unix only', {}, False),
    ('Gunicorn TCP IPv4', dict(listeners=[(4, 10001, 42)], owned=[42]), True),
    ('Gunicorn TCP IPv6', dict(listeners=[(6, 10001, 42)], owned=[42]), True),
    ('inherited root TCP socket', dict(listeners=[(4, 0, 42)], owned=[42]), True),
    ('unrelated namespace DNS listener', dict(listeners=[(4, 0, 42)]), False),
    ('unattributed app socket', dict(listeners=[(4, 10001, 42)]), True),
    ('unknown inode', dict(listeners=[(4, 0, 0)]), True),
    ('unreadable process descriptors', dict(listeners=[(4, 0, 42)], denied=True), True),
    ('racing socket table', dict(listeners=[(4, 0, 42)], unstable=True), True),
    ('unsafe Unix mode', dict(bad_mode=True), True),
]
for name, kwargs, expected in cases:
    failed, output = run_probe(**kwargs)
    assert failed == expected, (name, output)
    assert ('C61_FAIL' if expected else 'PASS socket metadata') in output, (name, output)
    print('PASS', name)
