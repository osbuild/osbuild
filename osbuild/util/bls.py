"""
Function for appending parameters to
Boot Loader Specification (BLS).
"""
import glob
import os
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
        with open(entry, encoding="utf8") as f:
            lines = f.read().splitlines()
        with open(entry + ".tmp", "w", encoding="utf8") as f:
            found_opts_line = False
            for line in lines:
                if not found_opts_line and line.startswith('options '):
                    f.write(f"{line} {' '.join(kernel_arguments)}\n")
                    found_opts_line = True
                else:
                    f.write(f"{line}\n")
            if not found_opts_line:
                f.write(f"options {' '.join(kernel_arguments)}\n")
        os.rename(entry + ".tmp", entry)
