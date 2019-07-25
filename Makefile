PACKAGE_NAME=osbuild
VERSION=1

.PHONY: sdist tarball srpm rpm copy-rpms-to-test check-working-directory vagrant-test vagrant-test-keep-running

sdist:
	python3 setup.py sdist
	find `pwd`/dist -name '*.tar.gz' -printf '%f\n' -exec mv {} . \;

tarball:
	git archive --prefix=osbuild-$(VERSION)/ --format=tar.gz HEAD > $(VERSION).tar.gz

srpm: $(PACKAGE_NAME).spec tarball
	/usr/bin/rpmbuild -bs \
	  --define "_sourcedir $(CURDIR)" \
	  --define "_srcrpmdir $(CURDIR)" \
	  $(PACKAGE_NAME).spec

rpm: $(PACKAGE_NAME).spec tarball
	- rm -r "`pwd`/output"
	mkdir -p "`pwd`/output"
	mkdir -p "`pwd`/rpmbuild"
	/usr/bin/rpmbuild -bb \
	  --define "_sourcedir `pwd`" \
	  --define "_specdir `pwd`" \
	  --define "_builddir `pwd`/rpmbuild" \
	  --define "_srcrpmdir `pwd`" \
	  --define "_rpmdir `pwd`/output" \
	  --define "_buildrootdir `pwd`/build" \
	  $(PACKAGE_NAME).spec
	rm -r "`pwd`/rpmbuild"
	rm -r "`pwd`/build"

rpm-nodeps: $(PACKAGE_NAME).spec tarball
	- rm -r "`pwd`/output"
	mkdir -p "`pwd`/output"
	mkdir -p "`pwd`/rpmbuild"
	/usr/bin/rpmbuild -bb \
	  --nodeps \
	  --define "_sourcedir `pwd`" \
	  --define "_specdir `pwd`" \
	  --define "_builddir `pwd`/rpmbuild" \
	  --define "_srcrpmdir `pwd`" \
	  --define "_rpmdir `pwd`/output" \
	  --define "_buildrootdir `pwd`/build" \
	  $(PACKAGE_NAME).spec
	rm -r "`pwd`/rpmbuild"
	rm -r "`pwd`/build"

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
