import setuptools

setuptools.setup(
    name="osbuild",
    version="12",
    description="A build system for OS images",
    packages=["osbuild", "osbuild.util"],
    license='Apache-2.0',
    entry_points={
        "console_scripts": [
            "osbuild = osbuild.main_cli:main_cli"
        ]
    },
)
