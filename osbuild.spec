%global         forgeurl https://github.com/osbuild/osbuild
%global         selinuxtype targeted

Version:        173
%global         osbuild_initrd_version 0.1

%forgemeta

%global         pypi_name osbuild
%global         pkgdir %{_prefix}/lib/%{pypi_name}
%global         debug_package %{nil}

Name:           %{pypi_name}
Release:        1%{?dist}
License:        Apache-2.0

URL:            %{forgeurl}

Source0:        %{forgesource}
Source1:        https://github.com/osbuild/initrd/releases/download/%{osbuild_initrd_version}/osbuild-initrd-%{osbuild_initrd_version}.tar.gz
Summary:        A build system for OS images

# There is no golang support for i686 on centos and RHEL
%if 0%{?rhel} || 0%{?centos}
ExcludeArch:    i686
%endif

BuildRequires:  make
BuildRequires:  python3-devel
BuildRequires:  python3-docutils
BuildRequires:  python3-setuptools
BuildRequires:  systemd

# for tests
BuildRequires:  python3-iniparse
BuildRequires:  python3-jsonschema
BuildRequires:  python3-kickstart
BuildRequires:  python3-mako
BuildRequires:  python3-PyYAML
BuildRequires:  python3-pytest
%if 0%{?fedora}
BuildRequires:  python3-license-expression
BuildRequires:  python3-pytest-xdist
BuildRequires:  python3-tomli-w
%endif

Requires:       bash
Requires:       bubblewrap
Requires:       coreutils
Requires:       curl
Requires:       e2fsprogs
Requires:       glibc
Requires:       policycoreutils
Requires:       qemu-img
Requires:       systemd
Requires:       skopeo
Requires:       tar
Requires:       util-linux
Requires:       python3-%{pypi_name} = %{version}-%{release}
Requires:       (%{name}-selinux if selinux-policy-%{selinuxtype})
Requires:       python3-librepo
Requires:       %{name}-initrd = %{version}-%{release}

# This is required for `osbuild`, for RHEL-10 and above
# the stdlib tomllib module can be used instead
%if 0%{?rhel} && 0%{?rhel} < 10
Requires:       python3-tomli
%endif

# Turn off dependency generators for runners. The reason is that runners are
# tailored to the platform, e.g. on RHEL they are using platform-python. We
# don't want to pick up those dependencies on other platform.
%global __requires_exclude_from ^%{pkgdir}/(runners)/.*$

# Turn off shebang mangling on RHEL. brp-mangle-shebangs (from package
# redhat-rpm-config) is run on all executables in a package after the `install`
# section runs. The below macro turns this behavior off for:
#   - runners, because they already have the correct shebang for the platform
#     they're meant for, and
#   - stages and assemblers, because they are run within osbuild build roots,
#     which are not required to contain the same OS as the host and might thus
#     have a different notion of "platform-python".
# RHEL NB: Since assemblers and stages are not excluded from the dependency
# generator, this also means that an additional dependency on /usr/bin/python3
# will be added. This is intended and needed, so that in the host build root
# /usr/bin/python3 is present so stages and assemblers can be run.
%global __brp_mangle_shebangs_exclude_from ^%{pkgdir}/(assemblers|runners|stages)/.*$

%{?python_enable_dependency_generator}

%description
A build system for OS images

%package -n     python3-%{pypi_name}
Summary:        %{summary}
%{?python_provide:%python_provide python3-%{pypi_name}}

%description -n python3-%{pypi_name}
A build system for OS images

%package        lvm2
Summary:        LVM2 support
Requires:       %{name} = %{version}-%{release}
Requires:       lvm2

%description lvm2
Contains the necessary stages and device host
services to build LVM2 based images.

%package        luks2
Summary:        LUKS2 support
Requires:       %{name} = %{version}-%{release}
Requires:       cryptsetup

%description luks2
Contains the necessary stages and device host
services to build LUKS2 encrypted images.

%package        ostree
Summary:        OSTree support
Requires:       %{name} = %{version}-%{release}
Requires:       ostree
Requires:       rpm-ostree

%description ostree
Contains the necessary stages, assembler and source
to build OSTree based images.

%package        initrd
Summary:        osbuild initrd for vm support
BuildRequires:  %{?go_compiler:compiler(go-compiler)}%{!?go_compiler:golang}

%description    initrd
Osbuild initrd used for in-vm support.

%package        selinux
Summary:        SELinux policies
Requires:       %{name} = %{version}-%{release}
Requires:       selinux-policy-%{selinuxtype}
Requires(post): selinux-policy-%{selinuxtype}
BuildRequires:  selinux-policy-devel
%{?selinux_requires}

