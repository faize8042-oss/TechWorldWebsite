"""Offline regression checks for secret-safe failure reporting."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.publishing_test_runner import SafeResult, error_kind


class DiagnosticTests(unittest.TestCase):
    def test_regression_command_accepts_runner_option_and_preserves_labels(self):
        # Exercise Django's real command parser, stopping before database setup.
        code = '''
from django.conf import settings
settings.configure(SECRET_KEY='synthetic', INSTALLED_APPS=[])
import django
django.setup()
from unittest.mock import patch
from scripts.publishing_verify import run_regression_suite
with patch('scripts.publishing_test_runner.VerificationRunner.run_tests', return_value=0) as run:
    run_regression_suite()
    run.assert_called_once_with(('config', 'core', 'projects', 'contact', 'analytics', 'blog', 'news', 'publishing'))
'''
        result = subprocess.run([sys.executable, '-B', '-c', code],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True)
        self.assertEqual(result.returncode, 0, 'Django rejected the regression command or its app labels')

    def test_database_error_reports_state_without_message(self):
        cause = RuntimeError('synthetic-password-do-not-print')
        cause.sqlstate = '42501'
        error = ValueError('synthetic-url-do-not-print')
        error.__cause__ = cause
        self.assertEqual(error_kind(error), 'ValueError SQLSTATE=42501')
        cause.sqlstate = 'synthetic-password-do-not-print'
        self.assertEqual(error_kind(error), 'ValueError')

    def test_failed_test_diagnostic_omits_assertion_values(self):
        result = SafeResult(io.StringIO(), True, 1)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                raise AssertionError('synthetic-password-do-not-print')
            except AssertionError:
                result.addFailure(self, sys.exc_info())
        self.assertEqual(output.getvalue(), 'INFO: test-failure exception=AssertionError\n')
        self.assertEqual(len(result.failures), 1)


if __name__ == '__main__':
    unittest.main()
