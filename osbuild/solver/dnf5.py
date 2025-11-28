import os
import os.path
import tempfile
from typing import Dict, List, Optional, Set

import libdnf5 as dnf5
from libdnf5.base import GoalProblem_NO_PROBLEM as NO_PROBLEM
from libdnf5.base import GoalProblem_NOT_FOUND as NOT_FOUND
from libdnf5.common import QueryCmp_CONTAINS as CONTAINS
from libdnf5.common import QueryCmp_EQ as EQ
from libdnf5.common import QueryCmp_GLOB as GLOB

import osbuild.solver.model as model
from osbuild.solver import SolverBase, modify_rootdir_path, read_keys
from osbuild.solver.exceptions import DepsolveError, MarkingError, NoReposError, RepoError
from osbuild.solver.request import DepsolveCmdArgs, RepositoryConfig, SearchCmdArgs, SolverConfig
from osbuild.util.sbom.dnf5 import dnf_pkgset_to_sbom_pkgset
from osbuild.util.sbom.spdx import sbom_pkgset_to_spdx2_doc


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


def any_repos_enabled(base):
    """Return true if any repositories are enabled"""
    rq = dnf5.repo.RepoQuery(base)
    return rq.begin() != rq.end()


def _reldep_to_dependency(reldep: dnf5.rpm.Reldep) -> model.Dependency:
    """
    Convert a libdnf5.rpm.Reldep to an RPM Dependency.
    """
    return model.Dependency(reldep.get_name(), reldep.get_relation().strip(), reldep.get_version())


# pylint: disable=too-many-branches
def _dnf_pkg_to_package(pkg: dnf5.rpm.Package) -> model.Package:
    """
    Convert a dnf5.rpm.Package to an RPM Package.
    """
    kwargs = {
        "name": pkg.get_name(),
        "version": pkg.get_version(),
        "release": pkg.get_release(),
        "arch": pkg.get_arch(),
        "epoch": int(pkg.get_epoch()),
        "group": pkg.get_group() or "",
        "download_size": pkg.get_download_size() or 0,
        "install_size": pkg.get_install_size() or 0,
        "license": pkg.get_license() or "",
        "source_rpm": pkg.get_sourcerpm() or "",
        "build_time": pkg.get_build_time() or 0,
        "packager": pkg.get_packager() or "",
        "vendor": pkg.get_vendor() or "",
        "url": pkg.get_url() or "",
        "summary": pkg.get_summary() or "",
        "description": pkg.get_description() or "",
        "provides": sorted([_reldep_to_dependency(p) for p in pkg.get_provides()], key=str),
        "requires": sorted([_reldep_to_dependency(p) for p in pkg.get_requires()], key=str),
        "requires_pre": sorted([_reldep_to_dependency(p) for p in pkg.get_requires_pre()], key=str),
        "conflicts": sorted([_reldep_to_dependency(p) for p in pkg.get_conflicts()], key=str),
        "obsoletes": sorted([_reldep_to_dependency(p) for p in pkg.get_obsoletes()], key=str),
        "regular_requires": sorted([_reldep_to_dependency(p) for p in pkg.get_regular_requires()], key=str),
        "recommends": sorted([_reldep_to_dependency(p) for p in pkg.get_recommends()], key=str),
        "suggests": sorted([_reldep_to_dependency(p) for p in pkg.get_suggests()], key=str),
        "enhances": sorted([_reldep_to_dependency(p) for p in pkg.get_enhances()], key=str),
        "supplements": sorted([_reldep_to_dependency(p) for p in pkg.get_supplements()], key=str),
        "files": list(pkg.get_files()),
        "location": pkg.get_location() or "",
        "remote_locations": list(pkg.get_remote_locations()),
        "repo_id": pkg.get_repo().get_id() or "",
        "reason": pkg.get_reason() or "",
    }
    checksum = pkg.get_checksum()
    if checksum and checksum.get_type() != dnf5.rpm.Checksum.Type_UNKNOWN:
        kwargs["checksum"] = model.Checksum(
            algorithm=checksum.get_type_str(), value=checksum.get_checksum())
    header_checksum = pkg.get_hdr_checksum()
    if header_checksum and header_checksum.get_type() != dnf5.rpm.Checksum.Type_UNKNOWN:
        kwargs["header_checksum"] = model.Checksum(
            algorithm=header_checksum.get_type_str(), value=header_checksum.get_checksum())
    return model.Package(**kwargs)


