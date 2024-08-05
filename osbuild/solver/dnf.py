import os
import os.path
import tempfile
from datetime import datetime
from typing import List

import dnf
import hawkey

from osbuild.solver import DepsolveError, MarkingError, RepoError, SolverBase, modify_rootdir_path, read_keys


class DNF(SolverBase):
    def __init__(self, request, persistdir, cache_dir):
        arch = request["arch"]
        releasever = request.get("releasever")
        module_platform_id = request["module_platform_id"]
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

            self.base.fill_sack(load_system_repo=False)
        except dnf.exceptions.Error as e:
            raise RepoError(e) from e

    # pylint: disable=too-many-branches
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
        # # Return an empty list when 'transactions' key is missing or when it is None
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

                # depsolve the current transaction
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
        }
        return response
