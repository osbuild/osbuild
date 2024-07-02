import os
import os.path
import tempfile
from datetime import datetime
from typing import List

import libdnf5 as dnf5
from libdnf5.base import GoalProblem_NO_PROBLEM as NO_PROBLEM
from libdnf5.common import QueryCmp_CONTAINS as CONTAINS
from libdnf5.common import QueryCmp_EQ as EQ
from libdnf5.common import QueryCmp_GLOB as GLOB

from osbuild.solver import DepsolveError, RepoError, SolverBase, modify_rootdir_path, read_keys


def remote_location(package, schemes=("http", "ftp", "file", "https")):
    """Return the remote url where a package rpm may be downloaded from

    This wraps the get_remote_location() function, returning the first
    result or if it cannot find a suitable url it raises a RuntimeError
    """
    urls = package.get_remote_locations(schemes)
    if not urls or len(urls) == 0:
        raise RuntimeError(f"Cannot determine remote location for {package.get_nevra()}")

    return urls[0]


def get_string_option(option):
    # option.get_value() causes an error if it's unset for string values, so check if it's empty first
    if option.empty():
        return None
    return option.get_value()


# XXX - Temporarily lifted from dnf.rpm module  # pylint: disable=fixme
def _invert(dct):
    return {v: k for k in dct for v in dct[k]}


