VERSION := $(shell python3 setup.py --version)
NEXT_VERSION := $(shell expr "$(VERSION)" + 1)
COMMIT=$(shell git rev-parse HEAD)

#
# Building packages
#
# The following rules build osbuild packages from the current HEAD commit,
# based on the spec file in this directory. The resulting packages have the
# commit hash in their version, so that they don't get overwritten when calling
# `make rpm` again after switching to another branch.
#
# All resulting files (spec files, source rpms, rpms) are written into
# ./rpmbuild, using rpmbuild's usual directory structure.
#

RPM_SPECFILE=rpmbuild/SPECS/osbuild-$(COMMIT).spec
RPM_TARBALL=rpmbuild/SOURCES/osbuild-$(COMMIT).tar.gz

$(RPM_SPECFILE):
	mkdir -p $(CURDIR)/rpmbuild/SPECS
	(echo "%global commit $(COMMIT)"; git show HEAD:osbuild.spec) > $(RPM_SPECFILE)

$(RPM_TARBALL):
	mkdir -p $(CURDIR)/rpmbuild/SOURCES
	git archive --prefix=osbuild-$(COMMIT)/ --format=tar.gz HEAD > $(RPM_TARBALL)

.PHONY: srpm
srpm: $(RPM_SPECFILE) $(RPM_TARBALL)
	rpmbuild -bs \
		--define "_topdir $(CURDIR)/rpmbuild" \
		$(RPM_SPECFILE)

.PHONY: rpm
rpm: $(RPM_SPECFILE) $(RPM_TARBALL)
	rpmbuild -bb \
		--define "_topdir $(CURDIR)/rpmbuild" \
		$(RPM_SPECFILE)

#
# Releasing
#

.PHONY: bump-version
bump-version:
	sed -i "s|Version:\(\s*\)$(VERSION)|Version:\1$(NEXT_VERSION)|" osbuild.spec
	sed -i "s|Release:\(\s*\)[[:digit:]]\+|Release:\11|" osbuild.spec
	sed -i "s|version=\"$(VERSION)\"|version=\"$(NEXT_VERSION)\"|" setup.py
