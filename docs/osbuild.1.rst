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

| ``osbuild`` [ OPTIONS ] PIPELINE
| ``osbuild`` [ OPTIONS ] -
| ``osbuild`` ``--help``

DESCRIPTION
===========

**osbuild** is a build-system for operating system artifacts. It takes a
pipeline description as input and produces file-system trees, images, or other
artifacts as output. Its pipeline description gives comprehensive control over
the individual steps to execute as part of a pipeline. **osbuild** provides
isolation from the host system as well as caching capabilities, and thus
ensures that pipeline builds will be deterministic and efficient.

OPTIONS
=======

**osbuild** reads the pipeline description from the file passed on the
command-line. To make **osbuild** read the pipeline description from standard
input, pass ``-``.

The following command-line options are supported. If an option is passed, which
is not listed here, **osbuild** will deny startup and exit with an error.

-h, --help                      print usage information and exit immediately
--store=DIR                     directory where intermediary file system trees
                                are stored
--secrets=PATH                  json file containing a dictionary of secrets
                                that are passed to sources
-l DIR, --libdir=DIR            directory containing stages, assemblers, and
                                the osbuild library
--checkpoint=CHECKPOINT         stage to commit to the object store during
                                build (can be passed multiple times)
--json                          output results in JSON format
--output-directory=DIR          directory where result objects are stored

NB: If neither ``--output-directory`` nor ``--checkpoint`` is specified, no
attempt to build the manifest will be made.

MANIFEST
========

The input to **osbuild** is a description of the pipeline to execute, as well
as required parameters to each pipeline stage. This data must be *JSON*
encoded. It is read from the file specified on the command-line, or, if ``-``
is passed, from standard input.

The format of the manifest is described in ``osbuild-manifest``\(5). The formal
schema of the manifest is available online as the OSBuild JSON Schema [#]_.

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

Example 1: Build a Fedora 30 qcow2 image
----------------------------------------

To build a basic qcow2 image of Fedora 30, use:

    |
    | # osbuild ./samples/base-qcow2.json
    |

The pipeline definition ``./samples/base-rpm-qcow2.json`` is provided in the
upstream source repository of **osbuild**.

Example 2: Run from a local checkout
------------------------------------

To run **osbuild** from a local checkout, use:

    |
    | # python3 -m osbuild --libdir . samples/base-rpm-qcow2.json
    |

This will make sure to execute the **osbuild** module from the current
directory, as well as use it to search for stages, assemblers, and more.

SEE ALSO
========

``osbuild-manifest``\(5), ``osbuild-composer``\(1)

NOTES
=====

.. [#] OSBuild JSON Schema:
       https://osbuild.org/schemas/osbuild1.json
