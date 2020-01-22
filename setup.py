import os
import setuptools

# Mountpoints for osbuild library
data_files = [("/usr/lib/osbuild/stages/osbuild", []),
              ("/usr/lib/osbuild/assemblers/osbuild", [])]
# Copy the osbuild files
for d in ["stages", "assemblers", "runners", "sources"]:
    for root, dnames, fnames in os.walk(d):
        if fnames:
            data_files.append((f"/usr/lib/osbuild/{root}", [f"{root}/{f}" for f in fnames]))

setuptools.setup(
    name="osbuild",
    version="7",
    description="A build system for OS images",
    packages=["osbuild"],
    license='Apache-2.0',
    entry_points={
        "console_scripts": ["osbuild = osbuild.__main__:main"]
    },
    data_files=data_files,
)
