OSBuild Test Data
=================

This directory contains data used by the osbuild test-suite. Since many formats
do not allow comments, this file shortly describes their purpose.

### Directories

 * `./os-release/`:
   This directory is consumed by the unit-tests of the `os-release` parser. The
   directory contains example os-release files (see `os-release(5)`). Their
   directory name is the expected output of the parser.

 * `./manifests/`:
   This directory contains osbuild manifests used throughout the test-suite.

   Manifests prefixed with `f30`, `f31`, etc. are manifests that produce fedora
   images. If they have `base` as part of their name, they include a base set
   of packages which we very loosely define as `@core` plus the packages our
   test-suite needs.
   If they have `build` as part of their name, they have a very restricted
   package set which includes just what is needed in a build-root for osbuild.
   The `fedora` prefix is used for manifests that are kept up to date to the
   newest fedora release, and thus do not expose a specific `f30`, `f32`, etc.
   behavior.

   The `rhel` prefix is used for Red Hat Enterprise Linux images. Since they are
   not available publicly, the test-suite usually skips them.

   The `filesystem` manifest is used to test assemblers. These tests doesn't
   need a big filesystem tree representing a whole operating system. Instead,
   this manifest's tree is constructed just from the filesystem package and is
   marked using the selinux stage.

   Manifests ending on `.mpp.yaml` are fed through the ManifestPreProcessors
   and then stored in the same directory with an `.json` extension (replacing
   `.mpp.yaml`). generated files are committed to the repository. Nevertheless,
   if you need to regenerate them, use `make test-data`.

 * `./sources/`:
   This directory contains test-data for runtime tests of the source-engines. It
   contains a directory that is served via HTTP in the tests, and a directory of
   test-cases what to expect when using the attached `sources.json`.

 * `scripts`:
   This directory contains scripts used from other tests, i.e. although they are
   executables they are at the same time test-data to the actual (unit) tests.