%description    selinux
Contains the necessary SELinux policies that allows
osbuild to use labels unknown to the host inside the
containers it uses to build OS artifacts.

%package        container-selinux
Summary:        SELinux container policies
Requires:       selinux-policy-%{selinuxtype}
Requires:       container-selinux
Requires(post): selinux-policy-%{selinuxtype}
Requires(post): container-selinux
BuildRequires:  selinux-policy-devel
BuildRequires:  selinux-policy-devel
%{?selinux_requires}

%description    container-selinux
Contains the necessary SELinux policies that allows
running osbuild in a container.

%package        tools
Summary:        Extra tools and utilities
Requires:       %{name} = %{version}-%{release}
Requires:       python3-pyyaml
Requires:       python3-dnf

# These are required for `osbuild-dev`, only packaged for Fedora
%if 0%{?fedora}
Requires:       python3-rich
Requires:       python3-attrs
%if 0%{?fedora} > 40
Requires:       python3dist(typer-slim[standard])
%else
Requires:       python3-typer
%endif
%endif

%description    tools
Contains additional tools and utilities for development of
manifests and osbuild.

%package        depsolve-dnf
Summary:        Dependency solving support for DNF
Requires:       %{name} = %{version}-%{release}

# RHEL 11 and Fedora 41 and later use libdnf5, RHEL < 11 and Fedora < 41 use dnf
# On Fedora 41 however, we force dnf4 (and depend on python3-dnf) until dnf5 issues are resolved.
# See https://github.com/rpm-software-management/dnf5/issues/1748
# and https://issues.redhat.com/browse/COMPOSER-2361
%if 0%{?rhel} >= 11
Requires: python3-libdnf5 >= 5.2.1
%else
Requires: python3-dnf
%endif

%if 0%{?fedora}
# RHEL / CS does not have python3-license-expression
# It is needed for validating license expressions in RPM packages when generating SBOMs
# While SBOMs can be generated also without this package, it is recommended to have it.
Recommends: python3-license-expression
%endif

# osbuild 125 added a new "solver" field and osbuild-composer only
# supports this since 116
Conflicts: osbuild-composer <= 115

# XXX: remove this once the osbuild-dnf-json V1 API is removed (osbuild/solver/api/v1.py)
Provides: osbuild-dnf-json-api = 8

%description    depsolve-dnf
Contains depsolving capabilities for package managers.

%prep
%forgeautosetup -p1
tar xf %SOURCE1

%build
%py3_build
make man
(cd osbuild-initrd-%{osbuild_initrd_version}; make build)

# SELinux
make -f /usr/share/selinux/devel/Makefile osbuild.pp
bzip2 -9 osbuild.pp

make -f /usr/share/selinux/devel/Makefile osbuild-container.pp
bzip2 -9 osbuild-container.pp

%pre selinux
%selinux_relabel_pre -s %{selinuxtype}

%install
%py3_install
(cd osbuild-initrd-%{osbuild_initrd_version}; %make_install)

# Ensure vm.py is executable which is needed to run in with init= in the vm
chmod 0755 %{buildroot}%{python3_sitelib}/%{pypi_name}/vm.py

mkdir -p %{buildroot}%{pkgdir}/stages
install -p -m 0755 $(find stages -type f -not -name "test_*.py") %{buildroot}%{pkgdir}/stages/

mkdir -p %{buildroot}%{pkgdir}/assemblers
install -p -m 0755 $(find assemblers -type f) %{buildroot}%{pkgdir}/assemblers/

mkdir -p %{buildroot}%{pkgdir}/runners
install -p -m 0755 $(find runners -type f -or -type l) %{buildroot}%{pkgdir}/runners

mkdir -p %{buildroot}%{pkgdir}/sources
install -p -m 0755 $(find sources -type f) %{buildroot}%{pkgdir}/sources

mkdir -p %{buildroot}%{pkgdir}/devices
install -p -m 0755 $(find devices -type f) %{buildroot}%{pkgdir}/devices

mkdir -p %{buildroot}%{pkgdir}/inputs
install -p -m 0755 $(find inputs -type f) %{buildroot}%{pkgdir}/inputs

mkdir -p %{buildroot}%{pkgdir}/mounts
install -p -m 0755 $(find mounts -type f) %{buildroot}%{pkgdir}/mounts

# mount point for bind mounting the osbuild library
mkdir -p %{buildroot}%{pkgdir}/osbuild

