## CHANGES WITH 35:
  * Bug fix release.

Contributions from: Christian Kellner

— Oslo, 2021-08-29

## CHANGES WITH 34:

  * `stages/bootiso.mono`: support for aarch64

  * `stages/ostree.{pull,deploy}`: support for specifying ostree
    remotes.

— Oslo, 2021-08-29

## CHANGES WITH 33:

  * `stages/org.osbuild.grub2`: add support for greenboot, i.e.
    automatically rolling back bad updates, i.e. updates that do not
    boot successfully.

  * `stages/org.osbuild.gzip`: new stage to compress files via gzip.

Contributions from: Christian Kellner, Diaa Sami

— Vöcklabruck, 2021-08-25

## CHANGES WITH 32:

  * `stages/org.osbuild.grub2`: allow the unified grub config scheme
    to be configured even in pure UEFI configurations.

Contributions from: Christian Kellner

- Asker, 2021-08-24

## CHANGES WITH 31:

  * **LVM2 support** was added. For this new stages and host services
    were added:

  * Support for parent devices was added to the `devices` host
    service: a device can now specify a device it depends on. An
    example is an LVM2 volume on a partition. When loading, the
    devices are pre-sorted so that all dependencies are in the
    correct order.

  * `stages/org.osbuild.lvm2.create`: new stage to create logical
     volumes, the volume group and the physical volume in one
     operation.

  * `devices/org.osbuild.lvm2.lv`: new device host service to activate
     a LVM2 logical volume. The logical volume is identified via the
     underlying device, so there is no need to know the logical
     volume's name or uuid.

  * `stages/org.osbuild.lvm2.metadata`: new stage to modify LVM2
     metadata.

  * `stages/org.osbuild.untar`: new stage that can be used to extract
    a tarball.

  * `runners/org.osbuild.rhel86`: new runner for RHEL 8.6, based on
    the current RHEL 8.2 runner.

  * `stages/org.osbuild.nm.conf`: new stage to create NetworkManager
    configuration files. Currently only a subset of settings are
    supported.

  * `inputs/org.osbuild.ostree.checkout`: new input to checkout an
    OSTree commit so that stages can use its contents.

  * `stages/org.osbuild.ostree.passwd` new stage to merge the groups
    and passwords from one or more existing commits into the
    corresponding files in the tree. This is needed to make sure that
    uids/gids stay stable between commits.

  * `stages/org.osbuild.grub2.inst`: fix prefix for dos layouts: When
    the partition layout is `dos` or `mbr`, the correct name for it in
    the prefix is `msdos`.

  * Loop controller improvements: various new helper methods to close
    and flush the loop devices.

  * `devices/org.osbuild.loopback`: explicitly flush the device buffer
    cache and clear the fd to ensure that all data is properly written
    to the backing file.

Contributions from: Tomas Hozza, Martin Sehnoutka, Christian Kellner,
                    Ondřej Budai, Thomas Lavocat

— Berlin, 2021-08-18

