================
osbuild-manifest
================

-----------------------
OSBuild Manifest Format
-----------------------

:Manual section: 5
:Manual group: File Formats Manual

SYNOPSIS
========

|
| {
|   "**pipeline**": {
|     "**build**": { ... },
|     "**stages**": [ ... ],
|     "**assembler**": { ... }
|   },
|
|   "**sources**": {
|     "org.osbuild.files": {
|       "**urls**": {
|         ...
|       }
|     }
|   }
| }
|

DESCRIPTION
===========

The osbuild manifest format describes to ``osbuild``\(1) which build pipeline
to execute and which resources to make available to it. A manifest is always
formatted as a single `JSON` document and must contain all information needed
to execute a specified pipeline. Furthermore, a manifest must be
authoritative in that data passed to ``osbuild``\(1) via other means than the
manifest must not affect the outcome of the pipeline. Therefore, the content of
a manifest deterministicly describes the expected output.

The exact schema of the manifest is available online as the OSBuild JSON
Schema [#]_.

A manifest consists of a fixed amount of top-level sections. These include
sections that describe the steps of the pipeline to execute, but also external
resources to make available to the pipeline execution. The following manual
describe the different sections available in the manifest, as well as short
examples how these sections can look like.

PIPELINES
=========

The `pipeline` section describes the pipeline to execute. This includes a
description of the build system to use for the execution, the stages to
execute, and the final assemblers which produce the desired output format.

|
| "**pipeline**": {
|   "**build**": { ... },
|   "**stages**": [ ... ],
|   "**assembler**": { ... }
| }
|

PIPELINE: build
---------------

The `build` section specifies the system to use when executing stages of a
pipeline. The definition of this section is recursive, in that it requires a
pipeline definition as its value. The build system is created by recursively
executing its pipeline definition first. It is then used as the build system
to execute the pipeline that defined this build system.

Additionally to the pipeline description, a build definition must also define
the runner to use when executing applications in this system. These runners are
shipped with ``osbuild``\(1) and perform environment setup before executing a
stage.

|
| "**build**": {
|   "**pipeline**": {
|     "**build**": { ... },
|     "**stages**": [ ... ],
|     "**assembler**": { ... }
|   },
|   "**runner**": "org.osbuild.linux"
| }
|

PIPELINE: stages
----------------

The `stages` section is an array of stages to execute as part of the pipeline.
Together they produce a file system tree that forms the output of the pipeline.
Each stage can modify the tree, alter its content, or add new data to it. All
stages are executed in sequence, each taking the output of the previous stage
as their input.

|
| "**stages**": [
|   {
|     "**name**": "<stage-A>",
|     "**options**": {
|       ...
|     }
|   },
|   {
|     "**name**": "<stage-B>",
|     "**options**": {
|       ...
|     }
|   }
| ]
|

Stages are shipped together with ``osbuild``\(1). The manifest can optionally
contain options that are passed to the respective stage.

PIPELINE: assembler
-------------------

The assembler is the final stage of a pipeline. It is similar to a `stage` but
always executed last. Furthermore, it is not allowed to modify the file system
tree. Instead, it is expected to take the file system tree and produce a
desired output format for consumption by the user.

|
| "**assembler**": {
|   "**name**": "<assembler-A>",
|   "**options**": {
|     ...
|   }
| }
|

Assemblers are shipped together with ``osbuild``\(1). The manifest can
optionally contain options that are passed to the respective assembler.

SOURCES
=======

The `sources` section describes external resources that are needed to execute a
pipeline. Specified sources do not have to be used by a pipeline execution.
Hence, it is not an error to specify more resources than actually required.

Note:
        The pipeline executor might prefetch resources before executing a
        pipeline. Therefore, you should only specify resources that are
        actually required to execute a pipeline.

The `sources` section thus allows to hide from the pipeline execution where an
external resource comes from and how it is fetched. Instead, it provides an
internal API to the pipeline to access these external resources in a common
way. Depending on which pipeline `stages` are defined, they required different
source types to provide configured resources.

The following sub-sections describe the different available source types. To
configure a specific source type, you would use something like the following:

|
| "**sources**": {
|   "<source-type-A>": {
|     ...
|   },
|   "<source-type-B>": {
|     ...
|   }
| }
|

SOURCE: org.osbuild.files
-------------------------

The `org.osbuild.files` source type allows to provide external files to the
pipeline execution. The argument to this type is a dictionary of file names and
their corresponding resource URIs. The file name must be the hash of the
expected file, prefixed with the hash-type.

The following example shows how you could provide two files to a pipeline
execution via the `org.osbuild.files` source type:

|
| "**sources**": {
|   "org.osbuild.files": {
|     "sha256:<hash-A>": "https://example.com/some-file-A",
|     "sha256:<hash-B>": "https://example.com/some-file-B"
|   }
| }
|

SEE ALSO
========

``osbuild``\(1), ``osbuild-composer``\(1)

NOTES
=====

.. [#] OSBuild JSON Schema:
       https://osbuild.org/schemas/osbuild1.json
