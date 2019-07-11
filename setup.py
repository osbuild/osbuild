
import glob
import setuptools

setuptools.setup(
    name="osbuild",
    version="1",
    description="A build system for OS images",
    py_modules=["osbuild"],
    data_files=[
        ("/usr/bin", ["osbuild"]),
        ("/usr/lib/osbuild", ["osbuild-run"]),
        ("/usr/lib/osbuild/stages", glob.glob("./stages/*")),
        ("/usr/lib/osbuild/assemblers", glob.glob("./assemblers/*"))
    ]
)