## CHANGES WITH 30:

  * Add support for building **OSTree based raw images**. This
    means creating a raw image and deploying a commit in it. For
    this various stages have been added:

  * `stage/org.osbuild.ostree.init-fs`: initializes a file
    system in OSTree layout.

  * `stages/org.osbuild.ostree.init-os`: initializes a new
    state root with a given name.

  * `stages/org.osbuild.ostree.config`: allows changing the
    configuration for an OSTree repo.

  * `stages/org.osbuild.ostree.deploy`: deploy an existing
    commit.

  * `stages/org.osbuild.ostree.fillvar`: use `systemd-tmpfiles`
    to provision `/var` for a stateroot and deployment.

  * `stages/org.osbuild.ostree.remotes`: allows to configure
    remotes for an OSTree repository.

  * `stages/org.osbuild.ostree.selinux`: re-label (parts) of
    an OSTree deployment.

  * `stages/org.osbuild.fstab`: support for creating an fstab file in
    an OSTree deployment. NB: this is a temporary solution and will
    very likely be removed in the next release.

  * **Manifest-Pre-Processor**: the various mpp tools got unified into a
    single tool which is now shipped as `osbuild-mpp` in the `osbuild-tools`
    package. Additionally, it supports variable expansion via `mpp-vars`
    together with `mpp-format-{int,string,json}` as well as defining a
    partition table via `mpp-image`.

  * `stages/org.osbuild.tar`: option to not include the root node. When
    building the tar archive, the command that is used normally includes
    the root node as ./ and also leads to all files having a "./" prefix.
    On the other hand, the oci stage as well as the old ostree.commit
    assembler, with the tarball option, would enumerate the contents
    instead of passing ., thus not including the root node and also
    avoiding the ./ prefix.

  * `stages: add org.osbuild.nm.conn`: Add a new stage to configure
    NetworkManager system connections. Currently only ethernet
    connections are supported with a limited set of options.

  * `stages/org.osbuild.fstab`: support device nodes and partlabel.
    Add two new options to the fstab stage so that plain device nodes
    and also `PARTLABEL`s are supported for the fs spec field.

  * `util/rhsm`: Implement a fallback to the previous behaviour. This
    is useful if `redhat.repo` is not present, due to `manage_repos=0`,
    because it will pick up certificates with matching urls.

  * `mounts`: Change the format how mounts are specified from dictionary
    to arrays.

  * osbuild will now validate whether the source references are properly
    specified in the `sources` section of the manifest.

  * `stages/org.osbuild.grub.iso`: New stage to configure grub in EFI
    mode for the boot iso. This code used to be part of `bootiso.mono`
    stage but is now split out.

  * `stages/org.osbuild.isolinux`: New stage to configure the isolinux
    bootloader. This code used to be part of the `bootiso.mono` stage
    but is now split out.

  * NB: **The `bootiso.mono` stage is now deprecated**.

  * `assembler/org.osbuild.ostree.commit`: fix copying of links. A patch
    in version 29 lead to the contents of links being copied not the
    link itself. This broke OSTree upgrades.

  * `stages/org.osbuild.kickstart`: add support for creating users and
    groups. These new options will insert the corresponding commands
    in the kickstart file embedded into the boot iso.

  * objectstore: for the host object osbuild now uses recursive bind
    mounts. Additionally, it only exposes `/usr` from the host.

  * `stages/org.osbuild.mkdir`: new stage to create directories.

  * `stages/org.osbuild.tar`: support for choosing the tar format.

  * `stages/org.osbuild.xz`: new stage to compress files via `xz`.

  * `stages/org.osbuild.authselect`: new stage to select system
    identity and auth sources.

  * `stages/org.osbuild.keymap`: add new option to the stage to
    configure X11 keyboard.

  * `stages/org.osuild.nginx.conf`: add new stage to configure the
    `nginx` web server.

  * `stages/org.osbuild.chmod`: add new stage that uses `chmod` to
    change the mode for multiple files.

  * buildroot: mount `/sys` as read-only inside the container. That
    fixed a bug triggered by a scriptlet that would write to `/sys`.

  * `stages/org.osbuild.chrony`: extend the stage to allow for more
    configuration options.

  * `stages/org.osbuild.cloud-init`: add new stage to configure the
    `cloud-init` service.

  * `stages/org.osbuild.dracut.conf`: add new stage for creating
    dracut config files. The options are very similar to the ones
    in the existing dracut stage.

  * Various improvements to CI and testing.

Contributions from: Achilleas Koutsou, Alexander Larsson, Alexander Todorov,
                    Antonio Murdaca, Christian Kellner, Diaa Sami, Jakub Rusz,
                    Javier Martinez Canillas, Martin Sehnoutka, Ondřej Budai,
                    Paul Wayper, Tomas Hozza

— Berlin, 2021-07-22

## CHANGES WITH 29:

