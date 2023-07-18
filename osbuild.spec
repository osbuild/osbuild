%global         forgeurl https://github.com/osbuild/osbuild
%global         selinuxtype targeted

Version:        91

%forgemeta

%global         pypi_name osbuild
%global         pkgdir %{_prefix}/lib/%{pypi_name}

Name:           %{pypi_name}
Release:        1%{?dist}
License:        Apache-2.0

URL:            %{forgeurl}

Source0:        %{forgesource}
BuildArch:      noarch
Summary:        A build system for OS images

BuildRequires:  make
BuildRequires:  python3-devel
BuildRequires:  python3-docutils
BuildRequires:  systemd

Requires:       bash
Requires:       bubblewrap
Requires:       coreutils
Requires:       curl
Requires:       dnf
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

%package        tools
Summary:        Extra tools and utilities
Requires:       %{name} = %{version}-%{release}
Requires:       python3-pyyaml

# These are required for `osbuild-dev`, only packaged for Fedora
%if 0%{?fedora}
Requires:       python3-rich
Requires:       python3-attrs
Requires:       python3-typer
%endif

%description    tools
Contains additional tools and utilities for development of
manifests and osbuild.

%prep
%forgeautosetup -p1

%build
%py3_build
make man

# SELinux
make -f /usr/share/selinux/devel/Makefile osbuild.pp
bzip2 -9 osbuild.pp

%pre selinux
%selinux_relabel_pre -s %{selinuxtype}

%install
%py3_install

mkdir -p %{buildroot}%{pkgdir}/stages
install -p -m 0755 $(find stages -type f) %{buildroot}%{pkgdir}/stages/

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
install -D -m 0644 -t %{buildroot}%{_mandir}/man8 selinux/%{name}_selinux.8
install -D -p -m 0644 selinux/osbuild.if %{buildroot}%{_datadir}/selinux/devel/include/distributed/%{name}.if

# Udev rules
mkdir -p %{buildroot}%{_udevrulesdir}
install -p -m 0755 data/10-osbuild-inhibitor.rules %{buildroot}%{_udevrulesdir}

# Remove `osbuild-dev` on non-fedora systems
%{!?fedora:rm %{buildroot}%{_bindir}/osbuild-dev}

%check
exit 0
# We have some integration tests, but those require running a VM, so that would
# be an overkill for RPM check script.

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
%exclude %{pkgdir}/stages/org.osbuild.rpm-ostree

%files -n       python3-%{pypi_name}
%license LICENSE
%doc README.md
%{python3_sitelib}/%{pypi_name}-*.egg-info/
%{python3_sitelib}/%{pypi_name}/

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

%files tools
%{_bindir}/osbuild-mpp
%{?fedora:%{_bindir}/osbuild-dev}


%changelog
* Mon Aug 19 2019 Miro Hrončok <mhroncok@redhat.com> - 1-3
- Rebuilt for Python 3.8

* Mon Jul 29 2019 Martin Sehnoutka <msehnout@redhat.com> - 1-2
- update upstream URL to the new Github organization

* Wed Jul 17 2019 Martin Sehnoutka <msehnout@redhat.com> - 1-1
- Initial package
