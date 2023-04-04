# Making tests for stages

The stage tests are automatically run by the GitHub CI; in order to create a
new test-bed for your new stage do the following:

1. Create a folder with the name of your stage.

   If your stage is named `org.osbuild.my-new-stage` the folder should be named
   `my-new-stage`.

2. Populate the test folder.

   The test folder is expected to have a `a.mpp.json`, `b.mpp.json`, `a.json`,
   `b.json` and `diff.json`.

   `(a|b).mpp.json` and `dif.json`files are the ones that you will need to
   provide, `(a|b).json` will be generated based on the their
   ManifestPreProcessor json file counterpart (`.mpp.json`).

   The `a.mpp.json` file must provide the instructions for a minimal artifact
   build using the minimum amount of pipelines and stages; you must not add
   your new stage to this build. The artifact described in `b.mpp.json` will
   have the same build as the one described in `a.mpp.json` but you must add
   your new stage to the build.

   Once `(a|b).mpp.json` are made, run:

   ```bash
   make test/data/stages/my-new-stage/a.json
   make test/data/stages/my-new-stage/b.json
   ```

   to generate `a.json` and `b.json` respectively.

   During the tests the artifacts described by `a.json` and `b.json` will be
   built and their final states will be compared. In order for your new stage
   test to pass, every change in artifact b's state must have been accounted
   for in the `diff.json` file.

3. Add the five required test files to your commit (`a.mmp.json`, `b.mpp.json`,
   `a.json`, `b.json` and `diff.json`) and the GitHub CI will do the rest.

## Crafting `(a|b).mpp.json` test files

`(a|b).mpp.json` files can be based on OSBuild manifest v1 and v2. v2 is
preferred and is the version used in this guide. You can read about [Manifest
Version
2](https://www.osbuild.org/guides/developer-guide/osbuild.html?highlight=manifest#version-2)
in the OSBuild Guide.


Example of minimal `a.mpp.json`:
```
{
  "version": "2",
  # Specify the pipelines needed by your artifact, at a minimum it should
  # specify a base image. Other pipelines should install any needed
  # dependencies, create files, change permissions etc.
  "pipelines": [
    {
      "mpp-import-pipeline": {
        # check the ../manifests folder for more options
        "path": "../manifests/f34-build-v2.json",
        "id": "build"
      },
      # check osbuild/runners for more options
      "runner": "org.osbuild.fedora34"
    },
    {
      "name": "tree",
      "build": "name:build",
      "stages": [
        {
          # on manifest v1 this field was known as "name", watch out
          "type": "org.osbuild.rpm",
          "inputs": {
            "packages": {
              "type": "org.osbuild.files",
              "origin": "org.osbuild.source",
              # Modify these according to your needs
              "mpp-depsolve": {
                "architecture": "x86_64",
                "module-platform-id": "f34",
                "baseurl": "https://rpmrepo.osbuild.org/v2/mirror/public/f34/f34-x86_64-fedora-20210512/",
                "repos": [
                  {
                    "id": "default",
                    "baseurl": "https://rpmrepo.osbuild.org/v2/mirror/public/f34/f34-x86_64-fedora-20210512/"
                  }
                ],
                "packages": [
                  # Specify the packages needed by your new stage
                  "some-package",
                  "another-package"
                ]
              }
            }
          }
        }
      ]
    }
  ]
}
```

A `b.mpp.json` should have the same manifest as `a.mpp.json` but you should
also add your new stage:
```json
...[omitted]...
{
  "type": "org.osbuild.your-new-stage",
  # the following is stage-specific:
  "options": {
      # add the required options for your stage
      }
    },
  "inputs": {
   # add the required inputs for your stage
  }
}
```

## Crafting `diff.json` files

The `diff.json` file specifies the changes that are expected to be seen in the
new artifact once the results of artifact `b` are compared against the
baseline, artifact `a`.

Sample `diff.json` file:

```json
{
  # List of new files
  "added_files": [
    "/usr/lib/some-new-file",
    "/usr/lib/another-new-file"
  ],
  # List of deleted files
  "deleted_files": [
    "/usr/lib/old-file"
  ],
  # Here you can specify the differences between files, due to changes on
  # the file mode, uid, gid, selinux attributes, file contents, symlinks etc.
  "differences": {
    # specify the file and its differences
    "/etc/some-file.conf": {
      "mode": [
        33188,
        41471
      ],
      "content": [
        "sha256:previous-hash",
        "sha256:new-hash"
      ]
    },
    "/etc/another-file": {
      "symlink": [
        "/usr/share/previous.txt",
        "/usr/share/new.txt"
      ]
    }
  }
}
```
