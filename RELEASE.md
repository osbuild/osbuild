# How to create new release

Use the `bump-version` target to bump the version:

```
$ make bump-version
```
Check that the spec file is correctly modified.
Create new commit from this change; this commit will become the new tag.
The name of the tag should the be the new version number prefixed by `v`.
```
$ git tag -a v<version-number> -m <some description>
$ git push origin <version-number>
```


Create new release on Github containing the number of this release as its
name, the same number as a tag, and description copied from the previous
one.


Once the Github release is available, follow the standard procedure for
creating a Fedora update.
