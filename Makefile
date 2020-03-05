VERSION := $(shell python3 setup.py --version)
NEXT_VERSION := $(shell expr "$(VERSION)" + 1)
COMMIT=$(shell git rev-parse HEAD)

.PHONY: sdist copy-rpms-to-test check-working-directory vagrant-test vagrant-test-keep-running bump-version

sdist:
	python3 setup.py sdist
	find `pwd`/dist -name '*.tar.gz' -printf '%f\n' -exec mv {} . \;

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
# Vagrant
#

copy-rpms-to-test: rpm
	- rm test/testing-rpms/*.rpm
	find `pwd`/output -name '*.rpm' -printf '%f\n' -exec cp {} test/testing-rpms/ \;

check-working-directory:
	@if [ "`git status --porcelain --untracked-files=no | wc -l`" != "0" ]; then \
	  echo "Uncommited changes, refusing (Use git add . && git commit or git stash to clean your working directory)."; \
	  exit 1; \
	fi

vagrant-test: check-working-directory copy-rpms-to-test
	- $(MAKE) -C test destroy
	- $(MAKE) -C test up
	$(MAKE) -C test run-tests-remotely
	- $(MAKE) -C test destroy

vagrant-test-keep-running: check-working-directory copy-rpms-to-test
	- $(MAKE) -C test up
	- $(MAKE) -C test install-deps
	$(MAKE) -C test run-tests-remotely

bump-version:
	sed -i "s|Version:\(\s*\)$(VERSION)|Version:\1$(NEXT_VERSION)|" osbuild.spec
	sed -i "s|Release:\(\s*\)[[:digit:]]\+|Release:\11|" osbuild.spec
	sed -i "s|version=\"$(VERSION)\"|version=\"$(NEXT_VERSION)\"|" setup.py
