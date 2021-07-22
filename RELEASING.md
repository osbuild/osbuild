# Making a new release

This guide describes the process of releasing osbuild both [upstream][upstream-git] and into [Fedora][fedora-distgit] and [CentOS Stream][centos-distgit].

## Clone the release helper

Go to the [maintainer-tools repository][maintainer-tools], clone the repository and run `pip install -r requirements.txt` in order to get all the dependencies to be able to execute the `release.py` script.

## Upstream release

Osbuild release is a tagged commit that's merged into the `main` branch as any other contribution.

Navigate to your osbuild repository in your terminal and call the `release.py` script. It will interactively take you through the following steps:

1. Creating a release branch
2. Gathering all changes in the `NEWS.md` file and bumping the version in `osbuild.spec` and `setup.py`
3. Push your changes to your fork and creating a pull request
4. Creating a signed tag for the release
5. Creating a release on GitHub

## Fedora release

We use packit (see `.packit.yml` in this repository or the [official packit documentation][packit-dev]) to automatically create pull requests against all Fedora releases based on our upstream releases.

Hence all you need to do is to navigate to [Fedora package sources][src-fedora] once your release commit is merged to `main` and processed by GitHub Actions.

1. Merge the pull request
2. Get a kerberos ticket by running `kinit $USER@FEDORAPROJECT.ORG`
3. Run `packit build` from your local osbuild repository
4. Check [koji][koji] for the successful build of your release

Please note that in order to merge the new release into the active Fedora releases, you need to be [a Fedora packager][new-fedora-packager] and have commit rights for [the repository][fedora-distgit].

## CentOS Stream 9 release

TBD

## Spreading the word on osbuild.org

The last of releasing a new version is to create a new post on osbuild.org. Just open a PR in [osbuild/osbuild.github.io]. You can find a lot of inspiration in existing release posts.

[upstream-git]: https://github.com/osbuild/osbuild
[fedora-distgit]: https://src.fedoraproject.org/rpms/osbuild
[centos-distgit]: https://gitlab.com/redhat/centos-stream/rpms/osbuild
[maintainer-tools]: https://github.com/osbuild/maintainer-tools
[packit-dev]: https://packit.dev/docs/
[src-fedora]: https://src.fedoraproject.org/rpms/osbuild/pull-requests
[new-fedora-packager]: https://fedoraproject.org/wiki/Join_the_package_collection_maintainers
[osbuild/osbuild.github.io]: https://github.com/osbuild/osbuild.github.io
[koji]: https://koji.fedoraproject.org/koji/packageinfo?packageID=29756