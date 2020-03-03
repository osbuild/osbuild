# How to create new release

## Manual version using Packit

```
$ ./bump-version.sh
```
Check that the spec file is correctly modified.
Create new commit from this change; this commit will become the new tag.
```
$ git tag -a <version-number> -m <some description>
$ git push origin <version-number>
```


Create new release on Github containing the number of this release as a
name, the same number as a tag, and description copied from the previous
one.


Once the Github release is available, follow the standard procedure for
creating a Fedora update.
