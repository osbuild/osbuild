import glob
import setuptools

setuptools.setup(
    name="osbuild",
    version="1",
    description="A build system for OS images",
    packages=["osbuild"],
    entry_points={
        "console_scripts": ["osbuild = osbuild.executable:main"]
    },
    data_files=[
        ("/usr/lib/osbuild", ["osbuild-run"]),
        ("/usr/lib/osbuild/stages", glob.glob("./stages/*")),
        ("/usr/lib/osbuild/assemblers", glob.glob("./assemblers/*"))
    ]
)