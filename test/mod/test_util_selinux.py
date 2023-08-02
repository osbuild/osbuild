#
# Tests for the 'osbuild.util.selinux' module.
#

import errno
import io
from unittest import mock

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
    assert "SELINUX" in cfg
    assert "SELINUXTYPE" in cfg
    assert cfg["SELINUX"] == "enforcing"
    assert cfg["SELINUXTYPE"] == "targeted"

    policy = selinux.config_get_policy(cfg)
    assert policy == "targeted"


def test_setfilecon():
    with mock.patch("os.setxattr") as setxattr:

        selinux.setfilecon("/path", "context")
        setxattr.assert_called_once_with("/path", selinux.XATTR_NAME_SELINUX, b"context", follow_symlinks=True)

    with mock.patch("os.getxattr") as getxattr:
        with mock.patch("os.setxattr") as setxattr:

            def raise_error(*_args, **_kwargs):
                raise OSError(errno.ENOTSUP, "Not supported")

            getxattr.return_value = b"context"
            setxattr.side_effect = raise_error

            selinux.setfilecon("path", "context")
