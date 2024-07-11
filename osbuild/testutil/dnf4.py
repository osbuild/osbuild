import tempfile
from typing import List, Optional

import dnf


def depsolve_pkgset(
    repo_paths: List[str],
    pkg_include: List[str],
    pkg_exclude: Optional[List[str]] = None
) -> List[dnf.package.Package]:
    """
    Perform a dependency resolution on a set of local RPM repositories.
    """

    with tempfile.TemporaryDirectory() as tempdir:
        conf = dnf.conf.Conf()
        conf.config_file_path = "/dev/null"
        conf.persistdir = f"{tempdir}{conf.persistdir}"
        conf.cachedir = f"{tempdir}{conf.cachedir}"
        conf.reposdir = ["/dev/null"]
        conf.pluginconfpath = ["/dev/null"]
        conf.varsdir = ["/dev/null"]

        base = dnf.Base(conf)

        for idx, repo_path in enumerate(repo_paths):
            repo = dnf.repo.Repo(f"repo{idx}", conf)
            repo.baseurl = f"file://{repo_path}"
            base.repos.add(repo)

        base.fill_sack(load_system_repo=False)

        base.install_specs(pkg_include, pkg_exclude)
        base.resolve()
        return base.transaction.install_set