#### Host services

  * This release adds support for building raw images via the new manifest
    format version 2. To support this a new generic concept of a **host
    service** is introduced: Stages are executed in a container that
    isolates them from the hosts and thus limits their access to devices,
    the osbuild store, and and most privileged operations. But certain
    stages also require access to all of those. Previously, osbuild provided
    several APIs to stages for these kinds of operations. In format version
    2 the sources API concept was generalized to `inputs` and was also made
    declarative, i.e. the inputs are now defined at the manifest level and
    prepared by osbuild *before* the stage is executed.
    In this release, a generic framework for such services provided by
    *osbuild* to the stages was created: the *host services*. The existing
    inputs were ported to the new framework and two new services were
    introduced: **device services**: can provide stages with access to
    devices and **mount services** can provide stages with access to
    mounts of file systems of e.g. devices:

  * `devices/org.osbuild.loopback`: a new *device host service* that can
    be used to access a file or parts of it as a device. This replaces
    the `LoopServer` and `RemoteLoop` API.

  * `mounts/org.osbuild.{btrfs,ext4,fat,xfs}`: new *mount host services*
    that can be used to mount the corresponding file system transparently
    for the stages. All mounts are exposed in `/run/osbuild/mounts` to
    the stages.

  * Various new stages were created to support creating raw images via
    the new format and the new device and mount host services:

  * `stages/org.osbuild.truncate`, a new stage to truncate a file, i.e.
    create or resize a (sparse) file.

  * `stages/org.osbuild.sfdisk`, a new stage to create a partition with
    a given layout.

  * `stages/org.osbuild.mkfs.{btrfs,xfs,fat,xfs}`, new stages to create
    a file system on a device. The latter is provided via the device
    host service.

  * `stages/org.osbuild.copy`, new generic copy stage that allows copying
    of artifacts from inputs to trees and mounts. The latter are provided
    by the mount host service.

  * `stages/org.osbuild.grub2.inst`, a new stage to install the boot and
    core grub2 image to a device.

  * `stages/org.osbuild.zipl.inst`, a new stage to install the Z initial
    program loader to a device.

  * `stages/org.osbuild.qemu`, a new stage that can convert a raw image
    into a vm image such as a `qcow2`.

#### New stages:

  * `stages/org.osbuild.modprobe`, a new stage for configuring
    module loading via modprobe. For now only the `blacklist` command
    is implemented.

  * `stages/org.osbuild.logind`, add new stage for configuring
    `systemd-logind` via drop-ins. Currently only setting the `NAutoVTs`
    key in the `Login` section is supported.

#### Improvements and bug fixes for existing *stages*

  * stages: extend org.osbuild.systemd to create .service unit drop-ins

    Extend the `org.osbuild.systemd` stage to create drop-in configuration
    files for systemd `.service` units under `/usr/lib/systemd/system`.
    Currently only the `Environment` option in the `Service` section can be
    configured.

  * The `org.osbuild.sysconfig` stage was extended to be able to create
    `network-scripts/ifcfg-*` files.

  * The `org.osbuild.rhsm` stage was extended to be able to configure
    the subscription-manager.

  * stages/oci-archive: support for specifying annotations to the
    container manifest.

  * stages/groups and stages/users: fix user names schema validation
    so that invalid user and group names are caught when the schema
    is validated.

  * aarch64: use single qemu-img thread because converting an image
    might hang due to an bug in qemu.

  * stages/dracut: disable hostonly mode and default to reproducible images

#### Improvements and fixes for *sources*

  * sources/curl: Implement new way of getting RHSM secrets. This
    now matches subscription entitelments to repositories.

  * sources: introduce new `org.osbuild.inline` source that can be
    used to embed files directly into the manifest.

#### General *osbuild* bug fixes and improvements

  * Disable buffering for the python based stages so that print statements
    and output of tools are properly ordered.

  * meta: proper error reporting for schema parsing

  * test: update test manifests to use Fedora 34

  * Various improvements to testing and CI.

