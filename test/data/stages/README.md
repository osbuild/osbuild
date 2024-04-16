# Making integration tests for stages

The stage integration tests are automatically run by the GitHub CI; in order to create a
new test-bed for your new stage do the following:

1. Create a folder with the name of your stage.

   If your stage is named `org.osbuild.my-new-stage` the folder should be named
   `my-new-stage`.

2. Populate the test folder.

   The test folder is expected to have a `a.mpp.yaml`, `b.mpp.yaml`, `a.json`,
   `b.json` and `diff.json`.

   `(a|b).mpp.yaml` and `dif.json`files are the ones that you will need to
   provide, `(a|b).json` will be generated based on the their
   ManifestPreProcessor json file counterpart (`.mpp.yaml`).

   The `a.mpp.yaml` file must provide the instructions for a minimal artifact
   build using the minimum amount of pipelines and stages; you must not add
   your new stage to this build. The artifact described in `b.mpp.yaml` will
   have the same build as the one described in `a.mpp.yaml` but you must add
   your new stage to the build.

   Once `(a|b).mpp.yaml` are made, run:

   ```bash
   make test/data/stages/my-new-stage/a.json
   make test/data/stages/my-new-stage/b.json
   ```

   to generate `a.json` and `b.json` respectively.

   During the tests the artifacts described by `a.json` and `b.json` will be
   built and their final states will be compared. In order for your new stage
   test to pass, every change in artifact b's state must have been accounted
   for in the `diff.json` file.

3. Add the five required test files to your commit (`a.mmp.yaml`, `b.mpp.yaml`,
   `a.json`, `b.json` and `diff.json`) and the GitHub CI will do the rest.

## Crafting `(a|b).mpp.yaml` test files

`(a|b).mpp.yaml` files can be based on OSBuild manifest v1 and v2. v2 is
preferred and is the version used in this guide. You can read about [Manifest
Version
2](https://github.com/osbuild/osbuild/blob/main/docs/osbuild-manifest.5.rst).


Example of minimal `a.mpp.yaml`:
```yaml
version: '2'
pipelines:
  - mpp-import-pipelines:
      path: ../manifests/fedora-vars.ipp.yaml

      # If the build pipeline doesn't specify all packages needed for your
      # test, feel free to add them. The goal is to have one build pipeline
      # for everything to utilize caching as much as possible.
  - mpp-import-pipeline:
      path: ../manifests/fedora-build-v2.ipp.yaml
      id: build
    runner:
      mpp-format-string: org.osbuild.fedora{release}
  - name: tree
    build: name:build
    stages:
      - type: org.osbuild.rpm
        inputs:
          packages:
            type: org.osbuild.files
            origin: org.osbuild.source
            mpp-depsolve:
              architecture: $arch
              module-platform-id: $module_platform_id
              repos:
                mpp-eval: repos
              packages:
                # Specify the packages needed by your new stage
                - some-package
                - another-package
        options:
          gpgkeys:
            mpp-eval: gpgkeys
          exclude:
            docs: true
```

A `b.mpp.yaml` should have the same manifest as `a.mpp.yaml` but you should
also add your new stage:
```yaml

version: '2'
pipelines:
  # [pipeline imports omitted]
  - name: tree
    build: name:build
    stages:
      - type: org.osbuild.rpm
        # [options of the rpm stage omitted]
      - type: org.osbuild.your-new-stage
        options:
          # add the required options for your stage
        inputs:
          # add the required inputs for your stage
```

## Crafting `diff.json` files

The `diff.json` file specifies the changes that are expected to be seen in the
new artifact once the results of artifact `b` are compared against the
baseline, artifact `a`.

You can easily generate them using the `tools/gen-stage-test-diff` tool:

```
sudo tools/gen-stage-test-diff \
  --store ~/osbuild-store \
  --libdir . \
  test/data/stages/your-new-stage >test/data/stages/your-new-stage/diff.json
```

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
