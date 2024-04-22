#
# Maintenance Helpers
#
# This makefile contains targets used for development, as well as helpers to
# aid automatization of maintenance. Unless a target is documented in
# `make help`, it is not supported and is only meant to be used by developers
# to aid their daily development work.
#
# All supported targets honor the `SRCDIR` variable to find the source-tree.
# For most unsupported targets, you are expected to have the source-tree as
# your working directory. To specify a different source-tree, simply override
# the variable via `SRCDIR=<path>` on the commandline. While you can also
# override `BUILDDIR`, you are usually expected to have the build output
# directory as working directory.
#

BUILDDIR ?= .
SRCDIR ?= .

MKDIR ?= mkdir
PYTHON3 ?= python3
RST2MAN ?= rst2man
TAR ?= tar
WGET ?= wget

SHELL = /bin/bash

#
# Automatic Variables
#
# This section contains a bunch of automatic variables used all over the place.
# They mostly try to fetch information from the repository sources to avoid
# hard-coding them in this makefile.
#
# Most of the variables here are pre-fetched so they will only ever be
# evaluated once. This, however, means they are always executed regardless of
# which target is run.
#
#     VERSION:
#         This evaluates the `version` field of `setup.py`. Therefore, it will
#         be set to the latest version number of this repository without any
#         prefix (just a plain number).
#
#     COMMIT:
#         This evaluates to the latest git commit sha. This will not work if
#         the source is not a git checkout. Hence, this variable is not
#         pre-fetched but evaluated at time of use.
#

VERSION := $(shell (cd "$(SRCDIR)" && python3 setup.py --version))
COMMIT = $(shell (cd "$(SRCDIR)" && git rev-parse HEAD))

#
# Generic Targets
#
# The following is a set of generic targets used across the makefile. The
# following targets are defined:
#
#     help
#         This target prints all supported targets. It is meant as
#         documentation of targets we support and might use outside of this
#         repository.
#         This is also the default target.
#
#     $(BUILDDIR)/
#     $(BUILDDIR)/%/
#         This target simply creates the specified directory. It is limited to
#         the build-dir as a safety measure. Note that this requires you to use
#         a trailing slash after the directory to not mix it up with regular
#         files. Lastly, you mostly want this as order-only dependency, since
#         timestamps on directories do not affect their content.
#
#     FORCE
#         Dummy target to force .PHONY behavior. This is required if .PHONY is
#         not an option (e.g., due to implicit targets).
#

.PHONY: help
help:
	@echo "make [TARGETS...]"
	@echo
	@echo "This is the maintenance makefile of osbuild. The following"
	@echo "targets are available:"
	@echo
	@echo "    help:               Print this usage information."
	@echo "    man:                Generate all man-pages"
	@echo
	@echo "    lint:               Check the code with linter (tox)"
	@echo "    lint-quick:         Check the code with fast linters only (local)"
	@echo
	@echo "    coverity-download:  Force a new download of the coverity tool"
	@echo "    coverity-check:     Run the coverity test suite"
	@echo "    coverity-submit:    Run coverity and submit the results"
	@echo
	@echo "    test-all:           Run all tests"
	@echo "    test-data:          Generate test data"
	@echo "    test-module:        Run all module unit-tests"
	@echo "    test-stage:         Run all stage unit-tests"
	@echo "    test-run:           Run all osbuild pipeline tests"

$(BUILDDIR)/:
	mkdir -p "$@"

$(BUILDDIR)/%/:
	mkdir -p "$@"

FORCE:

#
# Documentation
#
# The following targets build the included documentation. This includes the
# packaged man-pages, but also all other kinds of documentation that needs to
# be generated. Note that these targets are relied upon by automatic
# deployments to our website, as well as package manager scripts.
#

