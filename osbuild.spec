%global         pypi_name osbuild
%global         pkgdir %{_prefix}/lib/%{pypi_name}

Name:           %{pypi_name}
Version:        7
Release:        1%{?dist}
License:        ASL 2.0

URL:            https://github.com/osbuild/osbuild

Source0:        https://github.com/osbuild/%{pypi_name}/archive/%{version}.tar.gz
BuildArch:      noarch
Summary:        A build system for OS images

BuildRequires:  python3-devel

Requires: bash
Requires: coreutils
Requires: dnf
Requires: e2fsprogs
Requires: glibc
Requires: policycoreutils
Requires: qemu-img
Requires: systemd
Requires: systemd-container
Requires: tar
Requires: util-linux
Requires: python3-%{pypi_name}

%{?python_enable_dependency_generator}

%description
A build system for OS images

%package -n     python3-%{pypi_name}
Summary:        %{summary}
%{?python_provide:%python_provide python3-%{pypi_name}}

%description -n     python3-%{pypi_name}
A build system for OS images

%prep
%autosetup -n %{name}-%{version}

%build
%py3_build

%install
%py3_install

# install host runner
%if 0%{?fc30}
ln -s org.osbuild.fedora30 %{buildroot}%{pkgdir}/runners/org.osbuild.host
%endif
%if 0%{?fc31}
ln -s org.osbuild.fedora31 %{buildroot}%{pkgdir}/runners/org.osbuild.host
%endif
%if 0%{?fc32}
ln -s org.osbuild.fedora32 %{buildroot}%{pkgdir}/runners/org.osbuild.host
%endif
%if 0%{?el8}
ln -s org.osbuild.rhel82 %{buildroot}%{pkgdir}/runners/org.osbuild.host
%endif

%check
exit 0
# We have some integration tests, but those require running a VM, so that would
# be an overkill for RPM check script.

%files
%license LICENSE
%{_bindir}/osbuild
%{pkgdir}

%files -n     python3-%{pypi_name}
%license LICENSE
%doc README.md
%{python3_sitelib}/%{pypi_name}-*.egg-info/
%{python3_sitelib}/%{pypi_name}/

%changelog
* Mon Aug 19 2019 Miro Hrončok <mhroncok@redhat.com> - 1-3
- Rebuilt for Python 3.8

* Mon Jul 29 2019 Martin Sehnoutka <msehnout@redhat.com> - 1-2
- update upstream URL to the new Github organization

* Wed Jul 17 2019 Martin Sehnoutka <msehnout@redhat.com> - 1-1
- Initial package