Contributions from: Achilleas Koutsou, Christian Kellner, Martin Sehnoutka,
                    Ondřej Budai, Tomas Hozza

— Berlin, 2021-06-14

# OSBuild - Build-Pipelines for Operating System Artifacts

## CHANGES WITH 28:

 * Add a new option to the `org.osbuild.qemu` assembler that controls
   the qcow2 format version (`qcow2_compat`).

 * Add history entries to the layers of OCI archives produced by the
   `org.osbuild.oci-archive` stage. This fixes push failures to quay.io.

 * Include only a specific, limited set of xattrs in OCI archives produced by
   the `org.osbuild.oci-archive` stage. This is specifically meant to exclude
   SELinux-related attributes (`security.selinux`) which are sometimes added
   even when invoking  `tar` with the `--no-selinux` option.

 * The package metadata for the `org.osbuild.rpm` stage is now sorted by
   package name, to provide a stable sorting of the array independent of
   the `rpm` output.

 * Add a new runner for Fedora 35 (`org.osbuild.fedora35`) which is
   currently a symlink to the Fedora 30 runner.

 * The `org.osbuild.ostree` input now uses `ostree-output` as temporary
   directory and its description got fixed to reflect that it does
   indeed support pipeline and source inputs.

 * devcontainer: Include more packages needed for the Python extension and
   various tools to ease debugging and development in general. Preserve
   the fish history across container rebuilds.

 * Stage tests are writing the prodcued metadata to `/tmp` so the actual
   data can be inspected in case there is a deviation.

 * CI: Start running images tests against 8.4 and execute image_tests directly
   from osbuild-composer-tests. Base CI images have been updated to Fedora 33.

Contributions from: Achilleas Koutsou, Alexander Todorov, Christian Kellner,
                    David Rheinsberg

— Berlin, 2021-04-08

## CHANGES WITH 27:

 * Add new `org.osbuild.resolv-conf` stage that can be used to
   configure the resolver(3) via the /etc/resolv.conf(5)
   configuration file.

 * Do not include SELinux labels in the `org.osbuild.oci-archive`
   when creating the archives for the file system layers. Since
   SELinux labels are not namespaced, the labelling is up to the
   host, not the container itself. Since podman does not adjust
   the labels after unpacking the archive, having labels might
   actually render the container unusable.

 * Fix the `org.osbuild.ostree.preptree` stage to properly detect
   the existence of`/etc/machine-id`, i.e. do it before the move
   of `/etc` to `/usr/etc` not after.

 * In the `org.osbuild.grub2` stage, write the kernel command
   line options also to `/etc/default/grub` (`GRUB_CMDLINE_LINUX`).
   This is used by `grub2-mkconfig` to assemble the full kernel
   command line when generating the menu entries.

 * Add a new runner for RHEL 8.5 (`org.osbuild.rhel85`) which is
   currently a symlink to the 8.2 runner as well as a new runner
   for RHEL 9.0 (`org.osbuild.rhel90`).

 * Fix the version 1 formatting code to properly set the overall
   result status to *failed* in case the assembler failed.

 * Fix the `org.osbuild.ostree` source to properly handle pre-
   fetching of commits.

 * Ability to set the system id in the `org.osbuild.xorrisofs`
   stage.

 * The `org.osbuild.ostree.preptree` stage now moves `/home` to
   `/var/home` after initializing the new root file system. This
   ensures that home directories of existing users are preserved.
   NB: This does not capture files and their contents only dirs.

 * Various improvements to testing and CI.

Contributions from: Achilleas Koutsou, Aleksandar Todorov, Christian
                    Kellner,Jozef Mikovic, Ondřej Budai, Tom Gundersen

— Berlin, 2021-03-16

