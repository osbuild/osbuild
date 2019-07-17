%global         pypi_name osbuild

Name:           %{pypi_name}
Version:        1
Release:        1%{?dist}
License:        ASL 2.0

URL:            https://github.com/larskarlitski/osbuild

Source0:        https://github.com/larskarlitski/%{pypi_name}/archive/%{version}.tar.gz
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

mkdir -p %{buildroot}%{_libexecdir}/%{pypi_name}/stages
install -p -m 0755 stages/* %{buildroot}%{_libexecdir}/%{pypi_name}/stages/

mkdir -p %{buildroot}%{_libexecdir}/%{pypi_name}/assemblers
install -p -m 0755 assemblers/* %{buildroot}%{_libexecdir}/%{pypi_name}/assemblers/

install -p -m 0755 osbuild-run %{buildroot}%{_libexecdir}/%{pypi_name}/

%check
exit 0
# We have some integration tests, but those require running a VM, so that would
# be an overkill for RPM check script.

%files
%license LICENSE
%{_bindir}/osbuild
%{_libexecdir}/%{pypi_name}

%files -n     python3-%{pypi_name}
%license LICENSE
%doc README.md
%{python3_sitelib}/%{pypi_name}-*.egg-info/
%{python3_sitelib}/%{pypi_name}/

%changelog
* Wed Jul 17 2019 Martin Sehnoutka <msehnout@redhat.com> - 1-1
- Initial package
