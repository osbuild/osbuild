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

RST2MAN ?= rst2man

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

.PHONY: help
help:
	@echo "make [TARGETS...]"
	@echo
	@echo "This is the maintenance makefile of osbuild. The following"
	@echo "targets are available:"
	@echo
	@echo "    help:               Print this usage information."
	@echo "    man:                Generate all man-pages"

$(BUILDDIR)/:
	mkdir -p "$@"

$(BUILDDIR)/%/:
	mkdir -p "$@"

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

NEXT_VERSION := $(shell expr "$(VERSION)" + 1)

.PHONY: bump-version
bump-version:
	sed -i "s|Version:\(\s*\)$(VERSION)|Version:\1$(NEXT_VERSION)|" osbuild.spec
	sed -i "s|Release:\(\s*\)[[:digit:]]\+|Release:\11|" osbuild.spec
	sed -i "s|version=\"$(VERSION)\"|version=\"$(NEXT_VERSION)\"|" setup.py

.PHONY: release
release:
	@echo
	@echo "Checklist for release of osbuild-$(NEXT_VERSION):"
	@echo
	@echo " * Create news entry in NEWS.md with a short description of"
	@echo "   any changes since the last release, which are relevant to"
	@echo "   users, packagers, distributors, or dependent projects."
	@echo
	@echo "   Use the following template, break lines at 80ch:"
	@echo
	@echo "--------------------------------------------------------------------------------"
	@echo "## CHANGES WITH $(NEXT_VERSION):"
	@echo
	@echo "        * ..."
	@echo
	@echo "        * ..."
	@echo
	@echo -n "        Contributions from: "
	# We omit the contributor list if `git log` fails. If you hit this,
	# consider fetching missing tags via `git fetch --tags`, or just copy
	# this command and remove the stderr-redirect.
	@echo `( git log --format='%an, ' v$(VERSION)..HEAD 2>/dev/null | sort -u | tr -d '\n' | sed 's/, $$//' ) || echo`
	@echo
	@echo "        - Location, YYYY-MM-DD"
	@echo "--------------------------------------------------------------------------------"
	@echo
	@echo "   To get a list of changes since the last release, you may use:"
	@echo
	@echo "        git log v$(VERSION)..HEAD"
	@echo
	@echo " * Bump the project version. The canonical location is"
	@echo "   'setup.py', but 'osbuild.spec' needs to be updated as well."
	@echo "   You can use the following make-target to automate this:"
	@echo
	@echo "        make bump-version"
	@echo
	@echo " * Make sure the spec-file is updated for the new release and"
	@echo "   correctly supports all new features. This should already be"
	@echo "   done by previous commits that introduced the changes, but"
	@echo "   a sanity check does not hurt."
	@echo
	@echo " * Commit the version bump, spec-file changes and NEWS.md in any"
	@echo "   order you want."
	@echo
	@echo " * Tag the release via:"
	@echo
	@echo "        git tag -s -m 'osbuild $(NEXT_VERSION)' v$(NEXT_VERSION) HEAD"
	@echo
	@echo " * Push master as well as the tag:"
	@echo
	@echo "        git push origin master"
	@echo "        git push origin v$(NEXT_VERSION)"
	@echo
	@echo " * Create a release on github. Use 'NEWS.md' verbatim from the"
	@echo "   top until the end of the section for this release as release"
	@echo "   notes. Use 'v$(NEXT_VERSION)' as release name and as tag for"
	@echo "   the release."
	@echo
