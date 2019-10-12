import glob
import setuptools
import osbuild

setuptools.setup(
    name="osbuild",
    version=osbuild.__version__,
    description="A build system for OS images",
    packages=["osbuild"],
    license='Apache-2.0',
    entry_points={
        "console_scripts": ["osbuild = osbuild.__main__:main"]
    },
)
