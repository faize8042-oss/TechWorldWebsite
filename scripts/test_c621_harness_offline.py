"""Offline harness contracts and fault injection. No Docker or DB calls allowed."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('c621_harness', ROOT / 'scripts/c621/harness.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class FakeDocker:
    instances = []
    fail_phase = False
    wrong_owner = False
    cleanup_fail = False
    fail_create = False
    timeout_create = False
    unsafe_image = False

    def __init__(self, deadline, directory):
        self.directory = directory
        self.calls = []
        self.resources = {}
        self.manifest = None
        self.__class__.instances.append(self)

    def call(self, args, stdin=None, check=True, cleanup=False):
        self.calls.append((args, stdin, cleanup))
        code, output = 0, ''
        if args[:2] == ['image', 'inspect']:
            output = json.dumps([{'Config': {'Env': ['PGDATA=/var/lib/postgresql/data'], 'Volumes': {'/unexpected': {}} if self.unsafe_image else {}}}])
        elif args[0] == 'compose':
            self.manifest = json.loads((self.directory / 'compose.json').read_text())
            run = self.manifest['name'].removeprefix('cv-c621-')
            labels = {h.LABEL: run, 'com.docker.compose.project': self.manifest['name']}
            network = self.manifest['networks']['isolated']['name']
            for service in self.manifest['services'].values():
                self.resources[service['container_name']] = {
                    'Id': format(len(self.resources) + 1, '064x'), 'Config': {'Labels': labels}, 'HostConfig': {'PortBindings': {}},
                    'NetworkSettings': {'Networks': {network: {}}}, 'Mounts': []}
            self.resources[network] = {'Id': 'f' * 64, 'Labels': labels, 'Internal': True}
            if self.timeout_create:
                raise subprocess.TimeoutExpired('compose', 60)
            if self.fail_create:
                raise RuntimeError('Partial create failure')
        elif len(args) > 1 and args[1] == 'inspect' and args[0] in ('container', 'network'):
            item = copy.deepcopy(self.resources.get(args[2]) or next((v for v in self.resources.values() if v['Id'] == args[2]), None))
            if item:
                if self.wrong_owner and cleanup:
                    (item.get('Config', item))['Labels'][h.LABEL] = 'foreign'
                output = json.dumps([item])
            else:
                code = 1
        elif len(args) > 1 and args[1] == 'rm':
            if self.cleanup_fail:
                raise RuntimeError('synthetic secret marker must be suppressed')
            for name, item in list(self.resources.items()):
                if item['Id'] == args[-1]:
                    del self.resources[name]
        elif len(args) > 1 and args[1] == 'ls':
            if '-q' in args:
                output = '\n'.join(v['Id'] for v in self.resources.values() if (args[0] == 'network') == ('Internal' in v)) if args[0] != 'volume' else ''
        elif args[0] == 'exec':
            if 'psql' in args and stdin and ('SELECT 1/0' in stdin or 'CREATE ROLE cv_owner' in stdin and sum('psql' in c[0] and c[1] and 'CREATE ROLE cv_owner' in c[1] for c in self.calls) > 1):
                code = 1
            if self.fail_phase and args[-1] == 'web' and args[-2] != 'seed':
                raise RuntimeError('synthetic secret marker must be suppressed')
        if check and code:
            raise RuntimeError('mocked operation failed')
        return subprocess.CompletedProcess(args, code, output, '')


class HarnessTests(unittest.TestCase):
    def setUp(self):
        FakeDocker.instances.clear()
        FakeDocker.timeout_create = False
        FakeDocker.fail_phase = FakeDocker.wrong_owner = FakeDocker.cleanup_fail = FakeDocker.fail_create = FakeDocker.unsafe_image = False
        self.run = 'a' * 32
        self.source = ROOT / 'synthetic-test-placeholder'
        self.plan = h.plan(self.run, 'postgres:17', 'python:3.12', self.source)

    def test_preflight_never_invokes_process(self):
        with patch.object(subprocess, 'run', side_effect=AssertionError('process forbidden')):
            files = h.preflight()
        self.assertTrue(files)
        self.assertFalse(any('.env' in p.parts or 'validation-results' in p.parts or 'uploads' in p.parts for p in files))

    def test_unique_runs_and_exact_names(self):
        import uuid
        plans = [h.plan(uuid.uuid4().hex, 'postgres:17', 'python:3.12', self.source) for _ in range(20)]
        self.assertEqual(len({p['name'] for p in plans}), 20)
        for value in plans:
            self.assertTrue(value['networks']['isolated']['internal'])
            for service in value['services'].values():
                self.assertEqual(service['networks'], ['isolated'])
                self.assertNotIn('ports', service)
                self.assertNotIn('env_file', service)
            self.assertNotIn('volumes', value)

    def test_manifest_mutations_fail_closed(self):
        mutations = [lambda p: p['services']['db'].update(ports=['5432:5432']),
                     lambda p: p['networks']['isolated'].update(external=True),
                     lambda p: p['networks']['isolated'].update(internal=False),
                     lambda p: p['services']['web'].update(env_file=['.env']),
                     lambda p: p['services']['web'].update(network_mode='host'),
                     lambda p: p['services']['web'].update(privileged=True),
                     lambda p: p['services']['db'].update(volumes=['existing:/data']),
                     lambda p: p['services']['web']['labels'].update({h.LABEL: 'foreign'}),
                     lambda p: p.update(volumes={'existing': {'external': True}})]
        for mutate in mutations:
            value = copy.deepcopy(self.plan)
            mutate(value)
            with self.assertRaises(ValueError):
                h.validate_plan(value, self.run, self.source)

    def args(self):
        return argparse.Namespace(approval=h.APPROVAL, timeout=60,
            postgres_image='postgres:17@sha256:' + '1' * 64,
            python_image='approved-python@sha256:' + '2' * 64)

    def test_execution_gates_before_docker(self):
        for field, value in [('approval', ''), ('postgres_image', 'postgres:17'),
                             ('python_image', 'python:latest'),
                             ('postgres_image', 'postgres:16@sha256:' + '1' * 64)]:
            args = self.args()
            setattr(args, field, value)
            with patch.object(h, 'Docker', side_effect=AssertionError('Docker forbidden')):
                with self.assertRaises(ValueError):
                    h.execute(args, [])

    def exercise(self, fault=None):
        if fault:
            setattr(FakeDocker, fault, True)
        with tempfile.TemporaryDirectory(prefix='c621-offline-') as base:
            target = Path(base) / 'run'
            target.mkdir()
            with patch.object(h, 'Docker', FakeDocker), patch.object(h.tempfile, 'mkdtemp', return_value=str(target)), patch.object(h.time, 'sleep'):
                code = h.execute(self.args(), h.preflight())
            status = json.loads((target / 'status.json').read_text())
            self.assertNotIn('synthetic secret marker', json.dumps(status))
            return code, status, FakeDocker.instances[-1]

    def test_success_cleans_exact_resources_without_global_commands(self):
        code, status, fake = self.exercise()
        self.assertEqual(code, 0)
        self.assertEqual(status['cleanup'], 'PASS')
        self.assertFalse(fake.resources)
        for args, stdin, cleanup in fake.calls:
            self.assertNotIn('prune', args)
            self.assertNotIn('down', args)
            self.assertNotIn('build', args)
            if len(args) > 1 and args[1] == 'rm':
                self.assertRegex(args[-1], r'^[0-9a-f]{64}$')
            self.assertNotIn('cv_runtime:', ' '.join(args))

    def test_phase_failure_still_cleans_and_suppresses_details(self):
        code, status, fake = self.exercise('fail_phase')
        self.assertEqual(code, 1)
        self.assertEqual(status['validation'], 'FAIL')
        self.assertEqual(status['cleanup'], 'PASS')
        self.assertFalse(fake.resources)

    def test_unexpected_image_volume_refuses_creation(self):
        code, status, fake = self.exercise('unsafe_image')
        self.assertEqual(code, 1)
        self.assertFalse(fake.resources)
        self.assertFalse(any(a[0] == 'compose' for a, _, _ in fake.calls))

    def test_partial_create_failure_is_indeterminate(self):
        code, status, fake = self.exercise('fail_create')
        self.assertEqual(code, 1)
        self.assertEqual(status['cleanup'], 'INDETERMINATE')
        self.assertFalse(fake.resources)

    def test_creation_timeout_cannot_report_cleanup_pass(self):
        code, status, fake = self.exercise('timeout_create')
        self.assertEqual(code, 1)
        self.assertEqual(status['creation'], 'UNRESOLVED')
        self.assertEqual(status['cleanup'], 'INDETERMINATE')
        self.assertFalse(fake.resources)

    def test_deadline_prevents_subprocess(self):
        import time
        with tempfile.TemporaryDirectory(prefix='c621-deadline-') as base:
            client = h.Docker(time.monotonic() - 1, Path(base))
            with patch.object(subprocess, 'run', side_effect=AssertionError('process forbidden')):
                with self.assertRaises(RuntimeError):
                    client.call(['version'])

    def test_foreign_labels_refuse_cleanup(self):
        code, status, fake = self.exercise('wrong_owner')
        self.assertEqual(code, 1)
        self.assertEqual(status['cleanup'], 'FAIL_OPERATOR_ACTION_REQUIRED')
        self.assertTrue(fake.resources)
        self.assertFalse(any(len(a) > 1 and a[1] == 'rm' for a, _, _ in fake.calls))

    def test_cleanup_failure_is_not_retried_or_reported_success(self):
        code, status, fake = self.exercise('cleanup_fail')
        self.assertEqual(code, 1)
        self.assertEqual(status['cleanup'], 'FAIL_OPERATOR_ACTION_REQUIRED')
        removals = [tuple(a) for a, _, _ in fake.calls if len(a) > 1 and a[1] == 'rm']
        self.assertEqual(len(removals), len(set(removals)))

    def test_limits_on_every_service_and_tmpfs(self):
        for name, service in self.plan['services'].items():
            self.assertEqual(service['mem_limit'], '1536m' if name == 'db' else '768m')
            self.assertEqual(service['cpus'], 2.0 if name == 'db' else 1.0)
            self.assertEqual(service['pids_limit'], 256)
            for mount in service['tmpfs']:
                self.assertRegex(mount, r'size=\d+m')

    def test_replacement_name_never_becomes_deletion_target(self):
        identity = '1' * 64
        calls = []
        class Replacement:
            def call(_, args, **kwargs):
                calls.append(args)
                if args[1] == 'ls':
                    value = identity if args[0] == 'container' and len(calls) == 1 else ''
                elif args[1] == 'inspect':
                    # The name now points at a foreign replacement; ID inspection
                    # continues to identify only the original owned object.
                    value = json.dumps([{'Id': identity, 'Name': '/reused-name',
                        'Config': {'Labels': {h.LABEL: self.run,
                        'com.docker.compose.project': self.plan['name']}}}])
                else:
                    value = ''
                return subprocess.CompletedProcess(args, 0, value, '')
        with patch.object(h.time, 'sleep'):
            self.assertEqual(h.reconcile(Replacement(), self.run, self.plan['name'], 'COMPLETED', {}), 'PASS')
        self.assertEqual([a[-1] for a in calls if a[1] == 'rm'], [identity])

    def test_changed_missing_and_ambiguous_ids_fail_closed(self):
        for items in ([], [{ 'Id': '2' * 64}], [{ 'Id': '1' * 64}] * 2):
            adapter = unittest.mock.Mock()
            adapter.call.return_value = subprocess.CompletedProcess([], 0, json.dumps(items), '')
            with self.assertRaises(ValueError):
                h.verified_resource(adapter, 'container', '1' * 64, self.run, self.plan['name'])

    def test_delayed_creation_after_initial_empty_round_never_proves_quiescence(self):
        identity = '3' * 64
        removed = []
        rounds = 0
        class Delayed:
            def call(_, args, **kwargs):
                nonlocal rounds
                output = ''
                if args[:2] == ['container', 'ls']:
                    rounds += 1
                    if rounds in (2, 5):
                        output = identity if rounds == 2 else '4' * 64
                elif args[1] == 'inspect':
                    output = json.dumps([{'Id': args[2], 'Config': {'Labels': {
                        h.LABEL: self.run, 'com.docker.compose.project': self.plan['name']}}}])
                elif args[1] == 'rm':
                    removed.append(args[-1])
                return subprocess.CompletedProcess(args, 0, output, '')
        diagnostics = {}
        with patch.object(h.time, 'sleep'):
            result = h.reconcile(Delayed(), self.run, self.plan['name'], 'UNRESOLVED', diagnostics)
        self.assertEqual(result, 'INDETERMINATE')
        self.assertEqual(removed, [identity, '4' * 64])
        self.assertEqual(diagnostics['rounds'], 6)

    def test_ownership_change_on_second_inspection_blocks_removal(self):
        identity = '5' * 64
        inspections = 0
        calls = []
        class Changed:
            def call(_, args, **kwargs):
                nonlocal inspections
                calls.append(args)
                output = ''
                if args[:2] == ['container', 'ls']:
                    output = identity
                elif args[1] == 'inspect':
                    inspections += 1
                    output = json.dumps([{'Id': identity, 'Config': {'Labels': {
                        h.LABEL: self.run if inspections == 1 else 'foreign',
                        'com.docker.compose.project': self.plan['name']}}}])
                return subprocess.CompletedProcess(args, 0, output, '')
        with patch.object(h.time, 'sleep'):
            result = h.reconcile(Changed(), self.run, self.plan['name'], 'COMPLETED', {})
        self.assertEqual(result, 'FAIL_OPERATOR_ACTION_REQUIRED')
        self.assertFalse(any(a[1] == 'rm' for a in calls))

    def test_cli_timeout_is_reaped_but_not_daemon_completion(self):
        with tempfile.TemporaryDirectory() as base:
            import time
            client = h.Docker(time.monotonic() + 60, Path(base))
            with patch.object(subprocess, 'run', side_effect=subprocess.TimeoutExpired('suppressed', 1)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    client.call(['compose', 'up'])

    def test_clean_environment_ignores_all_service_and_context_inputs(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'private', 'DOCKER_HOST': 'remote',
                                    'COMPOSE_FILE': 'existing', 'PGPASSWORD': 'private',
                                    'PRODUCTION_RUNTIME_FILE': 'private'}, clear=True):
            self.assertEqual(h.clean_environment(), {})

    def test_ps_default_and_confirmation_contract(self):
        source = (ROOT / 'scripts/validate-c6-2-1.ps1').read_text()
        self.assertIn('if ($ExecuteIsolatedValidation)', source)
        self.assertIn('Parser]::ParseFile', source)
        self.assertIn(h.APPROVAL, source)
        self.assertNotIn('docker ', source.lower())


if __name__ == '__main__':
    unittest.main()
