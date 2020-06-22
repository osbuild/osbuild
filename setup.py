import setuptools

setuptools.setup(
    name="osbuild",
    version="18",
    description="A build system for OS images",
    packages=["osbuild", "osbuild.util"],
    license='Apache-2.0',
    install_requires=[
        "jsonschema",
    ],
    entry_points={
        "console_scripts": [
            "osbuild = osbuild.main_cli:osbuild_cli"
        ]
    },
)
