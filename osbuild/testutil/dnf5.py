import tempfile
from typing import Dict, List, Tuple

import libdnf5
from libdnf5.base import GoalProblem_NO_PROBLEM as NO_PROBLEM


def depsolve_pkgset(
    repo_servers: List[Dict[str, str]],
    pkg_include: List[str]
) -> Tuple[libdnf5.base.Base, List[libdnf5.rpm.Package]]:
    """
    Perform a dependency resolution on a set of local RPM repositories.
    """

    with tempfile.TemporaryDirectory() as tempdir:
        base = libdnf5.base.Base()
        conf = base.get_config()
        conf.config_file_path = "/dev/null"
        conf.persistdir = f"{tempdir}{conf.persistdir}"
        conf.cachedir = f"{tempdir}{conf.cachedir}"
        conf.reposdir = ["/dev/null"]
        conf.pluginconfpath = "/dev/null"
        conf.varsdir = ["/dev/null"]

        sack = base.get_repo_sack()
        for repo_server in repo_servers:
            repo = sack.create_repo(repo_server["name"])
            conf = repo.get_config()
            conf.baseurl = repo_server["address"]

        base.setup()
        sack.load_repos(libdnf5.repo.Repo.Type_AVAILABLE)

        goal = libdnf5.base.Goal(base)
        for pkg in pkg_include:
            goal.add_install(pkg)
        transaction = goal.resolve()

        transaction_problems = transaction.get_problems()
        if transaction_problems != NO_PROBLEM:
            raise RuntimeError(f"transaction problems: {transaction.get_resolve_logs_as_strings()}")

        pkgs = []
        for tsi in transaction.get_transaction_packages():
            pkgs.append(tsi.get_package())

        # NB: return the base object as well, to workaround a bug in libdnf5:
        # https://github.com/rpm-software-management/dnf5/issues/1748
        return base, pkgs
