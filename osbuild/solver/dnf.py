# pylint: disable=too-many-branches
# pylint: disable=too-many-nested-blocks

import itertools
import os
import os.path
import tempfile
from typing import Any, Dict, List, Optional, Set

import dnf
import hawkey
import libdnf
from dnf.i18n import ucd

import osbuild.solver.model as model
from osbuild.solver import SolverBase, modify_rootdir_path, read_keys
from osbuild.solver.exceptions import DepsolveError, MarkingError, NoReposError, RepoError
from osbuild.solver.request import DepsolveCmdArgs, RepositoryConfig, SearchCmdArgs, SolverRequest
from osbuild.util.sbom.dnf import dnf_pkgset_to_sbom_pkgset
from osbuild.util.sbom.spdx import sbom_pkgset_to_spdx2_doc


def _reldep_to_dependency(reldep: hawkey.Reldep) -> model.Dependency:
    """
    Convert a hawkey.Reldep to an RPM Dependency.

    Note: Handles compatibility with RHEL-8 where Reldep objects don't have name/relation/version attributes.
    """
    try:
        return model.Dependency(reldep.name, reldep.relation.strip(), reldep.version)
    except AttributeError:
        # '_hawkey.Reldep' object has no attribute 'name' in the version shipped on RHEL-8
        dep_parts = str(reldep).split()
        while len(dep_parts) < 3:
            dep_parts.append("")
        return model.Dependency(dep_parts[0], dep_parts[1].strip(), dep_parts[2])


def _dnf_pkg_to_package(pkg: dnf.package.Package) -> model.Package:
    """
    Convert a dnf.package.Package to an RPM Package.
    """
    kwargs = {
        "name": pkg.name,
        "version": pkg.version,
        "release": pkg.release,
        "arch": pkg.arch,
        "epoch": int(pkg.epoch),
        "group": pkg.group or "",
        "download_size": pkg.downloadsize or 0,
        "install_size": pkg.installsize or 0,
        "license": pkg.license or "",
        "source_rpm": pkg.sourcerpm or "",
        "build_time": pkg.buildtime or 0,
        "packager": pkg.packager or "",
        "vendor": pkg.vendor or "",
        "url": pkg.url or "",
        "summary": pkg.summary or "",
        "description": pkg.description or "",
        "provides": sorted([_reldep_to_dependency(p) for p in pkg.provides], key=str),
        "requires": sorted([_reldep_to_dependency(p) for p in pkg.requires], key=str),
        "requires_pre": sorted([_reldep_to_dependency(p) for p in pkg.requires_pre], key=str),
        "conflicts": sorted([_reldep_to_dependency(p) for p in pkg.conflicts], key=str),
        "obsoletes": sorted([_reldep_to_dependency(p) for p in pkg.obsoletes], key=str),
        "regular_requires": sorted([_reldep_to_dependency(p) for p in pkg.regular_requires], key=str),
        "recommends": sorted([_reldep_to_dependency(p) for p in pkg.recommends], key=str),
        "suggests": sorted([_reldep_to_dependency(p) for p in pkg.suggests], key=str),
        "enhances": sorted([_reldep_to_dependency(p) for p in pkg.enhances], key=str),
        "supplements": sorted([_reldep_to_dependency(p) for p in pkg.supplements], key=str),
        "files": pkg.files,
        "location": pkg.location or "",
        "repo_id": pkg.repoid or "",
        "reason": pkg.reason or "",
    }
    # NB: prevent setting a [None] list for remote_locations
    if pkg.remote_location():
        kwargs["remote_locations"] = [pkg.remote_location()]
    checksum = pkg.chksum
    if checksum and hawkey.chksum_name(checksum[0]) != "UNKNOWN":
        kwargs["checksum"] = model.Checksum(
            algorithm=hawkey.chksum_name(checksum[0]), value=checksum[1].hex())
    header_checksum = pkg.hdr_chksum
    if header_checksum and hawkey.chksum_name(header_checksum[0]) != "UNKNOWN":
        kwargs["header_checksum"] = model.Checksum(
            algorithm=hawkey.chksum_name(pkg.hdr_chksum[0]), value=pkg.hdr_chksum[1].hex())
    return model.Package(**kwargs)


