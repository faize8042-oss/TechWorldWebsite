"""Django test diagnostics that never include exception messages or test data."""
import re
import unittest

from django.test.runner import DiscoverRunner


def error_kind(error):
    kind = type(error).__name__
    cause = error
    seen = set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        state = getattr(cause, 'sqlstate', None) or getattr(cause, 'pgcode', None)
        if isinstance(state, str) and re.fullmatch(r'[A-Z0-9]{5}', state):
            return kind + ' SQLSTATE=' + state
        cause = cause.__cause__
    return kind


class SafeResult(unittest.TextTestResult):
    def addError(self, test, err):
        print('INFO: test-error exception=' + error_kind(err[1]))
        super().addError(test, err)

    def addFailure(self, test, err):
        print('INFO: test-failure exception=' + error_kind(err[1]))
        super().addFailure(test, err)


class VerificationRunner(DiscoverRunner):
    def get_resultclass(self):
        return SafeResult

    def setup_databases(self, **kwargs):
        print('INFO: test-stage=create-and-migrate-isolated-database')
        return super().setup_databases(**kwargs)

    def teardown_databases(self, old_config, **kwargs):
        print('INFO: test-stage=destroy-isolated-database')
        return super().teardown_databases(old_config, **kwargs)
