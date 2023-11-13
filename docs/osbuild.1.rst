=======
osbuild
=======

----------------------------------------------
Build-Pipelines for Operating System Artifacts
----------------------------------------------

:Manual section: 1
:Manual group: User Commands

SYNOPSIS
========

| ``osbuild`` [ OPTIONS ] MANIFEST
| ``osbuild`` [ OPTIONS ] -
| ``osbuild`` ``--help``
| ``osbuild`` ``--version``

DESCRIPTION
===========

**osbuild** is a build-system for operating system artifacts. It takes an input
manifest describing the build pipelines and produces file-system trees, images,
or other artifacts as output. Its pipeline description gives comprehensive
control over the individual steps to execute as part of a pipeline. **osbuild**
provides isolation from the host system as well as caching capabilities, and
thus ensures that pipeline builds will be deterministic and efficient.

OPTIONS
=======

**osbuild** reads the pipeline description from the file passed on the
command-line. To make **osbuild** read the pipeline description from standard
input, pass ``-``.

The following command-line options are supported. If an option is passed, which
is not listed here, **osbuild** will deny startup and exit with an error.

-h, --help                      print usage information and exit immediately
--version                       print version information and exit immediately
--store=DIR                     directory where intermediary file system trees
                                are stored
-l DIR, --libdir=DIR            directory containing stages, assemblers, and
                                the osbuild library
--cache-max-size=SIZE           maximum size of the cache (bytes) or 'unlimited'
                                for no restriction (size may include an optional
                                unit suffix, like kB, kiB, MB, MiB and so on)
--checkpoint=CHECKPOINT         stage to commit to the object store during
                                build (can be passed multiple times)
--export=OBJECT                 object to export (can be passed multiple times)
--json                          output results in JSON format
--output-directory=DIR          directory where result objects are stored
--inspect                       return the manifest in JSON format including
                                all the ids
--monitor=TYPE                  name of the monitor to be used
--monitor-fd=NUM                file-descriptor to be used for the monitor
--stage-timeout                 set the maximal time (in seconds) each stage is
                                allowed to run

NB: If neither ``--output-directory`` nor ``--checkpoint`` is specified, no
attempt to build the manifest will be made.

MANIFEST
========

The input to **osbuild** is a description of the pipelines to execute, as well
as required parameters to each pipeline stage. This data must be *JSON*
encoded. It is read from the file specified on the command-line, or, if ``-``
is passed, from standard input.

The format of the manifest is described in ``osbuild-manifest``\(5). The formal
schema of the manifest is available online as the OSBuild JSON Schema [#]_.

MONITOR
=======

Live activity of the pipeline execution can be monitored via a built-in set
of different monitors. The ``--monitor=TYPE`` option selects the type of
monitor that is used. Valid types are:

``NullMonitor``
        No live coverage is reported and all monitoring features are disabled.
        This is the default monitor if ``--json`` was specified on the
        command-line.
``LogMonitor``
        A human-readable live monitor of the pipeline execution. This monitor
        prints pipeline names, stage names, and relevant options of each stage
        as it is executed. Additionally, timing information is provided for
        each stage. The output is not machine-readable and is interspersed
        with the individual log messages of the stages.
        This is the default monitor if ``--json`` was **not** specified.

Monitor output is written to the file-descriptor provided via
``--monitor-fd=NUM``. If none was specified, standard output is used.

OUTPUT
======

OSBuild only ever builds the requested artifacts, rather than all artifacts
defined in a manifest. Each stage and pipeline has an associated ID (which can
be acquired by passing ``--inspect``). To export an artifact after a stage or
pipeline finished, pass its ID via ``--export=ID``. A sub-directory will be
created in the output-directory with the ID as the name. The contents of the
artifact are then stored in that sub-directory.

Additionally, any completed pipeline or stage can be cached to avoid rebuilding
them in subsequent invocations. Use ``--checkpoint=ID`` to request caching of a
specific stage or pipeline.

EXAMPLES
========

The following sub-sections contain examples on running **osbuild**. Generally,
**osbuild** must be run with superuser privileges, since this is required to
create file-system images.

Example 1: Run an empty pipeline
--------------------------------

To verify your **osbuild** setup, you can run it on an empty pipeline which
produces no output:

    |
    | # echo {} | osbuild -
    |

Example 1: Build a Fedora 34 qcow2 image
----------------------------------------

To build a basic qcow2 image of Fedora 34, use:

    |
    | # osbuild ./samples/fedora-boot.json
    |

The pipeline definition ``./samples/fedora-boot.json`` is provided in the
upstream source repository of **osbuild**.

Example 2: Run from a local checkout
------------------------------------

To run **osbuild** from a local checkout, use:

    |
    | # python3 -m osbuild --libdir . samples/fedora-boot.json
    |

This will make sure to execute the **osbuild** module from the current
directory, as well as use it to search for stages, assemblers, and more.

SEE ALSO
========

``osbuild-manifest``\(5), ``osbuild-composer``\(1)

NOTES
=====

.. [#] OSBuild JSON Schema v2:
       https://osbuild.org/schemas/osbuild2.json