def _dnf_repo_to_repository(
    repo: dnf5.repo.Repo,
    root_dir: Optional[str],
    request_repo_ids: Set[str],
) -> model.Repository:
    """
    Convert a dnf5.repo.Repo to a Repository.
    """
    repo_cfg = repo.get_config()
    return model.Repository(
        repo_id=repo.get_id(),
        name=repo.get_name(),
        baseurl=list(repo_cfg.get_baseurl_option().get_value()),
        metalink=get_string_option(repo_cfg.get_metalink_option()),
        mirrorlist=get_string_option(repo_cfg.get_mirrorlist_option()),
        gpgcheck=repo_cfg.get_pkg_gpgcheck_option().get_value(),
        repo_gpgcheck=repo_cfg.get_repo_gpgcheck_option().get_value(),
        gpgkeys=read_keys(
            repo_cfg.get_gpgkey_option().get_value(),
            root_dir if repo.get_id() not in request_repo_ids else None
        ),
        sslverify=repo_cfg.get_sslverify_option().get_value(),
        sslcacert=get_string_option(repo_cfg.get_sslcacert_option()),
        sslclientkey=get_string_option(repo_cfg.get_sslclientkey_option()),
        sslclientcert=get_string_option(repo_cfg.get_sslclientcert_option()),
    )


