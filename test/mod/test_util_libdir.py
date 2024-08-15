from osbuild.util.libdir import Libdir


def test_libdir_libdir():
    ld = Libdir("/foo")
    assert ld.libdir == "/foo"
    ld = Libdir("/foo:/bar")
    assert ld.libdir == "/foo:/bar"
    # paths are normalized
    ld = Libdir("/../foo:/bar/./")
    assert ld.libdir == "/foo:/bar"


def test_libdir_dirs():
    ld = Libdir("/foo")
    assert ld.dirs == ["/foo"]
    ld = Libdir("/foo:/bar")
    assert ld.dirs == ["/foo", "/bar"]


def test_libdir_buildroot_dirs():
    ld = Libdir("/foo")
    assert ld.buildroot_dirs == ["/run/osbuild/lib"]
    ld = Libdir("/foo:/bar")
    assert ld.buildroot_dirs == ["/run/osbuild/lib", "/run/osbuild/lib1"]


def test_libdir_buildroot_libdir():
    ld = Libdir("/foo")
    assert ld.buildroot_libdir == "/run/osbuild/lib"
    ld = Libdir("/foo:/bar")
    assert ld.buildroot_libdir == "/run/osbuild/lib:/run/osbuild/lib1"
