"""
Function for appending parameters to
Boot Loader Specification (BLS).
"""
import glob
from typing import List


def options_append(root_path: str, kernel_arguments: List[str]) -> None:
    """
    Add kernel arguments to the Boot Loader Specification (BLS) configuration files.
    There is unlikely to be more than one BLS config, but just in case, we'll iterate over them.

    Parameters
    ----------

    root_path (str): The root path for locating BLS configuration files.
    kernel_arguments (list): A list of kernel arguments to be added.

    """
    bls_glob = f"{root_path}/loader/entries/*.conf"
    bls_conf_files = glob.glob(bls_glob)
    if len(bls_conf_files) == 0:
        raise RuntimeError(f"no BLS configuration found in {bls_glob}")
    for entry in bls_conf_files:
        # Read in the file and then append to the options line.
        with open(entry, encoding="utf8") as f:
            lines = f.read().splitlines()
        with open(entry, "w", encoding="utf8") as f:
            for line in lines:
                if line.startswith('options '):
                    f.write(f"{line} {' '.join(kernel_arguments)}\n")
                else:
                    f.write(f"{line}\n")