class DNF5(SolverBase):
    """Solver implements package related actions

    These include depsolving a package set, searching for packages, and dumping a list
    of all available packages.
    """

    SOLVER_NAME = "dnf5"

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

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        config: SolverConfig,
        persistdir: os.PathLike,
        license_index_path: Optional[os.PathLike] = None,
    ):
        super().__init__(config, persistdir, license_index_path)

        self.repos = self.config.repos or []
        self.request_repo_ids = {repo.repo_id for repo in self.repos}
        self.root_dir = self.config.root_dir

        # pylint: disable=fixme
        # XXX: This should be handled in the depsolve() function, where we should be setting up the
        # repos for each transaction, because the excluded packages are setup per-transaction!
        # We stopped doing this because the full request is not available any more when constructing the Solver object.
        # Since 'basic_pkg_group_with_excludes' and 'install_pkg_excluded_in_another_transaction' test cases are broken
        # with dnf5 anyway, there is little harm in not gathering up all the exclude packages from all the transactions.
        # The original behavior was incorrect anyway, because it would exclude the packages from all the transactions,
        # which explicitly breaks 'install_pkg_excluded_in_another_transaction' test case.
        # exclude_pkgs: List[str] = []
        # if self.request.depsolve_args:
        #     for transaction in self.request.depsolve_args.transactions:
        #         exclude_pkgs.extend(transaction.exclude_specs or [])

        self.base = dnf5.base.Base()

        # Base is the correct place to set substitutions, not per-repo.
        # See https://github.com/rpm-software-management/dnf5/issues/1248
        self.base.get_vars().set("arch", self.config.arch)
        self.base.get_vars().set("basearch", self._BASEARCH_MAP[self.config.arch])
        if self.config.releasever:
            self.base.get_vars().set('releasever', self.config.releasever)
        if self.config.proxy:
            self.base.get_vars().set('proxy', self.config.proxy)

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
        if self.config.module_platform_id:
            conf.module_platform_id = self.config.module_platform_id
        conf.config_file_path = "/dev/null"
        conf.persistdir = persistdir
        conf.cachedir = self.config.cachedir

        # Include comps metadata by default
        metadata_types = ['comps']
        if self.config.optional_metadata:
            metadata_types.extend(self.config.optional_metadata)
        conf.optional_metadata_types = metadata_types

        try:
            # NB: Package exclusion was previously handled here, but it should
            # be handled in the depsolve() function per transaction instead.
            # NOTE: With libdnf5 packages are excluded in the repo setup
            for repo_conf in self.repos:
                self._dnfrepo(repo_conf)

            if self.root_dir:
                # This sets the varsdir to ("{root_dir}/usr/share/dnf5/vars.d/", "{root_dir}/etc/dnf/vars/") for custom
                # variable substitution (e.g. CentOS Stream 9's $stream variable)
                conf.installroot = self.root_dir
                conf.varsdir = (
                    os.path.join(self.root_dir, "etc/dnf/vars"),
                    os.path.join(self.root_dir, "usr/share/dnf5/vars.d")
                )

            # Cannot modify .conf() values after this
            # base.setup() should be called before loading repositories otherwise substitutions might not work.
            self.base.setup()

            if self.root_dir:
                repos_dir = os.path.join(self.root_dir, "etc/yum.repos.d")
                self.base.get_repo_sack().create_repos_from_dir(repos_dir)
                rq = dnf5.repo.RepoQuery(self.base)
                rq.filter_enabled(True)
                repo_iter = rq.begin()
                while repo_iter != rq.end():
                    repo = repo_iter.value()
                    repo_config = repo.get_config()
                    repo_config.sslcacert = modify_rootdir_path(
                        get_string_option(repo_config.get_sslcacert_option()),
                        self.root_dir,
                    )
                    repo_config.sslclientcert = modify_rootdir_path(
                        get_string_option(repo_config.get_sslclientcert_option()),
                        self.root_dir,
                    )
                    repo_config.sslclientkey = modify_rootdir_path(
                        get_string_option(repo_config.get_sslclientkey_option()),
                        self.root_dir,
                    )
                    repo_iter.next()

            self.base.get_repo_sack().load_repos(dnf5.repo.Repo.Type_AVAILABLE)
        except Exception as e:
            raise RepoError(e) from e

        if not any_repos_enabled(self.base):
            raise NoReposError("There are no enabled repositories")

    # pylint: disable=too-many-branches
    def _dnfrepo(self, desc: RepositoryConfig, exclude_pkgs=None):
        """Makes a dnf.repo.Repo out of request.RepositoryConfig configuration"""
        if not exclude_pkgs:
            exclude_pkgs = []

        sack = self.base.get_repo_sack()

        repo = sack.create_repo(desc.repo_id)
        conf = repo.get_config()

        # NB: default to using the repo_id as the name, to be consistent with DNF4 solver.
        # DNF5 documentation says that this should happen, but it doesn't seem to be the case.
        # https://github.com/rpm-software-management/dnf5/issues/2533
        conf.name = desc.repo_id
        if desc.name:
            conf.name = desc.name

        # NB: the fact that at least one is set is checked when parsing the Solver request
        if desc.baseurl:
            conf.baseurl = desc.baseurl
        if desc.metalink:
            conf.metalink = desc.metalink
        if desc.mirrorlist:
            conf.mirrorlist = desc.mirrorlist

        conf.sslverify = desc.sslverify
        if desc.sslcacert:
            conf.sslcacert = desc.sslcacert
        if desc.sslclientkey:
            conf.sslclientkey = desc.sslclientkey
        if desc.sslclientcert:
            conf.sslclientcert = desc.sslclientcert

        if desc.gpgcheck:
            conf.gpgcheck = desc.gpgcheck
        if desc.repo_gpgcheck:
            conf.repo_gpgcheck = desc.repo_gpgcheck
        if desc.gpgkey:
            # gpgkeys can contain a full key, or it can be a URL
            # dnf expects urls, so write the key to a temporary location and add the file://
            # path to conf.gpgkey
            keydir = os.path.join(self.base.get_config().persistdir, "gpgkeys")
            if not os.path.exists(keydir):
                os.makedirs(keydir, mode=0o700, exist_ok=True)

            for key in desc.gpgkey:
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

        conf.metadata_expire = desc.metadata_expire
        if desc.module_hotfixes:
            repo.module_hotfixes = desc.module_hotfixes

        # Set the packages to exclude
        conf.excludepkgs = exclude_pkgs

        return repo

    def _sbom_for_pkgset(self, pkgset: List[dnf5.rpm.Package]) -> Dict:
        """
        Create an SBOM document for the given package set.

        For now, only SPDX v2 is supported.
        """
        pkgset = dnf_pkgset_to_sbom_pkgset(pkgset)
        spdx_doc = sbom_pkgset_to_spdx2_doc(pkgset, self.license_index_path)
        return spdx_doc.to_dict()

    def dump(self) -> model.DumpResult:
        """dump returns a list of all available packages"""
        packages = []
        repositories = {}
        q = dnf5.rpm.PackageQuery(self.base)
        q.filter_available()
        for package in list(q):
            packages.append(_dnf_pkg_to_package(package))
            if package.get_repo().get_id() not in repositories:
                repositories[package.get_repo().get_id()] = _dnf_repo_to_repository(
                    package.get_repo(), self.root_dir, self.request_repo_ids)

        return model.DumpResult(packages, list(repositories.values()))

    def search(self, args: SearchCmdArgs) -> model.SearchResult:
        """ Perform a search on the available packages"""

        packages = []
        repositories = {}

        # NOTE: Build query one piece at a time, don't pass all to filterm at the same
        # time.
        for name in args.packages:
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

            if args.latest:
                q.filter_latest_evr()

            for package in list(q):
                packages.append(_dnf_pkg_to_package(package))
                if package.get_repo().get_id() not in repositories:
                    repositories[package.get_repo().get_id()] = _dnf_repo_to_repository(
                        package.get_repo(), self.root_dir, self.request_repo_ids)

        return model.SearchResult(packages, list(repositories.values()))

    def depsolve(self, args: DepsolveCmdArgs) -> model.DepsolveResult:
        """Perform a dependency resolution for the given transactions"""
        last_dnf_transaction: List[dnf5.rpm.Package] = []
        # List of transaction results, each containing a list of packages that are a result of dependency resolution.
        # Each transaction result is a superset of the previous transaction result.
        # The package list in each transaction is alphabetically sorted by full NEVRA.
        transactions_results: List[List[model.Package]] = []
        repositories_by_id: Dict[str, model.Repository] = {}
        repositories: List[model.Repository] = []

        for transaction in args.transactions:
            goal = dnf5.base.Goal(self.base)
            goal.reset()
            sack = self.base.get_rpm_package_sack()
            sack.clear_user_excludes()

            # weak deps are selected per-transaction
            self.base.get_config().install_weak_deps = transaction.install_weak_deps

            # set the packages from the last transaction as installed
            for installed_pkg in last_dnf_transaction:
                goal.add_rpm_install(installed_pkg)

            # Support group/environment names as well as ids
            settings = dnf5.base.GoalJobSettings()
            settings.group_with_name = True

            # Packages are added individually
            # XXX: Add package excludes handling here!
            for package_spec in transaction.package_specs:
                goal.add_install(package_spec, settings)
            goal_result = goal.resolve()

            transaction_problems = goal_result.get_problems()
            if transaction_problems == NOT_FOUND:
                raise MarkingError("\n".join(goal_result.get_resolve_logs_as_strings()))
            if transaction_problems != NO_PROBLEM:
                raise DepsolveError("\n".join(goal_result.get_resolve_logs_as_strings()))

            transaction_result = []
            # store the current transaction result
            last_dnf_transaction.clear()
            for tsi in goal_result.get_transaction_packages():
                # Only add packages being installed, upgraded, downgraded, or reinstalled
                if not dnf5.base.transaction.transaction_item_action_is_inbound(tsi.get_action()):
                    continue
                pkg = tsi.get_package()
                last_dnf_transaction.append(pkg)
                transaction_result.append(_dnf_pkg_to_package(pkg))
                repo = pkg.get_repo()
                if repo.get_id() not in repositories_by_id:
                    repositories_by_id[repo.get_id()] = _dnf_repo_to_repository(
                        repo, self.root_dir, self.request_repo_ids)

            # NB: DNF5 solver returns packages in topological order, but the original DNF4 solver returns
            # alphabetically sorted packages. To be consistent and match the original DNF4 solver behavior,
            # we sort the packages alphabetically by full NEVRA.
            # NB: the org.osbuild.rpm stage as generated by osbuild/images does not depend on the order of packages,
            # because rpm gets the full package set at once and it will reorder the packages as needed when installing.
            transaction_result.sort()
            transactions_results.append(transaction_result)

        # NB: we sort the repositories by repo_id to ensure consistent ordering across DNF4 and DNF5.
        repositories = list(repositories_by_id.values())
        repositories.sort(key=lambda x: x.repo_id)

        # Something went wrong, but no error was generated by goal.resolve()
        if len(args.transactions) > 0 and len(transactions_results[-1]) == 0:
            raise DepsolveError("Empty transaction results")

        sbom = None
        if args.sbom_request:
            sbom = self._sbom_for_pkgset(last_dnf_transaction)

        return model.DepsolveResult(
            transactions=transactions_results,
            repositories=repositories,
            modules=None,  # DNF5 Solver does not support modules
            sbom=sbom,
        )
