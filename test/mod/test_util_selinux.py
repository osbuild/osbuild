#
# Tests for the 'osbuild.util.selinux' module.
#

import io

from osbuild.util import selinux


def test_selinux_config():
    f = io.StringIO()
    cfg = selinux.parse_config(f)
    assert cfg is not None
    policy = selinux.config_get_policy(cfg)
    assert policy is None

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
    assert 'SELINUX' in cfg
    assert 'SELINUXTYPE' in cfg
    assert cfg['SELINUX'] == 'enforcing'
    assert cfg['SELINUXTYPE'] == 'targeted'

    policy = selinux.config_get_policy(cfg)
    assert policy == 'targeted'