## CHANGES WITH 26:

  * Support the creation of boot iso installation media:
    Various new stages were added that make it possible
    to generate bootable installation media (bootisos).
    The stages are the following:

  * A new `org.osbuild.kickstart` stage was added which
    can be used to create an Anaconda kickstart file with
    the given option. For now only the `ostreesetup` and
    `liveimg` options can be configured.

  * A new `org.osbuild.buildstamp` stage was added to
    write a `.buildstamp` file, which is used to inform
    the Anaconda installer about the product to be
    installed, like its name, version, etc.

  * A new `org.osbuild.anaconda` stage was added which
    can be used to configure basic aspects of the
    installer. Right now, this allows the selection of
    enabled kickstart modules.

  * A new `org.osbuild.lorax-script` stage was added
    that can execute a Lorax template specified by
    `path` with a specified set of variables. A
    prominent use case is the post installation script
    of the lorax-templates package that will transform
    an OS installation into one suitable for the
    Ananconda installer.

  * A new `org.osbuild.bootiso.mono` stage was added
    that will prepare a file system tree that is
    suitable to create a bootlable installer medium.

  * A new `org.osbuild.xorrisofs` stage was added
    that will take a suitable file system tree and
    create a Rock Ridge enhanced ISO 9660 medium.

  * A new `org.osbuild.implantisomd5` stage was added
    that can implant md5 checksums into ISO 9660 media.
    These are used by a dracut module to check the
    installation medium.

  * A new `org.osbuild.discinfo` stage that writes a
    `.discinfo` file to the root of the installation
    medium to identify its content.

  * `osbuild` gained the ability to checkpoint via pipeline
     names, e.g., `--checkpoint build`, will checkpoint the
     last stage in the pipeline called `build`.

  * A new `org.osbuild.dracut` stage was added that
    can create an initrd image. The stage supports various
    options that allow a very fine-grained customization
    of the contents of the initrd.

  * The `org.osbuild.rpm` stage gained new options to
    prevent documentation from being installed as well
    as to prevent the generation of the initrd during the
    kernel package's install scripts.

  * The `org.osbuild.oci-archive` stage now supports additional
    layers via option inputs. This can be used to e.g.
    share a base image but have different content in
    separate layers.

  * The `org.osbuild.grub2` stage gained support for the
    standard grub2 machinery to select the menu entry to
    be booted. This is done by having a `saved_entry`
    variable in the `grubenv` file and the corresponding
    logic in the grub configuration, to select the default
    boot entry based on that variable. A new `saved_entry`
    stage option can be used to set the variable at image
    creation time.

  * The macro pre-processor (MPP) now properly supports
    multiple repos in `mpp-depsolve`

Contributions from: Christian Kellner, David Rheinsberg

— Berlin, 2021-02-19

