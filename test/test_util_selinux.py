import io
import unittest
import subprocess

from osbuild.util import selinux


class TestObjectStore(unittest.TestCase):

    def test_selinux_config(self):
        f = io.StringIO()
        cfg = selinux.parse_config(f)
        self.assertIsNotNone(cfg)
        policy = selinux.config_get_policy(cfg)
        self.assertIsNone(policy)

        example_good = """
        # This file controls the state of SELinux on the system.
        # SELINUX= can take one of these three values:
        #     enforcing - SELinux security policy is enforced.
        #     permissive - SELinux prints warnings instead of enforcing.
        #     disabled - No SELinux policy is loaded.
        SELINUX=enforcing
        # SELINUXTYPE= can take one of these three values:
        #     targeted - Targeted processes are protected,
        #     minimum - Modification of targeted policy.
        #     mls - Multi Level Security protection.
        SELINUXTYPE=targeted
        """

        f = io.StringIO(example_good)
        cfg = selinux.parse_config(f)
        self.assertIn('SELINUX', cfg)
        self.assertIn('SELINUXTYPE', cfg)
        self.assertEqual(cfg['SELINUX'], 'enforcing')
        self.assertEqual(cfg['SELINUXTYPE'], 'targeted')

        policy = selinux.config_get_policy(cfg)
        self.assertEqual(policy, 'targeted')


if __name__ == "__main__":
    unittest.main()
