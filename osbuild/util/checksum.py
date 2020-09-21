"""checksum utility functions"""

import subprocess

def verify_checksum(filename, checksum):
    """Verify that the contents of the file match the checksum

    :param filename: path of the file to check
    :type filename: str
    :param checksum: expected checksum of the file's contents
    :type checksum: str
    :returns: True if the checksum matches
    :rtype: bool

    The checksum uses the standard osbuild checksum specification where the algorithm
    to use is a prefix to the checksum, separated by a : (colon).
    """
    algorithm, checksum = checksum.split(":", 1)
    if algorithm not in ("md5", "sha1", "sha256", "sha384", "sha512"):
        raise RuntimeError(f"unsupported checksum algorithm: {algorithm}")

    ret = subprocess.run(
        [f"{algorithm}sum", "-c"],
        input=f"{checksum} {filename}",
        stdout=subprocess.DEVNULL,
        encoding="utf-8",
        check=False
    )

    return ret.returncode == 0