## CHANGES WITH 25:

  * **Tech preview** of the new manifest format version 2!
    This format can describe the generic direct a-cyclic
    pipeline graphs that were introduced internally in the
    last version (25). The schema validation code has been
    reworked so it supports multiple format versions. Format
    detection code was added so different format modules can
    be used transparently. The format version 2 schema was
    added and a new format module to load and describe the
    format was added. Basic checks were added to the tests
    to check validation, loading and describing the new
    format.
    The Manifest Pre-processor (MPP) now also supports
    format version 2.
    NB: This is indeed a preview of the format and it might
    still change, especially the output produce by it most
    certainly will.

  * Add `--export <name_or_id>` command line switch, which
    can be invoked multiple times to request the exporting
    of one or more artifacts that were built. They will be
    placed under a sub-directory of `--output-directory`,
    with the name or id that was specified.

  * The schema of the `org.osbuild.rpm` stage as well as the
    `org.osbuild.ostree` and `org.osbuild.files` sources
    was ported to format version 2.

  * The `org.osbuild.oci-archve` & `org.osbuild.ostree.commit`
    assemblers were ported to new assembler like stages with
    tree inputs so they can be used in the new format v2.

  * A new `org.osbuild.ostree.init` stage was added to
    create a OSTree repo in a given format at a given location.

  * A new `org.osbuild.ostree.pull` stage was added that can
    be used to pull commits, specified via inputs, into a
    pre-existing repository.

  * A new `org.osbuild.ostree.preptree` stage was added that
    replaces the `org.osbuild.rpm-ostree`, which is
    now deprecated and should not be used in new manifests.

  * A new `org.osbuild.files` input was added that provides
    file-like resources to stages. Currently only supports
    source origins.

  * A new `org.osbuild.ostree` input was added that provides
    ostree commits to stages. It can handle sources as well
    as pipeline origins, i.e. it can provide previously
    build commits to other stages.

  * A new `org.osbuild.noop` input was added, that like the
    noop stage, does nothing but forward the supplied data
    to the stage.

  * A new integration test was added that uses the new
    manifest format that builds an OSTree commit, then builds
    a container with that commit into. This will test all new
    assembler like stages that were added as well as the new
    `--export` command line option.

  * The `org.osbuild.files` source was renamed after the
    underlying tool to `org.osbuild.curl`, since other
    sources might in the future provide resources of type
    `org.osbuild.files`.

  * The `org.osbuild.rpm` stage gained support to not install
    documentation via a new `exclude.docs` option.

  * The `org.osbuild.copy` stage was removed since it does no
    longer fit in the inputs model. It will be re-added with
    proper support for inputs later.

  * Fix a bug where osbuild would create temporary build
    directories in `/var/tmp` instead of a directory within
    the store.

Contributions from: Christian Kellner, Lars Karlitski,
                    Tom Gundersen, Ondřej Budai

— Berlin, 2021-02-12

## CHANGES WITH 24:

  * Add a new `org.osbuild.rhsm` stage to configure the Red Hat
    subscription management. Currently the stage supports only
    enabling or disabling the RHSM DNF plugins.

  * Add a new `org.osbuild.sysconfig` stage that allows for the
    configuration of basic aspects of the system via the files
    located in `/etc/sysconfig`. Currently only a small subset
    of possbile configuration values is supported, for example
    the default kernel.

  * runners: add a runner for CentOS 8. It is currently based on
    the same runner used for RHEL 8.2 and newer.

  * The `org.osbuild.tar` assembler now by default also includes
    the SELinux contexts, POSIX ACLs and extended attributes.
    New stage options can be used to opt-out of any of those.

  * Add support for developing osbuild via Visual Studio Code
    Remote - Containers. This allows easy onboarding as well as
    cross-platform development of osbuild inside VS Code. When
    the osbuild source code folder is opened in VS Code it can
    detect the support for container based development and
    build and use the provided container environment. The
    container itself is based on Fedora.

  * Documentation: describe `--inspect` in the man page

  * Fix a bug so that log text is continuously stream to standard
    out when using osbuild in interactive, i.e. non JSON, mode.

  * spec file: only disable the dep. generator for runners.
    Don't detect dependencies for runners, because they are hand
    crafted to work on a specific platform, i.e. platform-python
    on RHEL. Do pick up dependencies for stages, assemblers, and
    sources, since they are also run on the host.

  * osbuild has seen massive refactoring so that now the internal
    manifest representation is a more generic direct a-cyclic graph
    of pipelines. Additionally a new concept called `Inputs` has
    been introduced. They provide resources to stages in a unified
    way, independently of their origin, i.e. if they were fetched
    via a source or built via a pipeline.
    The reading of the manifest description and the writing of
    results is now done in a format specific way to prepare for
    a new version of the description where the new generic, "dag"
    pipelines can be expressed.

  * Various big improvements to testing, like verifying the tar
    assembler output, using `pytest` as testing framework.

  * As always, CI has been improved, especially the mock build
    phase and how reverse dependency testing against composer
    is done.

Contributions from: Achilleas Koutsou, Christian Kellner, Jacob Kozol,
                    Lars Karlitski, Ondřej Budai, Tomas Hozza

— Berlin, 2021-01-27

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

— Berlin, 2020-06-10

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
