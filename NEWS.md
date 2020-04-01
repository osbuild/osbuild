# OSBuild - Build-Pipelines for Operating System Artifacts

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
	      issue that made this neccessary got fixed upstream.

		* Ensure the build tree is always being built even if there are no
		  stages specified.

		* spec file: Do no generate dependencies for the internal files and
		  add NEWS.md to the documentation section.

	    * The Fedora 30 based aarch64 example was fixed and now builds again.

        Contributions from: Christian Kellner, David Rheinsberg, Lars Karlitski,
		                    Major Hayden, Ondřej Budai

        - Berlin, 2020-04-01

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

        - Berlin, 2020-03-18

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

        - Berlin, 2020-03-05

## CHANGES BEFORE 9:

        * Initial implementation of 'osbuild'.

        Contributions from: Brian C. Lane, Christian Kellner, David Rheinsberg,
                            Jacob Kozol, Lars Karlitski, Major Hayden, Martin
                            Sehnoutka, Ondřej Budai, Sehny, Tom Gundersen,
                            Tomas Tomecek, Will Woods
