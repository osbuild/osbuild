# OSBuild - Build-Pipelines for Operating System Artifacts

## CHANGES WITH 23:

  * The `org.osbuild.rpm` stage now includes the `SIGPGP` and `SIGGPG`
    fields of each installed package in the returned metadata.
    Additionally, its docs have been improved to specify what metadata
    is returned.

  * The spec file has been changed so that the shebang for assemblers,
    stages and runners are not automatically mangled anymore. Runners
    were already changed to have the correct shebang for their target
    systems. Assemblers and stages are not meant to be run on the host
    itself, but always inside a build root container, which must bring
    the correct dependencies to run all stages and assemblers. For now,
    Python3 (>= 3.6), located at /usr/bin/python3, is required.
    This change will enable building Fedora systems on RHEL hosts.

  * Unit tests have been fixed to run on RHEL by dynamically selecting
    a runner that is suitable for the host system.

  * The stages unit tests are now using generated manifests via mpp,
    and have been updated to use Fedora 32. Additionally, the current
    mirror was replaced with [`rpmrepo`](https://osbuild.org/rpmrepo),
    which should provide a faster, more reliable package source.

  * The CI has dropped Fedora 31 but instead includes Fedora 33 as
    systems to run the composer reverse dependency tests for.

Contributions from: Christian Kellner, Lars Karlitski

— Berlin, 2020-10-23

## CHANGES WITH 22:

  * runners: support for RHEL 8.4 was added

  * A new internal API was added that can be used to communicate
    exceptions from runners, stages and assemblers in a more
    structured way and, thus, make it possible to include them in
    the final result in a machine readable way. Use that new API
    in the runners.

  * Improvements to the CI, including the integration of codespell
    to check for spelling mistakes.

Contributions from: Chloe Kaubisch, Christian Kellner, Jacob Kozol,
                    Lars Karlitski, Major Hayden

— Berlin, 2020-10-08

## CHANGES WITH 21:

  * The way that output of modules is communicated to osbuild was
    re-factored in a way that now makes it possible to also capture
    and log the output of the container runtime, i.e. `bubblewrap`.
    This should prove useful to track down errors where the runner
    can not be executed.

  * runners: support for Fedora 34 was added

  * A lot of internal re-factoring was done, to make the code nicer
    and easier to read. For example the way objects are exported in
    the pipeline is now unified.
    Additionally, a dedicated API is used to fetch the arguments in
    the modules, instead of relying on standard input.

Contributions from: chloenayon, Christian Kellner

— Berlin, 2020-09-10

## CHANGES WITH 20:

  * The filesystem assemblers gained support for btrfs. They can
    now output image files as btrfs, similar to the existing support
    for ext4 and xfs.

  * The `--libdir=DIR` handling was generalized in that an empty
    `osbuild` subdirectory will now always cause osbuild to use the
    system osbuild package. This means a custom `libdir` via
    `--libdir=DIR` no longer requires the entire osbuild python
    package to be bundled in an `osbuild` subdirectory.

  * When run on a terminal, `osbuild` will now output the duration
    of a stage (or other module).

  * The `--output-directory` switch is now mandatory if no checkpoint
    was specified. In this situation, running `osbuild` would be a
    no-op.

  * The `ostree` assembler now optionally emits version metadata in
    its commits.

  * `osbuild` now supports running on Ubuntu-20.04.

  * Modules can now pass metadata alongside the filesystem objects
    they emit. This metadata is not stored in the final artifact, but
    passed to the caller via the structured osbuild output.

  * The `ostree` assembler now emits compose metadata as part of its
    build. This can be inspected by the caller to get detailed compose
    information.

  * The `rpm` stage now emits detailed metadata about the installed
    RPM packages.

  * Lots of fixes all over the place, including SELinux reworks and
    PEP-8 conformance.

Contributions from: Christian Kellner, David Rheinsberg, Davide Cavalca,
                    Major Hayden, chloenayon

— Berlin, 2020-08-13

## CHANGES WITH 19:

  * osbuild is now warning if neither output-directory nor any
    checkpoints were specified on the command line. No attempt
    to actually build anything will be made.

  * Fix a bug in the `org.osbuild.files` source where the timeout
    was passed as a floating point value to curl, which in
    certain locales would result in a comma being used for the
    decimal separator, which can not be parsed by curl.

  * The `org.osbuild.systemd` stage gained the ability to mask
    services. Additionally, `enabled_services` is not a required
    option anymore.

  * The `org.osbuild.script` stage has been dropped.

  * The ability to pass in secrets via the command line has been
    removed. It was only used by the deprecated `dnf` stage.

  * The JSON schema was fixed for the `org.osbuild.noop` stage.

  * Stages and assemblers are now contained via `bubblewrap`
    instead of `systemd-nspawn`, which has many advantages,
    including but not limited to: being faster, not requiring
    root, better control of the contents of the build-root.

  * Internally, the logging of output and the communication
    between the stages and the osbuild process on the host has
    been reworked and cleaned up. This should allow better
    monitoring in the future.

  * The network of the sandbox that is used to run stages and the
    assemblers is now isolated from the host network.

  * As always, lots of improvements to the testing infrastructure,
    that should lead to better and quicker tests. Static analysis
    is run nightly as well.

Contributions from: Chloe Kaubisch, Christian Kellner, David Rheinsberg,
                    Major Hayden, Martin Sehnoutka, Ondřej Budai,
                    Tom Gundersen

— Berlin, 2020-07-30

## CHANGES WITH 18:

  * All the RHEL runners now always use platform-python. This is the
    python3.6 based interpreter that provides a stable platform for
	system software based on python to be used. It is also always
    available, in contrast to the python3 binary, that needs to be
    installed separately.

  * The `org.osbuild.selinux` stage now support label overwrites, i.e.
    manually specifying the label specific files and directories.

  * Improvements to the testing infrastructure, including new tests for
    the `org.osbuild.selinux` stage and the `org.osbuild.ostree.commit`
    assembler. Additionally, the tests do not rely on the `nbd` kernel
    module, which seems to have stability issues.

Contributions from: Christian Kellner

— Berlin, 2020-06-23

## CHANGES WITH 17:

  * SELinux: When osbuild is creating the file system tree it can happen
    that the security policy of the new tree contains SELinux labels that
    are unknown to the host. The kernel will prevent writing and reading
    those labels unless the caller has the `CAP_MAC_ADMIN` capability.
    A custom SELinux policy was created that ensures that `setfiles` and
    `ostree` / `rpm-ostree` can execute in the right SELinux domain and
    therefore have the correct capability. Additionally, the build root
    container now retains the `CAP_MAC_ADMIN` capability.

  * The `org.osbuild.ostree.commit` assembler will now set the pipeline
    id as the value for the `rpm-ostree.inputhash` metadata of the commit.

  * The `org.osbuild.files` source is now more conservative by only using
    four concurrent downloads. It will also not try to fetch the same URL
    more than once.

  * Take care not to put large content on `/tmp` which is usually backed
    by a `tmpfs` and thus memory.

  * Allow `check_gpg` to be omitted in the `org.osbuild.rpm` stage.

  * Restore Python 3.6 support: Replace the usage of features that were
    introduced in later Python versions and add 3.6 specific code where
    needed.

  * MPP: add pipeline-import support for the pre-processor and use that
    for the test data.

  * Tests: Move the all remaining test into the correct sub-directory.

  * As always: improvements to the test infrastructure and the CI.

Contributions from: Christian Kellner, David Rheinsberg, Lars Karlitski,
                    Major Hayden, Tom Gundersen

— Berlin, 202-06-10

## CHANGES WITH 16:

  * Support for ignition: a new `org.osbuild.ignition` stage has been
    added together with a new option in the `org.osbuild.grub2` stage,
    called `ignition`. When used together, a new variable for the
    kernel command line, called `$ignition_firstboot`, will exist that
    will trigger the run of `ignition` on the first boot of an image.

  * A new `org.osbuild.copy` stage was added that can be used to copy
    files and directories from an archive to the file system tree. The
    archive will be fetched via the existing `org.osbuild.files` source.

  * The result of the assembler will now not automatically be committed
    to the store anymore, but only when requested via `--checkpoint`;
    very much like it is already the case for the stages.

  * The `tree_id` and `output_id` identifiers have been dropped from the
    osbuild result. This reflects the policy that the internals of the
    store are private. The `--output-directory` command line option can
    be used to obtain the final artifact instead.

  * The `org.osbuild.files` and `org.osbuild.ostree` sources have been
    properly documented and the JSON schema for their options was added.
    osbuild gained support for the validation of the source options in
    the manifest. As a result the whole manifest is now validated.

  * The GPG signature verification of RPMs in the `org.osbuild.rpm` stage
    is now optional and opt-in. The GPG key can now also be provided per
    package.

  * The `org.osbuild.ostree` gained support for pre-populating `/var`
    like it is done by anaconda.
    Also its `rootfs` option is not required anymore, since in specific
    cases, like when ignition is being used, the root file system is
    identified by its label only.

  * The common term for Stages, Assemblers and Sources shall from now on
    be "module". Rename the `StageInfo` class to `ModuleInfo`.

  * Small bug fixes, including to the org.osbuild.users stage, that now
    allows the creation of users with `uid`/`gid`s that are `0` and
    descriptions and passwords that are empty. The `org.osbuild.files`
    source got a bug fix to allow the use of URL format but without
    specifying the `secrets` key.

  * Numerous small fixes throughout the source code to fix all `pylint`
    warnings. These are now also enabled for the source checks.

  * Lots of improvements to the test infrastructure and the CI.

Contributions from: Christian Kellner, David Rheinsberg, Jacob Kozol,
                    Major Hayden, Tom Gundersen

— Berlin, 2020-06-04

## CHANGES WITH 15:

  * A new assembler, `org.osbuild.oci-archive`, that will turn a tree
    into an Open Container Initiative Image compliant archive. These
    archives can be used to run containers via e.g. podman.

  * Support for client side certificates to download content from the
    Red Hat servers: the `org.osbuild.files` source got support for
    reading entitlements and pass those certificates along when
    fetching content, i.e. RPMs.

  * A new ManifestPreProcessor (MPP) was added as a new tool located
    in `tools/mpp-depsolve.py`. Currently, it can take an existing
    manifest and dep-solve packages specified via a new `mpp-depsolve`
    option in existing `org.osbuild.rpm` stages.
    This is now used to generate Fedora 32 based test pipelines.

  * The `org.osbuild.ostree.commit` assembler gained an option to produce
    a tarball archive instead of emitting the plain OSTree repository.

  * Schema validation is now done with the draft 4 validator, and works
    therefore with pyhthon-jsonschema 2.6.

  * The `tree_id` and `output_id` fields got dropped from the resulting
    JSON when inspecting pipelines via `osbuild --inspect`.

  * The `--build-env` option has been dropped from the command line
    interface. It was deprecated and not used anymore.

  * Tests have been converted to not rely on `tree_id` and `output_id`
    anymore, as they are deprecated and will be removed in the future.

  * Lots of other improvements to the test infrastructure and the CI.

  * And finally for something meta: this file has been re-formatted to
    be proper markdown.

Contributions from: Christian Kellner, David Rheinsberg, Jacob Kozol,
                    Major Hayden

— Berlin, 2020-05-20

## CHANGES WITH 14:

  * Schema validation: The osbuild python library gained support for
    retrieving the metadata of modules and schema validation. This is
    being used on each invocation of osbuild in order to validate the
    manifest. Should the validation fail the build is aborted and
    validation errors are returned, either in human readable form or
    in JSON, if `--json` was specified.

  * A `--inspect` command line option was added for osbuild. Instead
    of attempting to build the pipeline, the manifest will be printed
    to stdout in JSON form, including all the calulcated identifiers
    of stages, the assembler and the `tree_id` and `output_id` of the
    pipeline (and build pipelines). Schema validation will be done and
    errors will be reported.

  * Internally, the buildroot class now uses `PYTHONPATH` to point to
    the `osbuild` module instead of the symlinks or bind-mounts in the
    individual modules.

  * Fixes to the CI and many cleanups to the schemata, sample and test
    pipelines as a result of the schema validation work.

Contributions from: Christian Kellner, David Rheinsberg, Ondřej Budai

— Berlin, 2020-05-06

## CHANGES WITH 13:

  * Stage `org.osbuild.yum` has been dropped. It has been deprecated for
    some time and `org.osbuild.rpm` provides a better alternative.

  * XZ compression now utilizes all available CPU cores. This affects all
    stages and assemblers that support XZ compression. It should decrease
    compression times considerably.

  * `org.osbuild.grub2` now supports referring to file-systems via a label
    additionally to a UUID. This affects all places where an existing
    file-system is referred to. Disk creation still requires a UUID to be
    provided. `org.osbuild.fstab` gained similar support.

  * RHEL-8.3 is now supported as host system.

  * The 'libdir' layout in `/usr/lib/osbuild/` has been simplified.
    Distributions are no longer required to create mount anchors during
    installation. Instead, all modules (stages, assemblers, sources, and
    runners) can be copied verbatim from the source tree.

  * `org.osbuild.grub2` now correctly pads `grubenv` files to 1024 bytes.
    This was not done correctly, previously, and caused other parsers to
    fail.

  * The containerization via systemd-nspawn was adjusted to support
    running in a container. With sufficient privileges, you can now run
    osbuild pipelines from within a container.

Contributions from: Christian Kellner, David Rheinsberg, Major Hayden

— Berlin, 2020-04-29

## CHANGES WITH 12:

  * The `qemu` assembler now supports the `VHDX` image format. This is the
    preferred format for AWS targets, so it is a natural fit for our
    assemblers.

  * The `grub2` stage now disables the legacy compatibility by default.
    You have to explicitly enable it in the stage options if you require
    it.

  * Additionally, the `grub2` stage now also has a `uefi.install` option
    to control whether it installs the UEFI configuration from the build
    tree into the target tree. Furthermore, a new option called
  `write_defaults` controls whether default options are written to
  `/etc` (enabled by default).

  * The `dnf` stage was removed. The `rpm` stage fully replaces all its
    functionality.

  * The `fedora27` runner is no longer supported. Fedora 30 is the minimum
    required host version for Fedora systems.

  * Add OSTree integration. This includes multiple stages and sources
    which allow to export osbuild trees as ostree commits, or import
    ostree commits into an osbuild pipeline:

    * org.osbuild.rpm-ostree: This stage uses `rpm-ostree compose` to
                              post-process a tree and prepare it for
                              committing to ostree.

    * org.osbuild.ostree.commit: A new assembler that takes a tree that
                                 conforms to the ostree layout and
                                 turns it into an ostree commit.

    * org.osbuild.ostree: A new source that provides external ostree
                          commits to a pipeline.

    * org.osbuild.ostree: A new stage that takes an ostree commit and
                          prepares the working directory with its
                          content.

  * The `osbuild` binary now has an `--output-directory=DIR` argument
    which allows to specify a directory where to put the output of the
    pipeline assembler. This is optional for now, but will be made
    mandatory in the future.

  * A new stage called `org.osbuild.first-boot` allows to control the
    execution of scripts at the first bootup of the generated images.

Contributions from: Christian Kellner, David Rheinsberg, Major Hayden,
                    Ondřej Budai, Tom Gundersen

— Berlin, 2020-04-15

## CHANGES WITH 11:

  * Drop support for legacy input: passing in non-manifest style
    pipelines is now not supported anymore.

  * Support for specifying an UUID for partitions when using the GPT
    partition layout was added to the org.osbuild.qemu assembler.

  * Fix a crash in the case the assembler failed, which was caused by
    cleanup up the object while the object was still being written to.

  * Delay the cleanup of the build tree to after the error checking
    since in the error case there is nothing to clean up and trying
    to do so will lead to crash.

  * `objectstore.Object` now directly cleans its working tree up, in
    contrast to relying on the implicit cleanup of `TemporaryDirectory`.
    One advantage of this is that the custom cleanup code can handle
    immutable directories, which Python 3 fails to clean up.

  * Drop custom `os-release` creation from the RHEL 8.2 runner. The
    issue that made this necessary got fixed upstream.

  * Ensure the build tree is always being built even if there are no
    stages specified.

  * spec file: Do no generate dependencies for the internal files and
    add NEWS.md to the documentation section.

  * The Fedora 30 based aarch64 example was fixed and now builds again.

Contributions from: Christian Kellner, David Rheinsberg, Lars Karlitski,
                    Major Hayden, Martin Sehnoutka, Ondřej Budai

— Berlin, 2020-04-01

## CHANGES WITH 10:

  * A new man-page `osbuild-manifest(5)` is available, which describes
    the input format of the JSON manifest that `osbuild` expects.

  * Man-pages can now be built via `make man`. This supports `SRCDIR` and
  `BUILDDIR` variables to build out-of-tree.

  * Temporary objects in the object-store are now created in
  `.osbuild/tmp/`, rather than in the top-level directory. This should
    help cleaning up temporary objects after a crash. If no osbuild
    process is running, the `tmp/` subdirectory should not exist.

  * The final stage of a build-pipeline is no longer automatically
    committed. You must pass checkpoints via `--checkpoint` to commit
    anything to the store.

  * Improve curl timeout handling. This should improve osbuild behavior
    with slow or bad mirrors and make sure operations are retried
    correctly, or time-out if no progress is made.

Contributions from: Christian Kellner, David Rheinsberg, Lars Karlitski,
                    Major Hayden, Tom Gundersen

— Berlin, 2020-03-18

## CHANGES WITH 9:

  * The last pipeline stage is no longer automatically committed to the
    store. This used to be a special case to make things work, but it has
    now been properly fixed.
    From now on, if you want a stage committed to the store, you need to
    pass a `--checkpoint` option for the stage.

  * The runner for the host system is now auto-detected. The
  `runners/org.osbuild.default` symlink is now longer required (nor
    supported).

  * A generic runner named `org.osbuild.linux` was added. This runner
    uses the default value of `ID` in `/etc/os-release`. That is, if the
    local OS cannot be detected, or if no `os-release` file is provided,
    this is the fallback runner that is used.
    This runner only performs the bare minimum of initialization. It is
    enough to run the most basic stages on all systems we tested.

  * On Archlinux, the generic runner will now be used.

  * A new runner for RHEL-8.1 is available.

  * The JSON input to `osbuild` is now a monolithic manifest format which
    contains all build information. For now, this means the input
    manifest can contain a `pipeline:` key with the pipeline definition,
    as well as a `sources:` key with external source definitions
    previously passed via `--sources`.
    The old input format is still supported, but will be dropped in the
    next release.

  * The osbuild sources now come with a man-page `osbuild(1)`. Further
    pages will follow in the future.

Contributions from: Christian Kellner, David Rheinsberg, Jacob Kozol,
                    Lars Karlitski, Major Hayden, Martin Sehnoutka, Tom
                    Gundersen

— Berlin, 2020-03-05

## CHANGES BEFORE 9:

  * Initial implementation of 'osbuild'.

Contributions from: Brian C. Lane, Christian Kellner, David Rheinsberg,
                    Jacob Kozol, Lars Karlitski, Major Hayden, Martin
                    Sehnoutka, Ondřej Budai, Sehny, Tom Gundersen,
                    Tomas Tomecek, Will Woods
