"""Repository contracts only: no application imports, Docker or service access."""
import ast
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / 'deploy/c621-validation'
spec = importlib.util.spec_from_file_location('image_harness', ROOT / 'scripts/c621/harness.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class ValidationImageTests(unittest.TestCase):
    def test_base_and_install_are_fail_closed(self):
        dockerfile = (CONTEXT / 'Dockerfile').read_text()
        bases = [line.split()[1] for line in dockerfile.splitlines() if line.startswith('FROM ')]
        self.assertEqual(bases, ['python@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2'] * 2)
        for required in ('RUN --network=none', '--no-index', '--require-hashes',
                         '--only-binary=:all:', 'pip check', 'COPY requirements.lock',
                         'COPY wheelhouse/', 'USER 10001:10002', 'HOME=/tmp',
                         'TMPDIR=/tmp', 'PYTHONDONTWRITEBYTECODE=1'):
            self.assertIn(required, dockerfile)
        for forbidden in ('COPY . ', 'ADD ', 'VOLUME ', 'EXPOSE ', 'apt-get',
                          'manage.py', 'collectstatic', 'migrate --'):
            self.assertNotIn(forbidden, dockerfile)

    def test_context_uses_exact_allowlist(self):
        rules = [line for line in (CONTEXT / '.dockerignore').read_text().splitlines()
                 if line and not line.startswith('#')]
        self.assertEqual(rules, ['**', '!Dockerfile', '!.dockerignore',
                                 '!requirements.lock', '!wheelhouse/', '!wheelhouse/*.whl'])
        copies = [line for line in (CONTEXT / 'Dockerfile').read_text().splitlines()
                  if line.startswith('COPY ')]
        self.assertEqual(copies, ['COPY requirements.lock /inputs/requirements.lock',
                                 'COPY wheelhouse/ /inputs/wheelhouse/',
                                 'COPY --from=dependencies /opt/validation /opt/validation'])

    def test_actual_import_inventory_includes_nested_probe_imports(self):
        imports = set()
        for path in h.source_files():
            if path.suffix != '.py':
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imports.add(node.module.split('.')[0])
        self.assertTrue({'django', 'psycopg', 'environ', 'PIL', 'django_ratelimit'} <= imports)

    def test_harness_isolation_remains_exact(self):
        plan = h.plan('a' * 32, 'postgres:17', 'validation', ROOT / 'synthetic-source')
        h.validate_plan(plan, 'a' * 32, ROOT / 'synthetic-source')
        self.assertTrue(plan['networks']['isolated']['internal'])
        for name in ('web', 'migrate', 'audit'):
            service = plan['services'][name]
            self.assertEqual(service['user'], '10001:10002')
            self.assertTrue(service['read_only'])
            self.assertTrue(service['volumes'][0]['read_only'])
            self.assertEqual(service['networks'], ['isolated'])
            self.assertNotIn('ports', service)
            self.assertEqual(service['mem_limit'], '768m')
            self.assertEqual(service['pids_limit'], 256)
            self.assertTrue(all('size=' in mount for mount in service['tmpfs']))

    def test_mutable_tag_and_bare_image_id_rejected_before_docker(self):
        import argparse
        for image in ('validation:reviewed', 'sha256:' + 'a' * 64):
            args = argparse.Namespace(approval=h.APPROVAL,
                postgres_image='postgres:17@sha256:' + 'b' * 64,
                python_image=image, timeout=60)
            with patch.object(h, 'Docker', side_effect=AssertionError('Docker forbidden')):
                with self.assertRaises(ValueError):
                    h.execute(args, [])

    def test_repository_digest_passes_syntax_gate_without_daemon(self):
        import argparse
        args = argparse.Namespace(approval=h.APPROVAL,
            postgres_image='postgres:17@sha256:' + 'b' * 64,
            python_image='local/codeventra-c621@sha256:' + 'a' * 64, timeout=60)
        # Stop before staging or Docker; this proves syntax acceptance only.
        with patch.object(h.tempfile, 'mkdtemp', side_effect=RuntimeError('offline boundary')):
            with self.assertRaisesRegex(RuntimeError, 'offline boundary'):
                h.execute(args, [])


if __name__ == '__main__':
    unittest.main()
