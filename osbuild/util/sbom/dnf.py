from datetime import datetime
from typing import Dict, List

import dnf
import hawkey

import osbuild.util.sbom.model as sbom_model


def bom_chksum_algorithm_from_hawkey(chksum_type: int) -> sbom_model.ChecksumAlgorithm:
    """
    Convert a hawkey checksum type number to an SBOM checksum algorithm.
    """
    if chksum_type == hawkey.CHKSUM_MD5:
        return sbom_model.ChecksumAlgorithm.MD5
    if chksum_type == hawkey.CHKSUM_SHA1:
        return sbom_model.ChecksumAlgorithm.SHA1
    if chksum_type == hawkey.CHKSUM_SHA256:
        return sbom_model.ChecksumAlgorithm.SHA256
    if chksum_type == hawkey.CHKSUM_SHA384:
        return sbom_model.ChecksumAlgorithm.SHA384
    if chksum_type == hawkey.CHKSUM_SHA512:
        return sbom_model.ChecksumAlgorithm.SHA512
    raise ValueError(f"Unknown Hawkey checksum type: {chksum_type}")


# pylint: disable=too-many-branches
def dnf_pkgset_to_sbom_pkgset(dnf_pkgset: List[dnf.package.Package]) -> List[sbom_model.BasePackage]:
    """
    Convert a dnf package set to a SBOM package set.
    """
    pkgs_by_name = {}
    pkgs_by_provides: Dict[str, List[sbom_model.BasePackage]] = {}

    for dnf_pkg in dnf_pkgset:
        pkg = sbom_model.RPMPackage(
            name=dnf_pkg.name,
            version=dnf_pkg.version,
            release=dnf_pkg.release,
            architecture=dnf_pkg.arch,
            epoch=dnf_pkg.epoch,
            license_declared=dnf_pkg.license,
            vendor=dnf_pkg.vendor,
            build_date=datetime.fromtimestamp(dnf_pkg.buildtime),
            summary=dnf_pkg.summary,
            description=dnf_pkg.description,
            source_rpm=dnf_pkg.sourcerpm,
            homepage=dnf_pkg.url,
        )

        if dnf_pkg.chksum:
            pkg.checksums = {
                bom_chksum_algorithm_from_hawkey(dnf_pkg.chksum[0]): dnf_pkg.chksum[1].hex()
            }

        if dnf_pkg.remote_location():
            pkg.download_url = dnf_pkg.remote_location()

        # if dnf_pkg.from_repo is empty, the pkg is not installed. determine from remote_location
        # if dnf_pkg.from_repo is "@commanddline", the pkg was installed from the command line, there is no repo URL
        # if dnf_pkg.reponame is "@System", the package is installed and there is no repo URL
        # if dnf_pkg.from_repo is a string with repo ID, determine the repo URL from the repo configuration
        if not dnf_pkg.from_repo and dnf_pkg.remote_location():
            pkg.repository_url = dnf_pkg.remote_location()[:-len("/" + dnf_pkg.relativepath)]
        elif dnf_pkg.from_repo != "@commandline" and dnf_pkg.reponame != "@System":
            repo_url = ""
            if dnf_pkg.repo.baseurl:
                repo_url = dnf_pkg.repo.baseurl
            elif dnf_pkg.repo.metalink:
                repo_url = dnf_pkg.repo.metalink
            elif dnf_pkg.repo.mirrorlist:
                repo_url = dnf_pkg.repo.mirrorlist
            pkg.repository_url = repo_url

        pkg.rpm_provides = [sbom_model.RPMDependency(r.name, r.relation, r.version) for r in dnf_pkg.provides]
        pkg.rpm_requires = [sbom_model.RPMDependency(r.name, r.relation, r.version) for r in dnf_pkg.requires]
        pkg.rpm_recommends = [sbom_model.RPMDependency(r.name, r.relation, r.version) for r in dnf_pkg.recommends]
        pkg.rpm_suggests = [sbom_model.RPMDependency(r.name, r.relation, r.version) for r in dnf_pkg.suggests]

        # The dnf_pkgset is not sorted by package dependencies. We need to determine relationships in two steps:
        # 1. Collect all packages that provide a certain capability
        # 2. Resolve dependencies for each package using previously constructed list of capabilities by package.
        # Doing this in two steps ensures that all soft dependencies satisfied by a package from the same set are
        # resolved.
        for provide in pkg.rpm_provides:
            pkgs_by_provides.setdefault(provide.name, []).append(pkg)
        # Packages can also depend directly on files provided by other packages. Collect these as well.
        for provided_file in dnf_pkg.files:
            pkgs_by_provides.setdefault(provided_file, []).append(pkg)

        pkgs_by_name[pkg.name] = pkg

    for pkg in pkgs_by_name.values():
        for require in pkg.rpm_requires:
            # skip conditional dependencies if the required package is not in the set
            # "relation" contains whitespace on both sides
            if require.relation.strip() == "if" and pkgs_by_name.get(require.version) is None:
                continue
            for provider_pkg in pkgs_by_provides.get(require.name, []):
                pkg.depends_on.add(provider_pkg)

        for soft_dep in pkg.rpm_recommends + pkg.rpm_suggests:
            for provider_pkg in pkgs_by_provides.get(soft_dep.name, []):
                pkg.optional_depends_on.add(provider_pkg)

    return list(pkgs_by_name.values())
