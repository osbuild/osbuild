%global         forgeurl https://github.com/osbuild/osbuild

Version:        16

%forgemeta

%global         pypi_name osbuild
%global         pkgdir %{_prefix}/lib/%{pypi_name}

Name:           %{pypi_name}
Release:        1%{?dist}
License:        ASL 2.0

URL:            %{forgeurl}

Source0:        %{forgesource}
BuildArch:      noarch
Summary:        A build system for OS images

BuildRequires:  make
BuildRequires:  python3-devel
BuildRequires:  python3-docutils

Requires:       bash
Requires:       coreutils
Requires:       curl
Requires:       dnf
Requires:       e2fsprogs
Requires:       glibc
Requires:       policycoreutils
Requires:       qemu-img
Requires:       systemd
Requires:       systemd-container
Requires:       tar
Requires:       util-linux
Requires:       python3-%{pypi_name} = %{version}-%{release}

# Turn off dependency generators for assemblers, runners and stages.
# They run in a container, so there's no reason to generate dependencies
# from them. As of 2020-03-25 this filters out python3.6 dependency generated
# by rhel runner.
%global __requires_exclude_from ^%{pkgdir}/(assemblers|runners|stages)/.*$

%{?python_enable_dependency_generator}

%description
A build system for OS images

%package -n     python3-%{pypi_name}
Summary:        %{summary}
%{?python_provide:%python_provide python3-%{pypi_name}}

%description -n python3-%{pypi_name}
A build system for OS images

%package        ostree
Summary:        OSTree support
Requires:       %{name} = %{version}-%{release}
Requires:       ostree
Requires:       rpm-ostree

%description ostree
Contains the necessary stages, assembler and source
to build OSTree based images.

%prep
%forgesetup

%build
%py3_build
make man

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

# mount point for bind mounting the osbuild library
mkdir -p %{buildroot}%{pkgdir}/osbuild

# schemata
mkdir -p %{buildroot}%{_datadir}/osbuild/schemas
install -p -m 0755 $(find schemas/*.json) %{buildroot}%{_datadir}/osbuild/schemas
ln -s %{_datadir}/osbuild/schemas %{buildroot}%{pkgdir}/schemas

# documentation
mkdir -p %{buildroot}%{_mandir}/man1
mkdir -p %{buildroot}%{_mandir}/man5
install -p -m 0644 -t %{buildroot}%{_mandir}/man1/ docs/*.1
install -p -m 0644 -t %{buildroot}%{_mandir}/man5/ docs/*.5

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
# the following files are in the ostree sub-package
%exclude %{pkgdir}/assemblers/org.osbuild.ostree.commit
%exclude %{pkgdir}/sources/org.osbuild.ostree
%exclude %{pkgdir}/stages/org.osbuild.ostree
%exclude %{pkgdir}/stages/org.osbuild.rpm-ostree

%files -n       python3-%{pypi_name}
%license LICENSE
%doc README.md NEWS.md
%{python3_sitelib}/%{pypi_name}-*.egg-info/
%{python3_sitelib}/%{pypi_name}/

%files ostree
%{pkgdir}/assemblers/org.osbuild.ostree.commit
%{pkgdir}/sources/org.osbuild.ostree
%{pkgdir}/stages/org.osbuild.ostree
%{pkgdir}/stages/org.osbuild.rpm-ostree

%changelog
* Mon Aug 19 2019 Miro Hrončok <mhroncok@redhat.com> - 1-3
- Rebuilt for Python 3.8

* Mon Jul 29 2019 Martin Sehnoutka <msehnout@redhat.com> - 1-2
- update upstream URL to the new Github organization

* Wed Jul 17 2019 Martin Sehnoutka <msehnout@redhat.com> - 1-1
- Initial package