MANPAGES_RST = $(wildcard $(SRCDIR)/docs/*.[0123456789].rst)
MANPAGES_TROFF = $(patsubst $(SRCDIR)/%.rst,$(BUILDDIR)/%,$(MANPAGES_RST))

$(MANPAGES_TROFF): $(BUILDDIR)/docs/%: $(SRCDIR)/docs/%.rst | $(BUILDDIR)/docs/
	$(RST2MAN) "$<" "$@"

.PHONY: man
man: $(MANPAGES_TROFF)

#
# Coverity
#
# Download the coverity analysis tool and run it on the repository, archive the
# analysis result and upload it to coverity. The target to do all of that is
# `coverity-submit`.
#
# Individual targets exist for the respective steps.
#
# Needs COVERITY_TOKEN and COVERITY_EMAIL to be set for downloading
# the analysis tool and submitting the final results.
#

COVERITY_URL = https://scan.coverity.com/download/linux64
COVERITY_TARFILE = coverity-tool.tar.gz

COVERITY_BUILDDIR = $(BUILDDIR)/coverity
COVERITY_TOOLTAR = $(COVERITY_BUILDDIR)/$(COVERITY_TARFILE)
COVERITY_TOOLDIR = $(COVERITY_BUILDDIR)/cov-analysis-linux64
COVERITY_ANALYSIS = $(COVERITY_BUILDDIR)/cov-analysis-osbuild.xz

.PHONY: coverity-token
coverity-token:
	$(if $(COVERITY_TOKEN),,$(error COVERITY_TOKEN must be set))

.PHONY: coverity-email
coverity-email:
	$(if $(COVERITY_EMAIL),,$(error COVERITY_EMAIL must be set))

.PHONY: coverity-download
coverity-download: | coverity-token $(COVERITY_BUILDDIR)/
	@$(RM) -rf "$(COVERITY_TOOLDIR)" "$(COVERITY_TOOLTAR)"
	@echo "Downloading $(COVERITY_TARFILE) from $(COVERITY_URL)..."
	@$(WGET) -q "$(COVERITY_URL)" --post-data "project=osbuild&token=$(COVERITY_TOKEN)" -O "$(COVERITY_TOOLTAR)"
	@echo "Extracting $(COVERITY_TARFILE)..."
	@$(MKDIR) -p "$(COVERITY_TOOLDIR)"
	@$(TAR) -xzf "$(COVERITY_TOOLTAR)" --strip 1 -C "$(COVERITY_TOOLDIR)"

$(COVERITY_TOOLTAR): | $(COVERITY_BUILDDIR)/
	@$(MAKE) --no-print-directory coverity-download

.PHONY: coverity-check
coverity-check: $(COVERITY_TOOLTAR)
	@echo "Running coverity suite..."
	@$(COVERITY_TOOLDIR)/bin/cov-build \
		--dir "$(COVERITY_BUILDDIR)/cov-int" \
		--no-command \
		--fs-capture-search "$(SRCDIR)" \
		--fs-capture-search-exclude-regex "$(COVERITY_BUILDDIR)"
	@echo "Compressing analysis results..."
	@$(TAR) -caf "$(COVERITY_ANALYSIS)" -C "$(COVERITY_BUILDDIR)" "cov-int"

$(COVERITY_ANALYSIS): | $(COVERITY_BUILDDIR)/
	@$(MAKE) --no-print-directory coverity-check

.PHONY: coverity-submit
coverity-submit: $(COVERITY_ANALYSIS) | coverity-email coverity-token
	@echo "Submitting $(COVERITY_ANALYSIS)..."
	@curl --form "token=$(COVERITY_TOKEN)" \
		--form "email=$(COVERITY_EMAIL)" \
		--form "file=@$(COVERITY_ANALYSIS)" \
		--form "version=main" \
		--form "description=$$(git describe)" \
		https://scan.coverity.com/builds?project=osbuild

.PHONY: coverity-clean
coverity-clean:
	@$(RM) -rfv "$(COVERITY_BUILDDIR)/cov-int" "$(COVERITY_ANALYSIS)"

.PHONY: coverity-clean-all
coverity-clean-all: coverity-clean
	@$(RM) -rfv "$(COVERITY_BUILDDIR)"

#
# Test Suite
#
# We use the python `unittest` module for all tests. All the test-sources are
# located in the `./test/` top-level directory, with `./test/mod/` for module
# unittests, `./test/run/` for osbuild pipeline runtime tests, and `./test/src/`
# for linters and other tests on the source code.
#

TEST_MANIFESTS_MPP = $(filter-out $(SRCDIR)/test/data/manifests/fedora-build.mpp.yaml, \
             $(wildcard $(SRCDIR)/test/data/manifests/*.mpp.yaml)) \
             $(wildcard $(SRCDIR)/test/data/assemblers/*.mpp.yaml) \
		     $(wildcard $(SRCDIR)/test/data/stages/*/*.mpp.yaml)
