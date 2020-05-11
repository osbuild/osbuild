===========
osbuild-api
===========

----------------------------------------------
Build-Pipelines for Operating System Artifacts
----------------------------------------------

:Manual section: 1
:Manual group: User Commands

SYNOPSIS
========

| ``osbuild-api`` [ OPTIONS ]

DESCRIPTION
===========

**osbuild-api** is a machine interface to ``osbuild``\(1). It is a build engine
to produce operation system artifacts, including file-system trees, images, and
packages.

OPTIONS
=======

**osbuild-api** reads the pipeline description from standard-input and returns
a result on standard-output. Its behavior can be customized via command line
options. These command-line options control how **osbuild-api** integrates into
the system. They are meant for system-administration. Any option that controls
properties of individual pipeline runs must be passed via standard-input.

--cache-directory=DIRECTORY
        Directory where intermediary artifacts are cached. If not specified,
        intermediary artifacts are discarded immediately. This directory can be
        safely shared between multiple parallel runs.

        This entry is optional. If not given, no entries are cached.

--library-directory=DIRECTORY
        Directory where to take **osbuild** modules from.

        By default, they are taken from `/usr/lib/osbuild`.

--scratch-directory=DIRECTORY
        Directory used to assemble artifacts. This is exclusively used for
        temporary data and will be cleared after each run. You can safely share
        this directory between multiple parallel runs.

        This option is mandatory, unless ``--cache-directory`` is given, in
        which case temporary artifacts are stored in the cache.

EXITCODES
=========

The exit-codes of **osbuild-api** signal the following conditions:

Exitcode: **0**
        Operation finished without any setup errors. This means all command-line
        arguments were parsed correctly, and the environment behaved as
        expected. This does **not** mean that the given pipeline description was
        valid, or that it was produced successfully. This information is
        provided on standard-output (see section **OUTPUT**). A non-zero
        exitcode always signals an abnormal program exit triggered by invalid
        setups, which needs administrator intervention.

Exitcode: **100**
        The **osbuild-api** program was interrupted by the user. This is usually
        triggered by *CTRL+c* on a terminal.

Exitcodes: **101**, **102**, **103**
        The **standard-input**, **standard-output**, or **standard-error** (in
        that order) streams were not provided upon execution of **osbuild-api**.
        The caller must provide valid file-descriptors for all 3 standard
        streams when executing **osbuild-api**.

Exitcode: **104**
        There were invalid arguments passed on the command-line, or mandatory
        arguments were missing.

INPUT
=====

The input to **osbuild-api** is a description of the operation to perform. It
must be passed on standard-input. It is a *JSON* formatted document with the
following structure:

|
| {
|   "**checkpoints**": [
|     "<id-0>",
|     "<id-1>",
|     ...
|     "<id-n>"
|   ],
|
|   "**manifest**": {
|     ...
|   },
|
|   "**output-directory**": "path/to/output/directory"
| }
|

No other entries than the specified entries are allowed. If an entry is not
specified, its default value is assumed.

**checkpoints**
        The **checkpoints** array specifies a list of module IDs that should be
        stored in the shared cache. Whenever the pipeline engine produces a
        stage with the specified ID, it will store it in the cache. All other
        intermediary artifacts are immediately discarded.

        The default value is an empty array.

**manifest**
        The manifest describes a pipeline as well as as the required resources
        to build it. Its format is described in ``osbuild-manifest``\(5).

        The default value is an empty dictionary.

**output-directory**
        The output directory specifies a path to an existing directory where to
        place the produced output artifact.

        This entry is mandatory.

OUTPUT
======

After completion, **osbuild-api** writes its result description to
standard-output. This description is a *JSON* formatted document with the
following structure:

|
| {
|   "**success**": true,
|   "**debug**": {
|     "**stdout**": [ ... ]
|     "**stderr**": [ ... ]
|   }
| }
|

No other entries than the specified entries are produced.

**success**
        This is a boolean that represents whether the pipeline execution
        succeeded.

**debug**
        This is a dictionary of debug information. It may or may not be present.
        Its content is solely meant for debugging by a human.

**debug.stderr**:
        The concatenated standard-error of all stages of the pipeline execution.
        It is split into lines and provided as an array.

**debug.stdout**:
        Similar to **debug.stderr** but for content on standard-output. Note
        that this is intentionally *not* interleaved with standard-error, since
        applications will buffer differently for both streams.

Artifacts are not marshalled as part of the output. Instead, they are stored in
the output-directory specified by the caller in the input description. It is the
caller's responsibility to cleanup the specified output-directory. Note that
under normal operation no data is written to the output-directory on error.
However, during abnormal program exit there might be leftovers. This condition
can be detected by a non-zero exit code (see section **EXITCODES**), or
alternatively if standard-output is closed without a valid *JSON* output
description written to it.

SEE ALSO
========

``osbuild``\(1), ``osbuild-manifest``\(5), ``osbuild-composer``\(1)
