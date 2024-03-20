# Test repositories metadata

This directory is used for `osbuild-depsolve-dnf` unit tests.
Each subdirectory contains repository metadata that is served by a server during testing for `osbuild-depsolve-dnf` to query.
- `baseos`: CS9 BaseOS repository metadata.
- `custom`: a custom repository containing a single (empty) package, created with:

```bash
rpmdir=$(mktemp -d)
cat <<EOF > "${rpmdir}/nothing.spec"
#----------- spec file starts ---------------
Name:                   nothing
Version:                1.0.0
Release:                0
BuildArch:              noarch
Vendor:                 noone
Summary:                Provides %{name}
License:                BSD
Provides:               nothing

%description
%{summary}

%files
EOF

rpmbuild --quiet --define "_topdir ${rpmdir}" -bb "${rpmdir}/nothing.spec"
createrepo "${rpmdir}/RPMS/noarch/"
mkdir -p ./test/data/testrepos/custom
cp -a "${rpmdir}/RPMS/noarch/repodata" ./test/data/testrepos/custom
```
