# How to create new release

## Manual version using Packit

Increase the `__version__` variable in `osbuild/__init__.py`. Make a commit
with only that change and tag and push it:
```
$ git tag -a <version-number> -m <some description>
$ git push origin <version-number>
```

Create new release on Github containing the number of this release as a
name, the same number as a tag, and description copied from the previous
one.

```
$ packit status
```
This should show a new release available in upstream
In order to execute this you will need a ~/.config/packit.yaml containing
your FAS account, Pagure token, Github token, and valid Kerberos TGT for
FEDORAPROJECT.ORG realm
```
$ packit propose-update
```
It will create a PR on src.fedoraproject.org.
If everything looks fine, you can merge it.
```
$ packit build
```
Create new koji build
```
$ packit create-update
```
Create Bodhi update


You can also repeat the procedure from 'propose-update' to the end with
different branched of Fedora. You need to do it if you want to get new
version into stable releases.
```
$ packit propose-update --dist-git-branch f31
$ # other commands take the same switch
```

