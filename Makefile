PACKAGE_NAME=osbuild
VERSION=1

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
	find `pwd`/output -name '*.rpm' -printf '%f\n' -exec mv {} . \;
	rm -r "`pwd`/rpmbuild"
	rm -r "`pwd`/output"
	rm -r "`pwd`/build"

copy-rpms-to-test:
	cp *.rpm test/

vagrant-test: rpm copy-rpms-to-test
	- $(MAKE) -C test up
	- $(MAKE) -C test install-deps
	$(MAKE) -C test run-tests-remotely
