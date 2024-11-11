from datetime import datetime
from typing import Dict, List

import libdnf5

import osbuild.util.sbom.model as sbom_model


def bom_chksum_algorithm_from_libdnf5(chksum_type: int) -> sbom_model.ChecksumAlgorithm:
    """
    Convert a hawkey checksum type number to an SBOM checksum algorithm.
    """
    if chksum_type == libdnf5.rpm.Checksum.Type_MD5:
        return sbom_model.ChecksumAlgorithm.MD5
    if chksum_type == libdnf5.rpm.Checksum.Type_SHA1:
        return sbom_model.ChecksumAlgorithm.SHA1
    if chksum_type == libdnf5.rpm.Checksum.Type_SHA224:
        return sbom_model.ChecksumAlgorithm.SHA224
    if chksum_type == libdnf5.rpm.Checksum.Type_SHA256:
        return sbom_model.ChecksumAlgorithm.SHA256
    if chksum_type == libdnf5.rpm.Checksum.Type_SHA384:
        return sbom_model.ChecksumAlgorithm.SHA384
    if chksum_type == libdnf5.rpm.Checksum.Type_SHA512:
        return sbom_model.ChecksumAlgorithm.SHA512
    raise ValueError(f"Unknown libdnf5 checksum type: {chksum_type}")


def _libdnf5_reldep_to_rpmdependency(reldep: libdnf5.rpm.Reldep) -> sbom_model.RPMDependency:
    """
    Convert a libdnf5.rpm.Reldep to an SBOM RPM dependency.
    """
    return sbom_model.RPMDependency(reldep.get_name(), reldep.get_relation(), reldep.get_version())


# pylint: disable=too-many-branches
def dnf_pkgset_to_sbom_pkgset(dnf_pkgset: List[libdnf5.rpm.Package]) -> List[sbom_model.BasePackage]:
    """
    Convert a dnf5 package set to a SBOM package set.
    """
    pkgs_by_name = {}
    pkgs_by_provides: Dict[str, List[sbom_model.BasePackage]] = {}

    for dnf_pkg in dnf_pkgset:
        pkg = sbom_model.RPMPackage(
            name=dnf_pkg.get_name(),
            version=dnf_pkg.get_version(),
            release=dnf_pkg.get_release(),
            architecture=dnf_pkg.get_arch(),
            epoch=dnf_pkg.get_epoch(),
            license_declared=dnf_pkg.get_license(),
            vendor=dnf_pkg.get_vendor(),
            build_date=datetime.fromtimestamp(dnf_pkg.get_build_time()),
            summary=dnf_pkg.get_summary(),
            description=dnf_pkg.get_description(),
            source_rpm=dnf_pkg.get_sourcerpm(),
            homepage=dnf_pkg.get_url(),
        )

        dnf_pkg_checksum = dnf_pkg.get_checksum()
        if dnf_pkg_checksum and dnf_pkg_checksum.get_type() != libdnf5.rpm.Checksum.Type_UNKNOWN:
            pkg.checksums = {
                bom_chksum_algorithm_from_libdnf5(dnf_pkg_checksum.get_type()): dnf_pkg_checksum.get_checksum()
            }

        if len(dnf_pkg.get_remote_locations()) > 0:
            # NB: libdnf5 will return all remote locations (mirrors) for a package.
            # In reality, the first one is the repo which metadata were used to
            # resolve the package. DNF4 behavior would be to return just the first
            # remote location, so we do the same here.
            pkg.download_url = dnf_pkg.get_remote_locations()[0]

        # if dnf_pkg.get_from_repo_id() returns an empty string, the pkg is not installed. determine from remote_location
        # if dnf_pkg.get_from_repo_id() returns "@commanddline", the pkg was installed from the command line, there is no repo URL
        # if dnf_pkg.get_from_repo_id() returns "@System", the package is installed and there is no repo URL
        # if dnf_pkg.get_from_repo_id() returns "<unknown>", the package is installed and there is no repo URL

        # if dnf_pkg.get_from_repo_id() returns a string with repo ID, determine
        # the repo URL from the repo configuration
        if not dnf_pkg.get_from_repo_id() and len(dnf_pkg.get_remote_locations()) > 0:
            # NB: libdnf5 will return all remote locations (mirrors) for a package.
            # In reality, the first one is the repo which metadata were used to
            # resolve the package. DNF4 behavior would be to return just the first
            # remote location, so we do the same here.
            pkg.repository_url = dnf_pkg.get_remote_locations()[0][:-len("/" + dnf_pkg.get_location())]
        elif dnf_pkg.get_from_repo_id() not in ("@commandline", "@System", "<unknown>"):
            repo_url = ""
            repo_config = dnf_pkg.get_repo().get_config()
            # NB: checking only the empty() method is not enough, because of:
            # https://github.com/rpm-software-management/dnf5/issues/1859
            if not repo_config.get_baseurl_option().empty() and len(repo_config.get_baseurl_option().get_value()) > 0:
                repo_url = repo_config.get_baseurl_option().get_value_string()
            elif not repo_config.get_metalink_option().empty():
                repo_url = repo_config.get_metalink_option().get_value_string()
            elif not repo_config.get_mirrorlist_option().empty():
                repo_url = repo_config.get_mirrorlist_option().get_value_string()
            pkg.repository_url = repo_url

        pkg.rpm_provides = [_libdnf5_reldep_to_rpmdependency(r) for r in dnf_pkg.get_provides()]
        pkg.rpm_requires = [_libdnf5_reldep_to_rpmdependency(r) for r in dnf_pkg.get_requires()]
        pkg.rpm_recommends = [_libdnf5_reldep_to_rpmdependency(r) for r in dnf_pkg.get_recommends()]
        pkg.rpm_suggests = [_libdnf5_reldep_to_rpmdependency(r) for r in dnf_pkg.get_suggests()]

        # The dnf_pkgset is not sorted by package dependencies. We need to determine relationships in two steps:
        # 1. Collect all packages that provide a certain capability
        # 2. Resolve dependencies for each package using previously constructed list of capabilities by package.
        # Doing this in two steps ensures that all soft dependencies satisfied by a package from the same set are
        # resolved.
        for provide in pkg.rpm_provides:
            pkgs_by_provides.setdefault(provide.name, []).append(pkg)
        # Packages can also depend directly on files provided by other packages. Collect these as well.
        for provided_file in dnf_pkg.get_files():
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