class DNF5(SolverBase):
    """Solver implements package related actions

    These include depsolving a package set, searching for packages, and dumping a list
    of all available packages.
    """

    # pylint: disable=too-many-arguments
    def __init__(self, request, persistdir, cachedir):
        arch = request["arch"]
        releasever = request.get("releasever")
        module_platform_id = request["module_platform_id"]
        proxy = request.get("proxy")

        arguments = request["arguments"]
        repos = arguments.get("repos", [])
        root_dir = arguments.get("root_dir")

        # Gather up all the exclude packages from all the transactions
        exclude_pkgs = []
        # Return an empty list when 'transactions' key is missing or when it is None
        transactions = arguments.get("transactions") or []
        for t in transactions:
            # Return an empty list when 'exclude-specs' key is missing or when it is None
            exclude_pkgs.extend(t.get("exclude-specs") or [])

        if not exclude_pkgs:
            exclude_pkgs = []

        self.base = dnf5.base.Base()

        # Base is the correct place to set substitutions, not per-repo.
        # See https://github.com/rpm-software-management/dnf5/issues/1248
        self.base.get_vars().set("arch", arch)
        self.base.get_vars().set("basearch", self._BASEARCH_MAP[arch])
        if releasever:
            self.base.get_vars().set('releasever', releasever)
        if proxy:
            self.base.get_vars().set('proxy', proxy)

        # Enable fastestmirror to ensure we choose the fastest mirrors for
        # downloading metadata (when depsolving) and downloading packages.
        conf = self.base.get_config()
        conf.fastestmirror = True

        # Weak dependencies are installed for the 1st transaction
        # This is set to False for any subsequent ones in depsolve()
        conf.install_weak_deps = True

        # We use the same cachedir for multiple architectures. Unfortunately,
        # this is something that doesn't work well in certain situations
        # with zchunk:
        # Imagine that we already have cache for arch1. Then, we use dnf-json
        # to depsolve for arch2. If ZChunk is enabled and available (that's
        # the case for Fedora), dnf will try to download only differences
        # between arch1 and arch2 metadata. But, as these are completely
        # different, dnf must basically redownload everything.
        # For downloding deltas, zchunk uses HTTP range requests. Unfortunately,
        # if the mirror doesn't support multi range requests, then zchunk will
        # download one small segment per a request. Because we need to update
        # the whole metadata (10s of MB), this can be extremely slow in some cases.
        # I think that we can come up with a better fix but let's just disable
        # zchunk for now. As we are already downloading a lot of data when
        # building images, I don't care if we download even more.
        conf.zchunk = False

        # Set the rest of the dnf configuration.
        conf.module_platform_id = module_platform_id
        conf.config_file_path = "/dev/null"
        conf.persistdir = persistdir
        conf.cachedir = cachedir

        # Include comps metadata by default
        metadata_types = ['comps']
        metadata_types.extend(arguments.get("optional-metadata", []))
        conf.optional_metadata_types = metadata_types

        try:
            # NOTE: With libdnf5 packages are excluded in the repo setup
            for repo in repos:
                self._dnfrepo(repo, exclude_pkgs)

            if root_dir:
                # This sets the varsdir to ("{root_dir}/usr/share/dnf5/vars.d/", "{root_dir}/etc/dnf/vars/") for custom
                # variable substitution (e.g. CentOS Stream 9's $stream variable)
                conf.installroot = root_dir
                conf.varsdir = (os.path.join(root_dir, "etc/dnf/vars"), os.path.join(root_dir, "usr/share/dnf5/vars.d"))

            # Cannot modify .conf() values after this
            # base.setup() should be called before loading repositories otherwise substitutions might not work.
            self.base.setup()

            if root_dir:
                repos_dir = os.path.join(root_dir, "etc/yum.repos.d")
                self.base.get_repo_sack().create_repos_from_dir(repos_dir)
                rq = dnf5.repo.RepoQuery(self.base)
                rq.filter_enabled(True)
                repo_iter = rq.begin()
                while repo_iter != rq.end():
                    repo = repo_iter.value()
                    config = repo.get_config()
                    config.sslcacert = modify_rootdir_path(
                        get_string_option(config.get_sslcacert_option()),
                        root_dir,
                    )
                    config.sslclientcert = modify_rootdir_path(
                        get_string_option(config.get_sslclientcert_option()),
                        root_dir,
                    )
                    config.sslclientkey = modify_rootdir_path(
                        get_string_option(config.get_sslclientkey_option()),
                        root_dir,
                    )
                    repo_iter.next()

            self.base.get_repo_sack().update_and_load_enabled_repos(load_system=False)
        except RuntimeError as e:
            raise RepoError(e) from e

    _BASEARCH_MAP = _invert({
        'aarch64': ('aarch64',),
        'alpha': ('alpha', 'alphaev4', 'alphaev45', 'alphaev5', 'alphaev56',
                  'alphaev6', 'alphaev67', 'alphaev68', 'alphaev7', 'alphapca56'),
        'arm': ('armv5tejl', 'armv5tel', 'armv5tl', 'armv6l', 'armv7l', 'armv8l'),
        'armhfp': ('armv6hl', 'armv7hl', 'armv7hnl', 'armv8hl'),
        'i386': ('i386', 'athlon', 'geode', 'i386', 'i486', 'i586', 'i686'),
        'ia64': ('ia64',),
        'mips': ('mips',),
        'mipsel': ('mipsel',),
        'mips64': ('mips64',),
        'mips64el': ('mips64el',),
        'loongarch64': ('loongarch64',),
        'noarch': ('noarch',),
        'ppc': ('ppc',),
        'ppc64': ('ppc64', 'ppc64iseries', 'ppc64p7', 'ppc64pseries'),
        'ppc64le': ('ppc64le',),
        'riscv32': ('riscv32',),
        'riscv64': ('riscv64',),
        'riscv128': ('riscv128',),
        's390': ('s390',),
        's390x': ('s390x',),
        'sh3': ('sh3',),
        'sh4': ('sh4', 'sh4a'),
        'sparc': ('sparc', 'sparc64', 'sparc64v', 'sparcv8', 'sparcv9',
                  'sparcv9v'),
        'x86_64': ('x86_64', 'amd64', 'ia32e'),
    })

    # pylint: disable=too-many-branches
    def _dnfrepo(self, desc, exclude_pkgs=None):
        """Makes a dnf.repo.Repo out of a JSON repository description"""
        if not exclude_pkgs:
            exclude_pkgs = []

        sack = self.base.get_repo_sack()

        repo = sack.create_repo(desc["id"])
        conf = repo.get_config()

        if "name" in desc:
            conf.name = desc["name"]

        # At least one is required
        if "baseurl" in desc:
            conf.baseurl = desc["baseurl"]
        elif "metalink" in desc:
            conf.metalink = desc["metalink"]
        elif "mirrorlist" in desc:
            conf.mirrorlist = desc["mirrorlist"]
        else:
            raise ValueError("missing either `baseurl`, `metalink`, or `mirrorlist` in repo")

        conf.sslverify = desc.get("sslverify", True)
        if "sslcacert" in desc:
            conf.sslcacert = desc["sslcacert"]
        if "sslclientkey" in desc:
            conf.sslclientkey = desc["sslclientkey"]
        if "sslclientcert" in desc:
            conf.sslclientcert = desc["sslclientcert"]

        if "gpgcheck" in desc:
            conf.gpgcheck = desc["gpgcheck"]
        if "repo_gpgcheck" in desc:
            conf.repo_gpgcheck = desc["repo_gpgcheck"]
        if "gpgkey" in desc:
            conf.gpgkey = [desc["gpgkey"]]
        if "gpgkeys" in desc:
            # gpgkeys can contain a full key, or it can be a URL
            # dnf expects urls, so write the key to a temporary location and add the file://
            # path to conf.gpgkey
            keydir = os.path.join(self.base.get_config().persistdir, "gpgkeys")
            if not os.path.exists(keydir):
                os.makedirs(keydir, mode=0o700, exist_ok=True)

            for key in desc["gpgkeys"]:
                if key.startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----"):
                    # Not using with because it needs to be a valid file for the duration. It
                    # is inside the temporary persistdir so will be cleaned up on exit.
                    # pylint: disable=consider-using-with
                    keyfile = tempfile.NamedTemporaryFile(dir=keydir, delete=False)
                    keyfile.write(key.encode("utf-8"))
                    conf.gpgkey += (f"file://{keyfile.name}",)
                    keyfile.close()
                else:
                    conf.gpgkey += (key,)

        # In dnf, the default metadata expiration time is 48 hours. However,
        # some repositories never expire the metadata, and others expire it much
        # sooner than that. We therefore allow this to be configured. If nothing
        # is provided we error on the side of checking if we should invalidate
        # the cache. If cache invalidation is not necessary, the overhead of
        # checking is in the hundreds of milliseconds. In order to avoid this
        # overhead accumulating for API calls that consist of several dnf calls,
        # we set the expiration to a short time period, rather than 0.
        conf.metadata_expire = desc.get("metadata_expire", "20s")

        # This option if True disables modularization filtering. Effectively
        # disabling modularity for given repository.
        if "module_hotfixes" in desc:
            repo.module_hotfixes = desc["module_hotfixes"]

        # Set the packages to exclude
        conf.excludepkgs = exclude_pkgs

        return repo

    @staticmethod
    def _timestamp_to_rfc3339(timestamp):
        return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%dT%H:%M:%SZ')

    def dump(self):
        """dump returns a list of all available packages"""
        packages = []
        q = dnf5.rpm.PackageQuery(self.base)
        q.filter_available()
        for package in list(q):
            packages.append({
                "name": package.get_name(),
                "summary": package.get_summary(),
                "description": package.get_description(),
                "url": package.get_url(),
                "repo_id": package.get_repo_id(),
                "epoch": int(package.get_epoch()),
                "version": package.get_version(),
                "release": package.get_release(),
                "arch": package.get_arch(),
                "buildtime": self._timestamp_to_rfc3339(package.get_build_time()),
                "license": package.get_license()
            })
        return packages

    def search(self, args):
        """ Perform a search on the available packages

        args contains a "search" dict with parameters to use for searching.
        "packages" list of package name globs to search for
        "latest" is a boolean that will return only the latest NEVRA instead
        of all matching builds in the metadata.

        eg.

            "search": {
                "latest": false,
                "packages": ["tmux", "vim*", "*ssh*"]
            },
        """
        pkg_globs = args.get("packages", [])

        packages = []

        # NOTE: Build query one piece at a time, don't pass all to filterm at the same
        # time.
        for name in pkg_globs:
            q = dnf5.rpm.PackageQuery(self.base)
            q.filter_available()

            # If the package name glob has * in it, use glob.
            # If it has *name* use substr
            # If it has neither use exact match
            if "*" in name:
                if name[0] != "*" or name[-1] != "*":
                    q.filter_name([name], GLOB)
                else:
                    q.filter_name([name.replace("*", "")], CONTAINS)
            else:
                q.filter_name([name], EQ)

            if args.get("latest", False):
                q.filter_latest_evr()

            for package in list(q):
                packages.append({
                    "name": package.get_name(),
                    "summary": package.get_summary(),
                    "description": package.get_description(),
                    "url": package.get_url(),
                    "repo_id": package.get_repo_id(),
                    "epoch": int(package.get_epoch()),
                    "version": package.get_version(),
                    "release": package.get_release(),
                    "arch": package.get_arch(),
                    "buildtime": self._timestamp_to_rfc3339(package.get_build_time()),
                    "license": package.get_license()
                })
        return packages

    def depsolve(self, arguments):
        """depsolve returns a list of the dependencies for the set of transactions
        """
        # Return an empty list when 'transactions' key is missing or when it is None
        transactions = arguments.get("transactions") or []
        # collect repo IDs from the request so we know whether to translate gpg key paths
        request_repo_ids = set(repo["id"] for repo in arguments.get("repos", []))
        root_dir = arguments.get("root_dir")
        last_transaction: List = []

        for transaction in transactions:
            goal = dnf5.base.Goal(self.base)
            goal.reset()
            sack = self.base.get_rpm_package_sack()
            sack.clear_user_excludes()

            # weak deps are selected per-transaction
            self.base.get_config().install_weak_deps = transaction.get("install_weak_deps", False)

            # set the packages from the last transaction as installed
            for installed_pkg in last_transaction:
                goal.add_rpm_install(installed_pkg)

            # Support group/environment names as well as ids
            settings = dnf5.base.GoalJobSettings()
            settings.group_with_name = True

            # Packages are added individually, excludes are handled in the repo setup
            for pkg in transaction.get("package-specs"):
                goal.add_install(pkg, settings)
            transaction = goal.resolve()
            if transaction.get_problems() != NO_PROBLEM:
                raise DepsolveError("\n".join(transaction.get_resolve_logs_as_strings()))

            # store the current transaction result
            last_transaction.clear()
            for tsi in transaction.get_transaction_packages():
                # Only add packages being installed, upgraded, downgraded, or reinstalled
                if not dnf5.base.transaction.transaction_item_action_is_inbound(tsi.get_action()):
                    continue
                last_transaction.append(tsi.get_package())

        # Something went wrong, but no error was generated by goal.resolve()
        if len(transactions) > 0 and len(last_transaction) == 0:
            raise DepsolveError("Empty transaction results")

        packages = []
        pkg_repos = {}
        for package in last_transaction:
            packages.append({
                "name": package.get_name(),
                "epoch": int(package.get_epoch()),
                "version": package.get_version(),
                "release": package.get_release(),
                "arch": package.get_arch(),
                "repo_id": package.get_repo_id(),
                "path": package.get_location(),
                "remote_location": remote_location(package),
                "checksum": f"{package.get_checksum().get_type_str()}:{package.get_checksum().get_checksum()}",
            })
            # collect repository objects by id to create the 'repositories' collection for the response
            pkg_repo = package.get_repo()
            pkg_repos[pkg_repo.get_id()] = pkg_repo

        packages = sorted(packages, key=lambda x: x["path"])

        repositories = {}  # full repository configs for the response
        for repo in pkg_repos.values():
            repo_cfg = repo.get_config()
            repositories[repo.get_id()] = {
                "id": repo.get_id(),
                "name": repo.get_name(),
                "baseurl": list(repo_cfg.get_baseurl_option().get_value()),  # resolves to () if unset
                "metalink": get_string_option(repo_cfg.get_metalink_option()),
                "mirrorlist": get_string_option(repo_cfg.get_mirrorlist_option()),
                "gpgcheck": repo_cfg.get_gpgcheck_option().get_value(),
                "repo_gpgcheck": repo_cfg.get_repo_gpgcheck_option().get_value(),
                "gpgkeys": read_keys(repo_cfg.get_gpgkey_option().get_value(),
                                     root_dir if repo.get_id() not in request_repo_ids else None),
                "sslverify": repo_cfg.get_sslverify_option().get_value(),
                "sslclientkey": get_string_option(repo_cfg.get_sslclientkey_option()),
                "sslclientcert": get_string_option(repo_cfg.get_sslclientcert_option()),
                "sslcacert": get_string_option(repo_cfg.get_sslcacert_option()),
            }
        response = {
            "packages": packages,
            "repos": repositories,
        }
        return response
