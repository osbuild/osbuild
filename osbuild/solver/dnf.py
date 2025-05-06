# pylint: disable=too-many-branches
# pylint: disable=too-many-nested-blocks

import itertools
import os
import os.path
import tempfile
from datetime import datetime
from typing import Dict, List

import dnf
import hawkey

from osbuild.solver import DepsolveError, MarkingError, RepoError, SolverBase, modify_rootdir_path, read_keys
from osbuild.util.sbom.dnf import dnf_pkgset_to_sbom_pkgset
from osbuild.util.sbom.spdx import sbom_pkgset_to_spdx2_doc


class DNF(SolverBase):
    def __init__(self, request, persistdir, cache_dir, license_index_path=None):
        arch = request["arch"]
        releasever = request.get("releasever")
        module_platform_id = request.get("module_platform_id")
        proxy = request.get("proxy")

        arguments = request["arguments"]
        repos = arguments.get("repos", [])
        root_dir = arguments.get("root_dir")

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
        if module_platform_id:
            self.base.conf.module_platform_id = module_platform_id
        self.base.conf.config_file_path = "/dev/null"
        self.base.conf.persistdir = persistdir
        self.base.conf.cachedir = cache_dir
        self.base.conf.substitutions['arch'] = arch
        self.base.conf.substitutions['basearch'] = dnf.rpm.basearch(arch)
        self.base.conf.substitutions['releasever'] = releasever

        if hasattr(self.base.conf, "optional_metadata_types"):
            # the attribute doesn't exist on older versions of dnf; ignore the option when not available
            self.base.conf.optional_metadata_types.extend(arguments.get("optional-metadata", []))
        if proxy:
            self.base.conf.proxy = proxy

        try:
            req_repo_ids = set()
            for repo in repos:
                self.base.repos.add(self._dnfrepo(repo, self.base.conf))
                # collect repo IDs from the request to separate them from the ones loaded from a root_dir
                req_repo_ids.add(repo["id"])

            if root_dir:
                # This sets the varsdir to ("{root_dir}/etc/yum/vars/", "{root_dir}/etc/dnf/vars/") for custom variable
                # substitution (e.g. CentOS Stream 9's $stream variable)
                self.base.conf.substitutions.update_from_etc(root_dir)

                repos_dir = os.path.join(root_dir, "etc/yum.repos.d")
                self.base.conf.reposdir = repos_dir
                self.base.read_all_repos()
                for repo_id, repo_config in self.base.repos.items():
                    if repo_id not in req_repo_ids:
                        repo_config.sslcacert = modify_rootdir_path(repo_config.sslcacert, root_dir)
                        repo_config.sslclientcert = modify_rootdir_path(repo_config.sslclientcert, root_dir)
                        repo_config.sslclientkey = modify_rootdir_path(repo_config.sslclientkey, root_dir)

            self.base.update_cache()
            self.base.fill_sack(load_system_repo=False)
        except dnf.exceptions.Error as e:
            raise RepoError(e) from e

        # enable module resolving
        self.base_module = dnf.module.module_base.ModuleBase(self.base)

        # Custom license index file path use for SBOM generation
        self.license_index_path = license_index_path

    @staticmethod
    def _dnfrepo(desc, parent_conf=None):
        """Makes a dnf.repo.Repo out of a JSON repository description"""

        repo = dnf.repo.Repo(desc["id"], parent_conf)

        if "name" in desc:
            repo.name = desc["name"]

        # at least one is required
        if "baseurl" in desc:
            repo.baseurl = desc["baseurl"]
        elif "metalink" in desc:
            repo.metalink = desc["metalink"]
        elif "mirrorlist" in desc:
            repo.mirrorlist = desc["mirrorlist"]
        else:
            raise ValueError("missing either `baseurl`, `metalink`, or `mirrorlist` in repo")

        repo.sslverify = desc.get("sslverify", True)
        if "sslcacert" in desc:
            repo.sslcacert = desc["sslcacert"]
        if "sslclientkey" in desc:
            repo.sslclientkey = desc["sslclientkey"]
        if "sslclientcert" in desc:
            repo.sslclientcert = desc["sslclientcert"]

        if "gpgcheck" in desc:
            repo.gpgcheck = desc["gpgcheck"]
        if "repo_gpgcheck" in desc:
            repo.repo_gpgcheck = desc["repo_gpgcheck"]
        if "gpgkey" in desc:
            repo.gpgkey = [desc["gpgkey"]]
        if "gpgkeys" in desc:
            # gpgkeys can contain a full key, or it can be a URL
            # dnf expects urls, so write the key to a temporary location and add the file://
            # path to repo.gpgkey
            keydir = os.path.join(parent_conf.persistdir, "gpgkeys")
            if not os.path.exists(keydir):
                os.makedirs(keydir, mode=0o700, exist_ok=True)

            for key in desc["gpgkeys"]:
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

        # In dnf, the default metadata expiration time is 48 hours. However,
        # some repositories never expire the metadata, and others expire it much
        # sooner than that. We therefore allow this to be configured. If nothing
        # is provided we error on the side of checking if we should invalidate
        # the cache. If cache invalidation is not necessary, the overhead of
        # checking is in the hundreds of milliseconds. In order to avoid this
        # overhead accumulating for API calls that consist of several dnf calls,
        # we set the expiration to a short time period, rather than 0.
        repo.metadata_expire = desc.get("metadata_expire", "20s")

        # This option if True disables modularization filtering. Effectively
        # disabling modularity for given repository.
        if "module_hotfixes" in desc:
            repo.module_hotfixes = desc["module_hotfixes"]

        return repo

    @staticmethod
    def _timestamp_to_rfc3339(timestamp):
        return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%dT%H:%M:%SZ')

    def _sbom_for_pkgset(self, pkgset: List[dnf.package.Package]) -> Dict:
        """
        Create an SBOM document for the given package set.

        For now, only SPDX v2 is supported.
        """
        pkgset = dnf_pkgset_to_sbom_pkgset(pkgset)
        spdx_doc = sbom_pkgset_to_spdx2_doc(pkgset, self.license_index_path)
        return spdx_doc.to_dict()

    def dump(self):
        packages = []
        for package in self.base.sack.query().available():
            packages.append({
                "name": package.name,
                "summary": package.summary,
                "description": package.description,
                "url": package.url,
                "repo_id": package.repoid,
                "epoch": package.epoch,
                "version": package.version,
                "release": package.release,
                "arch": package.arch,
                "buildtime": self._timestamp_to_rfc3339(package.buildtime),
                "license": package.license
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
        available = self.base.sack.query().available()
        for name in pkg_globs:
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

            if args.get("latest", False):
                q = q.latest()

            for package in q:
                packages.append({
                    "name": package.name,
                    "summary": package.summary,
                    "description": package.description,
                    "url": package.url,
                    "repo_id": package.repoid,
                    "epoch": package.epoch,
                    "version": package.version,
                    "release": package.release,
                    "arch": package.arch,
                    "buildtime": self._timestamp_to_rfc3339(package.buildtime),
                    "license": package.license
                })
        return packages

    def depsolve(self, arguments):
        # Return an empty list when 'transactions' key is missing or when it is None
        transactions = arguments.get("transactions") or []
        # collect repo IDs from the request so we know whether to translate gpg key paths
        request_repo_ids = set(repo["id"] for repo in arguments.get("repos", []))
        root_dir = arguments.get("root_dir")
        last_transaction: List = []

        for transaction in transactions:
            self.base.reset(goal=True)
            self.base.sack.reset_excludes()

            self.base.conf.install_weak_deps = transaction.get("install_weak_deps", False)

            try:
                # set the packages from the last transaction as installed
                for installed_pkg in last_transaction:
                    self.base.package_install(installed_pkg, strict=True)

                # enabling a module means that packages can be installed from that
                # module
                self.base_module.enable(transaction.get("module-enable-specs", []))

                # installing a module takes the specification of the module and then
                # installs all packages belonging to its default group, modules to
                # install are listed directly in `package-specs` but prefixed with an
                # `@` *and* containing a `:` this is up to the user of the depsolver
                self.base.install_specs(
                    transaction.get("package-specs"),
                    transaction.get("exclude-specs"),
                    reponame=transaction.get("repo-ids"),
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
        pkg_repos = {}
        for package in last_transaction:
            packages.append({
                "name": package.name,
                "epoch": package.epoch,
                "version": package.version,
                "release": package.release,
                "arch": package.arch,
                "repo_id": package.repoid,
                "path": package.relativepath,
                "remote_location": package.remote_location(),
                "checksum": f"{hawkey.chksum_name(package.chksum[0])}:{package.chksum[1].hex()}",
            })
            # collect repository objects by id to create the 'repositories' collection for the response
            pkgrepo = package.repo
            pkg_repos[pkgrepo.id] = pkgrepo

        repositories = {}  # full repository configs for the response
        for repo in pkg_repos.values():
            repositories[repo.id] = {
                "id": repo.id,
                "name": repo.name,
                "baseurl": list(repo.baseurl) if repo.baseurl else None,
                "metalink": repo.metalink,
                "mirrorlist": repo.mirrorlist,
                "gpgcheck": repo.gpgcheck,
                "repo_gpgcheck": repo.repo_gpgcheck,
                "gpgkeys": read_keys(repo.gpgkey, root_dir if repo.id not in request_repo_ids else None),
                "sslverify": bool(repo.sslverify),
                "sslcacert": repo.sslcacert,
                "sslclientkey": repo.sslclientkey,
                "sslclientcert": repo.sslclientcert,
            }
        response = {
            "solver": "dnf",
            "packages": packages,
            "repos": repositories,
            "modules": {},
        }

        if "sbom" in arguments:
            response["sbom"] = self._sbom_for_pkgset(last_transaction)

        # if any modules have been requested we add sources for these so they can
        # be used by stages to enable the modules in the eventual artifact
        modules = {}

        for transaction in transactions:
            # module specifications must start with an "@", if they do we try to
            # ask DNF for a module by that name, if it doesn't exist it isn't a
            # module; otherwise it is and we should use it
            modules_in_package_specs = []

            for p in transaction.get("package-specs", []):
                if p.startswith("@") and self.base_module.get_modules(p):
                    modules_in_package_specs.append(p.lstrip("@"))

            if transaction.get("module-enable-specs") or modules_in_package_specs:
                # we'll be checking later if any packages-from-modules are in the
                # packages-to-install set so let's do this only once here
                package_nevras = []

                for package in packages:
                    if package["epoch"] == 0:
                        package_nevras.append(
                            f"{package['name']}-{package['version']}-{package['release']}.{package['arch']}")
                    else:
                        package_nevras.append(
                            f"{package['name']}-{package['epoch']}:{package['version']}-{package['release']}.{package['arch']}")

                for module_spec in itertools.chain(
                    transaction.get("module-enable-specs", []),
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
        for module_ns, (module, profiles) in modules.items():
            response["modules"][module.getName()] = {
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

        return response