TEST_MANIFESTS_GEN = $(TEST_MANIFESTS_MPP:%.mpp.yaml=%.json)

.PHONY: $(TEST_MANIFESTS_GEN)
$(TEST_MANIFESTS_GEN): %.json: %.mpp.yaml
	$(SRCDIR)/tools/osbuild-mpp -I "$(SRCDIR)/test/data/manifests" "$<" "$@"

.PHONY: test-data
test-data: $(TEST_MANIFESTS_GEN)

.PHONY: test-module
test-module:
	@$(PYTHON3) -m pytest \
			$(SRCDIR)/test/mod \
			--rootdir=$(SRCDIR) \
			-v

.PHONY: test-stage
test-stage:
	@$(PYTHON3) -m pytest \
			$(SRCDIR)/stages/test \
			--rootdir=$(SRCDIR) \
			-v

.PHONY: test-run
test-run:
	@[[ $${EUID} -eq 0 ]] || (echo "Error: Root privileges required!"; exit 1)
	@$(PYTHON3) -m pytest \
			$(SRCDIR)/test/run \
			--rootdir=$(SRCDIR) \
			-v


.PHONY: test-all
test-all:
	@$(PYTHON3) -m pytest \
			--rootdir=$(SRCDIR) \
			-v

#
# Linting the code
#
# Just run `make lint` and see if our linters like your code. Linters run in an
# environment created by tox.
#

.PHONY: lint
lint:
	tox run-parallel -e ruff,pylint,autopep8,mypy,mypy-strict


#
# Quick-linting the code
#
# Just run `make lint-quick` and see if our linters like your code. Linters run locally
# and need to be installed. See also `lint`.
#
.PHONY: lint-quick
lint-quick:
	ruff check osbuild/ assemblers/* devices/* inputs/* mounts/* runners/* sources/*.* stages/*.* inputs/test/*.py stages/test/*.py sources/test/*.py test/

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

.PHONY: git-diff-check
git-diff-check:
	@git diff --exit-code
	@git diff --cached --exit-code

RPM_SPECFILE=rpmbuild/SPECS/osbuild-$(COMMIT).spec
RPM_TARBALL=rpmbuild/SOURCES/osbuild-$(COMMIT).tar.gz

$(RPM_SPECFILE):
	mkdir -p $(CURDIR)/rpmbuild/SPECS
	(echo "%global commit $(COMMIT)"; git show HEAD:osbuild.spec) > $(RPM_SPECFILE)

$(RPM_TARBALL):
	mkdir -p $(CURDIR)/rpmbuild/SOURCES
	git archive --prefix=osbuild-$(COMMIT)/ --format=tar.gz HEAD > $(RPM_TARBALL)

.PHONY: srpm
srpm: git-diff-check $(RPM_SPECFILE) $(RPM_TARBALL)
	rpmbuild -bs \
		--define "_topdir $(CURDIR)/rpmbuild" \
		$(RPM_SPECFILE)

.PHONY: rpm
rpm: git-diff-check $(RPM_SPECFILE) $(RPM_TARBALL)
	rpmbuild -bb $(RPMBUILD_ARGS) \
		--define "_topdir $(CURDIR)/rpmbuild" \
		$(RPM_SPECFILE)

#
# Releasing
#

NEXT_VERSION := $(shell expr "$(VERSION)" + 1)

.PHONY: bump-version
bump-version:
	sed -i "s|Version:\(\s*\)$(VERSION)|Version:\1$(NEXT_VERSION)|" osbuild.spec
	sed -i "s|Release:\(\s*\)[[:digit:]]\+|Release:\11|" osbuild.spec
	sed -i "s|version=\"$(VERSION)\"|version=\"$(NEXT_VERSION)\"|" setup.py
	sed -i "s|__version__ = \"$(VERSION)\"|__version__ = \"$(NEXT_VERSION)\"|" osbuild/__init__.py

.PHONY: format
format:
	autopep8 --in-place --max-line-length 120 -a -a -a -j0 -r .
