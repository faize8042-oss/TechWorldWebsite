"""Source checks for the proposed production publishing volume boundary."""
from pathlib import Path
import re
import unittest


class ProductionPublishingStorageTests(unittest.TestCase):
    def test_private_volume_is_persistent_and_not_exposed_by_nginx(self):
        source = (Path(__file__).resolve().parents[1] / 'deploy/compose.production.yaml').read_text()
        services = dict(re.findall(r'^  ([a-z][a-z0-9_-]*):\n(.*?)(?=^  [a-z][a-z0-9_-]*:|^volumes:)', source, re.M | re.S))
        self.assertIn('private_publishing:/app/private_publishing', services['web'])
        self.assertNotIn('private_publishing', services['nginx'])
        init = services['publishing-storage-init']
        for requirement in ('profiles: [operator]', 'network_mode: none', 'cap_drop: [ALL]',
                            'cap_add: [CHOWN]', '0o700', '10001, 10002'):
            self.assertIn(requirement, init)
        self.assertNotIn('secrets:', init)
        self.assertIn('  private_publishing:', source.split('\nvolumes:\n')[1])


if __name__ == '__main__':
    unittest.main()