def _dnf_repo_to_repository(
    repo: dnf.repo.Repo,
    root_dir: Optional[str],
    request_repo_ids: Set[str],
) -> model.Repository:
    """
    Convert a dnf.repo.Repo to a Repository.
    """
    return model.Repository(
        repo_id=repo.id,
        name=repo.name,
        baseurl=list(repo.baseurl),
        metalink=repo.metalink,
        mirrorlist=repo.mirrorlist,
        gpgcheck=repo.gpgcheck,
        repo_gpgcheck=repo.repo_gpgcheck,
        gpgkeys=read_keys(repo.gpgkey, root_dir if repo.id not in request_repo_ids else None),
        sslverify=bool(repo.sslverify),
        sslcacert=repo.sslcacert,
        sslclientkey=repo.sslclientkey,
        sslclientcert=repo.sslclientcert,
    )


class DNF(SolverBase):
    SOLVER_NAME = "dnf"

    def __init__(
        self,
        request: SolverRequest,
        persistdir: os.PathLike,
        license_index_path: Optional[os.PathLike] = None,
    ):
        super().__init__(request, persistdir, license_index_path)

        self.repos = self.request.config.repos or []
        self.request_repo_ids = {repo.repo_id for repo in self.repos} if self.repos else set()
        self.root_dir = self.request.config.root_dir

        self.base = dnf.Base()

        # Enable fastestmirror to ensure we choose the fastest mirrors for
        # downloading metadata (when depsolving) and downloading packages.
        self.base.conf.fastestmirror = True

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
        self.base.conf.zchunk = False

        # Set the rest of the dnf configuration.
        if self.request.config.module_platform_id:
            self.base.conf.module_platform_id = self.request.config.module_platform_id
        self.base.conf.config_file_path = "/dev/null"
        self.base.conf.persistdir = persistdir
        self.base.conf.cachedir = self.request.config.cachedir
        self.base.conf.substitutions['arch'] = self.request.config.arch
        self.base.conf.substitutions['basearch'] = dnf.rpm.basearch(self.request.config.arch)
        self.base.conf.substitutions['releasever'] = self.request.config.releasever

        # variables substitution is only available when root_dir is provided
        if self.root_dir:
            # This sets the varsdir to ("{root_dir}/etc/yum/vars/", "{root_dir}/etc/dnf/vars/") for custom variable
            # substitution (e.g. CentOS Stream 9's $stream variable)
            self.base.conf.substitutions.update_from_etc(self.root_dir)

        if hasattr(self.base.conf, "optional_metadata_types") and self.request.config.optional_metadata:
            # the attribute doesn't exist on older versions of dnf; ignore the option when not available
            self.base.conf.optional_metadata_types.extend(self.request.config.optional_metadata)
        if self.request.config.proxy:
            self.base.conf.proxy = self.request.config.proxy

        try:
            for repo_conf in self.repos:
                self.base.repos.add(self._dnfrepo(repo_conf, self.base.conf, self.root_dir is not None))

            if self.root_dir:
                repos_dir = os.path.join(self.root_dir, "etc/yum.repos.d")
                self.base.conf.reposdir = repos_dir
                self.base.read_all_repos()
                for repo_id, repo_config in self.base.repos.items():
                    if repo_id not in self.request_repo_ids:
                        repo_config.sslcacert = modify_rootdir_path(repo_config.sslcacert, self.root_dir)
                        repo_config.sslclientcert = modify_rootdir_path(repo_config.sslclientcert, self.root_dir)
                        repo_config.sslclientkey = modify_rootdir_path(repo_config.sslclientkey, self.root_dir)

            self.base.update_cache()
            self.base.fill_sack(load_system_repo=False)
        except Exception as e:
            raise RepoError(e) from e

        if not self.base.repos._any_enabled():
            raise NoReposError("There are no enabled repositories")

        # enable module resolving
        self.base_module = dnf.module.module_base.ModuleBase(self.base)

    @staticmethod
    def _dnfrepo(desc: RepositoryConfig, parent_conf=None, subs_links=False):
        """Makes a dnf.repo.Repo out of request.RepositoryConfig configuration"""

        repo = dnf.repo.Repo(desc.repo_id, parent_conf)
        config = libdnf.conf.ConfigParser

        if desc.name:
            repo.name = desc.name

        def subs(basestr):
            if subs_links and parent_conf:
                return config.substitute(ucd(basestr), parent_conf.substitutions)
            return basestr

        # NB: the fact that at least one is set is checked when parsing the Solver request
        if desc.baseurl:
            repo.baseurl = [subs(url) for url in desc.baseurl]
        if desc.metalink:
            repo.metalink = subs(desc.metalink)
        if desc.mirrorlist:
            repo.mirrorlist = subs(desc.mirrorlist)

        repo.sslverify = desc.sslverify
        if desc.sslcacert:
            repo.sslcacert = desc.sslcacert
        if desc.sslclientkey:
            repo.sslclientkey = desc.sslclientkey
        if desc.sslclientcert:
            repo.sslclientcert = desc.sslclientcert

        if desc.gpgcheck:
            repo.gpgcheck = desc.gpgcheck
        if desc.repo_gpgcheck:
            repo.repo_gpgcheck = desc.repo_gpgcheck
        if desc.gpgkey:
            # gpgkeys can contain a full key, or it can be a URL
            # dnf expects urls, so write the key to a temporary location and add the file://
            # path to repo.gpgkey
            keydir = os.path.join(parent_conf.persistdir, "gpgkeys")
            if not os.path.exists(keydir):
                os.makedirs(keydir, mode=0o700, exist_ok=True)

            for key in desc.gpgkey:
                if key.startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----"):
                    # Not using with because it needs to be a valid file for the duration. It
                    # is inside the temporary persistdir so will be cleaned up on exit.
                    # pylint: disable=consider-using-with
                    keyfile = tempfile.NamedTemporaryFile(dir=keydir, delete=False)
                    keyfile.write(key.encode("utf-8"))
                    repo.gpgkey.append(f"file://{keyfile.name}")
                    keyfile.close()
                else:
                    repo.gpgkey.append(key)

        repo.metadata_expire = desc.metadata_expire

        # This option if True disables modularization filtering. Effectively
        # disabling modularity for given repository.
        if desc.module_hotfixes:
            repo.module_hotfixes = desc.module_hotfixes

        return repo

    def _sbom_for_pkgset(self, pkgset: List[dnf.package.Package]) -> Dict:
        """
        Create an SBOM document for the given package set.

        For now, only SPDX v2 is supported.
        """
        pkgset = dnf_pkgset_to_sbom_pkgset(pkgset)
        spdx_doc = sbom_pkgset_to_spdx2_doc(pkgset, self.license_index_path)
        return spdx_doc.to_dict()

    def dump(self) -> model.DumpResult:
        packages = []
        repositories = {}
        for pkg in self.base.sack.query().available():
            packages.append(_dnf_pkg_to_package(pkg))
            if pkg.repo.id not in repositories:
                repositories[pkg.repo.id] = _dnf_repo_to_repository(pkg.repo, self.root_dir, self.request_repo_ids)

        return model.DumpResult(packages, list(repositories.values()))

    def search(self, args: SearchCmdArgs) -> model.SearchResult:
        """ Perform a search on the available packages"""
        packages = []
        repositories = {}

        # NOTE: Build query one piece at a time, don't pass all to filterm at the same
        # time.
        available = self.base.sack.query().available()
        for name in args.packages:
            # If the package name glob has * in it, use glob.
            # If it has *name* use substr
            # If it has neither use exact match
            if "*" in name:
                if name[0] != "*" or name[-1] != "*":
                    q = available.filter(name__glob=name)
                else:
                    q = available.filter(name__substr=name.replace("*", ""))
            else:
                q = available.filter(name__eq=name)

            if args.latest:
                q = q.latest()

            for pkg in q:
                packages.append(_dnf_pkg_to_package(pkg))
                if pkg.repo.id not in repositories:
                    repositories[pkg.repo.id] = _dnf_repo_to_repository(pkg.repo, self.root_dir, self.request_repo_ids)

        return model.SearchResult(packages, list(repositories.values()))

    def depsolve(self, args: DepsolveCmdArgs) -> model.DepsolveResult:
        # collect repo IDs from the request so we know whether to translate gpg key paths
        last_transaction: List = []

        for transaction in args.transactions:
            self.base.reset(goal=True)
            self.base.sack.reset_excludes()

            self.base.conf.install_weak_deps = transaction.install_weak_deps

            try:
                # set the packages from the last transaction as installed
                for installed_pkg in last_transaction:
                    self.base.package_install(installed_pkg, strict=True)

                # enabling a module means that packages can be installed from that
                # module
                if transaction.module_enable_specs:
                    self.base_module.enable(transaction.module_enable_specs)

                # installing a module takes the specification of the module and then
                # installs all packages belonging to its default group, modules to
                # install are listed directly in `package-specs` but prefixed with an
                # `@` *and* containing a `:` this is up to the user of the depsolver
                self.base.install_specs(
                    transaction.package_specs,
                    transaction.exclude_specs,
                    reponame=transaction.repo_ids,
                )
            except dnf.exceptions.Error as e:
                raise MarkingError(e) from e

            try:
                self.base.resolve()
            except dnf.exceptions.Error as e:
                raise DepsolveError(e) from e

            # store the current transaction result
            last_transaction.clear()
            for tsi in self.base.transaction:
                # Avoid using the install_set() helper, as it does not guarantee
                # a stable order
                if tsi.action not in dnf.transaction.FORWARD_ACTIONS:
                    continue
                last_transaction.append(tsi.pkg)

        packages = []
        repositories = {}
        for package in last_transaction:
            packages.append(_dnf_pkg_to_package(package))
            repositories[package.repo.id] = _dnf_repo_to_repository(package.repo, self.root_dir, self.request_repo_ids)

        sbom = None
        if args.sbom_request:
            sbom = self._sbom_for_pkgset(last_transaction)

        # if any modules have been requested we add sources for these so they can
        # be used by stages to enable the modules in the eventual artifact
        modules: Dict[str, Any] = {}

        for transaction in args.transactions:
            # module specifications must start with an "@", if they do we try to
            # ask DNF for a module by that name, if it doesn't exist it isn't a
            # module; otherwise it is and we should use it
            modules_in_package_specs = []

            for p in transaction.package_specs:
                if p.startswith("@") and self.base_module.get_modules(p):
                    modules_in_package_specs.append(p.lstrip("@"))

            if transaction.module_enable_specs or modules_in_package_specs:
                # we'll be checking later if any packages-from-modules are in the
                # packages-to-install set so let's do this only once here
                package_nevras = []

                for package in packages:
                    if package.epoch == 0:
                        package_nevras.append(
                            f"{package.name}-{package.version}-{package.release}.{package.arch}")
                    else:
                        package_nevras.append(
                            f"{package.name}-{package.epoch}:{package.version}-{package.release}.{package.arch}")

                for module_spec in itertools.chain(
                    transaction.module_enable_specs or [],
                    modules_in_package_specs,
                ):
                    module_packages, module_nsvcap = self.base_module.get_modules(module_spec)

                    # we now need to do an annoying dance as multiple modules could be
                    # returned by `.get_modules`, we need to select the *same* one as
                    # previously selected. we do this by checking if any of the module
                    # packages are in the packages set marked for installation.

                    # this is a result of not being able to get the enabled modules
                    # from the transaction, if that turns out to be possible then
                    # we can get rid of these shenanigans
                    for module_package in module_packages:
                        module_nevras = module_package.getArtifacts()

                        if any(module_nevra in package_nevras for module_nevra in module_nevras):
                            # a package from this module is being installed so we must
                            # use this module
                            module_ns = f"{module_nsvcap.name}:{module_nsvcap.stream}"

                            if module_ns not in modules:
                                modules[module_ns] = (module_package, set())

                            if module_nsvcap.profile:
                                modules[module_ns][1].add(module_nsvcap.profile)

                            # we are unable to skip the rest of the `module_packages`
                            # here since different profiles might be contained

        # now we have the information we need about modules so we need to return *some*
        # information to who is using the depsolver so they can use that information to
        # enable these modules in the artifact

        # there are two files that matter for each module that is used, the caller needs
        # to write a file to `/etc/dnf/modules.d/{module_name}.module` to enable the
        # module for dnf

        # the caller also needs to set up `/var/lib/dnf/modulefailsafe/` with the contents
        # of the modulemd for the selected modules, this is to ensure that even when a
        # repository is disabled or disappears that non-modular content can't be installed
        # see: https://dnf.readthedocs.io/en/latest/modularity.html#fail-safe-mechanisms
        modules_response = {}
        for module_ns, (module, profiles) in modules.items():
            modules_response[module.getName()] = {
                "module-file": {
                    "path": f"/etc/dnf/modules.d/{module.getName()}.conf",
                    "data": {
                        "name": module.getName(),
                        "stream": module.getStream(),
                        "profiles": list(profiles),
                        "state": "enabled",
                    }
                },
                "failsafe-file": {
                    "data": module.getYaml(),
                    "path": f"/var/lib/dnf/modulefailsafe/{module.getName()}:{module.getStream()}",
                },
            }

        return model.DepsolveResult(
            packages=packages,
            repositories=list(repositories.values()),
            modules=modules_response if modules_response else None,
            sbom=sbom if sbom else None,
        )