# schemata
mkdir -p %{buildroot}%{_datadir}/osbuild/schemas
install -p -m 0644 $(find schemas/*.json) %{buildroot}%{_datadir}/osbuild/schemas
ln -s %{_datadir}/osbuild/schemas %{buildroot}%{pkgdir}/schemas

# documentation
mkdir -p %{buildroot}%{_mandir}/man1
mkdir -p %{buildroot}%{_mandir}/man5
install -p -m 0644 -t %{buildroot}%{_mandir}/man1/ docs/*.1
install -p -m 0644 -t %{buildroot}%{_mandir}/man5/ docs/*.5

# SELinux
install -D -m 0644 -t %{buildroot}%{_datadir}/selinux/packages/%{selinuxtype} %{name}.pp.bz2
install -D -m 0644 -t %{buildroot}%{_datadir}/selinux/packages/%{selinuxtype} %{name}-container.pp.bz2
install -D -m 0644 -t %{buildroot}%{_mandir}/man8 selinux/%{name}_selinux.8
install -D -p -m 0644 selinux/osbuild.if %{buildroot}%{_datadir}/selinux/devel/include/distributed/%{name}.if

# Udev rules
mkdir -p %{buildroot}%{_udevrulesdir}
install -p -m 0755 data/10-osbuild-inhibitor.rules %{buildroot}%{_udevrulesdir}

# Remove `osbuild-dev` on non-fedora systems
%{!?fedora:rm %{buildroot}%{_bindir}/osbuild-dev}

# Install `osbuild-depsolve-dnf` into libexec
mkdir -p %{buildroot}%{_libexecdir}
install -p -m 0755 tools/osbuild-depsolve-dnf %{buildroot}%{_libexecdir}/osbuild-depsolve-dnf

# Configure the solver for dnf
mkdir -p %{buildroot}%{_datadir}/osbuild
# RHEL 11 and Fedora 41 and later use dnf5, RHEL < 11 and Fedora < 41 use dnf
# On Fedora 41 however, we force dnf4 (and depend on python3-dnf) until dnf5 issues are resolved.
# See https://github.com/rpm-software-management/dnf5/issues/1748
# and https://issues.redhat.com/browse/COMPOSER-2361
%if 0%{?rhel} >= 11
install -p -m 0644 tools/solver-dnf5.json %{buildroot}%{pkgdir}/solver.json
%else
install -p -m 0644 tools/solver-dnf.json %{buildroot}%{pkgdir}/solver.json
%endif

%if 0%{?fedora} || 0%{?rhel} >= 9
%check
# skip toml-writing tests in RHEL (no such library available there)
# There is a bunch of tests failing on specific arch/OS combinations.
# osbuild is a noarch package, meaning the architecture conditionals don't work.
# The details of the failing tests are described in the comments.
# Since we can't be granular enough, skip tests based on the OS only.
# This means some tests won't be run even though they could,
# but that's an acceptable tradeoff.
ignore_files=()
skip_tests=()

# x86_64-specific tests:
# test/mod/test_util_sbom_spdx.py
# test/mod/test_util_sbom_dnf.py
# test/mod/test_testutil_dnf4.py
# test/mod/test_solver_implementations.py
%ifnarch x86_64
ignore_files+=(
    test/mod/test_util_sbom_spdx.py
    test/mod/test_util_sbom_dnf.py
    test/mod/test_testutil_dnf4.py
    test/mod/test_solver_implementations.py
)
%endif

# fails on s390x:
# test_ioctl_toggle_immutable
# test_rmtree_immutable
%ifarch s390x
skip_tests+=(
    test_ioctl_toggle_immutable
    test_rmtree_immutable
)
%endif

# fails on ppc64le:
# TestAPI.test_exception - https://github.com/osbuild/osbuild/issues/2337
# TestUtilJsonComm.test_send_and_recv_tons_of_data_is_fine - https://github.com/osbuild/osbuild/issues/2336
# TestUtilJsonComm.test_sendmsg_errors_with_size_on_EMSGSIZE - https://github.com/osbuild/osbuild/issues/2342
%ifarch ppc64le
skip_tests+=(
    "(TestAPI and test_exception)"
    "(TestUtilJsonComm and test_send_and_recv_tons_of_data_is_fine)"
    "(TestUtilJsonComm and test_sendmsg_errors_with_size_on_EMSGSIZE)"
)
%endif

# fails on ppc64le and aarch64:
# test_cache_full_behavior
%ifarch ppc64le || aarch64
skip_tests+=(
    test_cache_full_behavior
)
%endif

# fails on C9S and EPEL9:
# tools/test/test_depsolve.py
# test_dnf4_pkg_to_package - https://github.com/osbuild/osbuild/issues/2339
%if 0%{?rhel} && 0%{?rhel} < 10
ignore_files+=(
    tools/test/test_depsolve.py
)
skip_tests+=(
    test_dnf4_pkg_to_package
)
%endif

ignore_args=()
for file in "${ignore_files[@]}"; do
    ignore_args+=(--ignore "$file")
done

skip_test_expr=""
for test in "${skip_tests[@]}"; do
    if [ "$skip_test_expr" != "" ]; then
        skip_test_expr+=" and not $test"
    else
        skip_test_expr+="not $test"
    fi
done

%pytest %{?fedora:-n auto} -v %{?rhel:-m "not tomlwrite"} ${ignore_args[@]} -k "${skip_test_expr}"
%endif

%files
%license LICENSE
%{_bindir}/osbuild
%{_mandir}/man1/%{name}.1*
%{_mandir}/man5/%{name}-manifest.5*
%{_datadir}/osbuild/schemas
%{pkgdir}
%{_udevrulesdir}/*.rules
# the following files are in the lvm2 sub-package
%exclude %{pkgdir}/devices/org.osbuild.lvm2*
%exclude %{pkgdir}/stages/org.osbuild.lvm2*
# the following files are in the luks2 sub-package
%exclude %{pkgdir}/devices/org.osbuild.luks2*
%exclude %{pkgdir}/stages/org.osbuild.crypttab
%exclude %{pkgdir}/stages/org.osbuild.luks2*
# the following files are in the ostree sub-package
%exclude %{pkgdir}/assemblers/org.osbuild.ostree*
%exclude %{pkgdir}/inputs/org.osbuild.ostree*
%exclude %{pkgdir}/sources/org.osbuild.ostree*
%exclude %{pkgdir}/stages/org.osbuild.ostree*
%exclude %{pkgdir}/stages/org.osbuild.experimental.ostree*
%exclude %{pkgdir}/stages/org.osbuild.rpm-ostree

%files -n       python3-%{pypi_name}
%license LICENSE
%doc README.md
%{python3_sitelib}/%{pypi_name}-*.egg-info/
%{python3_sitelib}/%{pypi_name}/

%files initrd
%{pkgdir}/initrd

%files lvm2
%{pkgdir}/devices/org.osbuild.lvm2*
%{pkgdir}/stages/org.osbuild.lvm2*

%files luks2
%{pkgdir}/devices/org.osbuild.luks2*
%{pkgdir}/stages/org.osbuild.crypttab
%{pkgdir}/stages/org.osbuild.luks2*

%files ostree
%{pkgdir}/assemblers/org.osbuild.ostree*
%{pkgdir}/inputs/org.osbuild.ostree*
%{pkgdir}/sources/org.osbuild.ostree*
%{pkgdir}/stages/org.osbuild.ostree*
%{pkgdir}/stages/org.osbuild.experimental.ostree*
%{pkgdir}/stages/org.osbuild.rpm-ostree

%files selinux
%{_datadir}/selinux/packages/%{selinuxtype}/%{name}.pp.bz2
%{_mandir}/man8/%{name}_selinux.8.*
%{_datadir}/selinux/devel/include/distributed/%{name}.if
%ghost %verify(not md5 size mode mtime) %{_sharedstatedir}/selinux/%{selinuxtype}/active/modules/200/%{name}

%post selinux
%selinux_modules_install -s %{selinuxtype} %{_datadir}/selinux/packages/%{selinuxtype}/%{name}.pp.bz2

%postun selinux
if [ $1 -eq 0 ]; then
    %selinux_modules_uninstall -s %{selinuxtype} %{name}
fi

%posttrans selinux
%selinux_relabel_post -s %{selinuxtype}

%files container-selinux
%{_datadir}/selinux/packages/%{selinuxtype}/%{name}-container.pp.bz2
%ghost %verify(not md5 size mode mtime) %{_sharedstatedir}/selinux/%{selinuxtype}/active/modules/200/%{name}-container

%post container-selinux
%selinux_modules_install -s %{selinuxtype} %{_datadir}/selinux/packages/%{selinuxtype}/%{name}-container.pp.bz2

%postun container-selinux
if [ $1 -eq 0 ]; then
    %selinux_modules_uninstall -s %{selinuxtype} %{name}-container
fi

%files tools
%{_bindir}/osbuild-image-info
%{_bindir}/osbuild-mpp
%{?fedora:%{_bindir}/osbuild-dev}

%files depsolve-dnf
%{_libexecdir}/osbuild-depsolve-dnf
%{pkgdir}/solver.json

%changelog
* Mon Aug 19 2019 Miro Hrončok <mhroncok@redhat.com> - 1-3
- Rebuilt for Python 3.8

* Mon Jul 29 2019 Martin Sehnoutka <msehnout@redhat.com> - 1-2
- update upstream URL to the new Github organization

* Wed Jul 17 2019 Martin Sehnoutka <msehnout@redhat.com> - 1-1
- Initial package
