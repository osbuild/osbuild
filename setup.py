import setuptools

setuptools.setup(
    name="osbuild",
    version="147",
    description="A build system for OS images",
    packages=[
        "osbuild",
        "osbuild.formats",
        "osbuild.solver",
        "osbuild.util",
        "osbuild.util.sbom",
        "osbuild.util.sbom.spdx2",
    ],
    license='Apache-2.0',
    install_requires=[
        "jsonschema",
    ],
    entry_points={
        "console_scripts": [
            "osbuild = osbuild.main_cli:osbuild_cli"
        ]
    },
    scripts=[
        "tools/osbuild-mpp",
        "tools/osbuild-dev",
        "tools/osbuild-image-info",
    ],
)
