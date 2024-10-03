import json
import pathlib
import subprocess

from osbuild.solver import SolverBase

CONFIGURATION_TEMPLATE = """
[options]
Architecture = {architecture}
CheckSpace
SigLevel    = Required DatabaseOptional
LocalFileSigLevel = Optional
"""

REPOSITORY_TEMPLATE = """
[{id}]
Server = {url}
"""

# Output format for pacman that's close enough to JSON to pretend it
# is JSON
PRINT_FORMAT = '{"url": "%l", "version": "%v", "name": "%n"},'


def _parse_package_info(text: str) -> dict[str, str]:
    lines = text.split("\n")

    def parse_line(l):
        k, v = l.split(":", maxsplit=1)
        return k.strip(), v.strip()

    return dict(parse_line(line) for line in lines if ":" in line)


class Pacman(SolverBase):
    def __init__(self, request: dict, cache_path: str) -> None:
        self._cache_path = pathlib.Path(cache_path)

        self._etc_path = self._cache_path / "etc"
        self._cfg_path = self._etc_path / "pacman.conf"

        self._lib_path = self._cache_path / "var/lib/pacman"

        self._architecture = request["arch"]
        self._repositories = request.get("arguments", {}).get("repos", [])

    def _prepare_root(self) -> None:
        """Prepares a pacman root for a our architecture by preparing the
        necessary directories and writing a pacman configuration file that
        includes the configured repositories."""

        self._etc_path.mkdir(parents=True, exist_ok=True)
        self._lib_path.mkdir(parents=True, exist_ok=True)

        text = CONFIGURATION_TEMPLATE.format(architecture=self._architecture)

        for repository in self._repositories:
            text = text + REPOSITORY_TEMPLATE.format(
                id=repository["id"], url=repository["baseurl"]
            )

        self._cfg_path.write_text(text)

    def depsolve(self, arguments: dict) -> dict:
        self._prepare_root()

        # Ensure there is exactly one transaction given by unpacking the given
        # transactions into a single name
        (transaction,) = arguments.get("transactions", [])

        # Run pacman's sync and refresh first to make sure the root is valid
        subprocess.run(
            [
                "pacman", "-Sy",
                "--root", str(self._cache_path),
                "--config", str(self._cfg_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

        # Pacman does not have any form of JSON output so we're going to build
        # JSON with string formatting!
        result = subprocess.run(
            [
                "pacman", "-S",
                "--print",
                "--print-format", PRINT_FORMAT,
                "--sysroot", str(self._cache_path),
                *transaction["package-specs"]["include"],
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.decode("utf-8")

        result = result.strip().rstrip(",")
        result = f"[{result}]"

        # The certainty of this being valid JSON is: "uhh, maybe" so let's try
        # to load it.
        selected = json.loads(result)
        packages = []

        for selection in selected:
            # We need to request more information from pacman for each package
            text = subprocess.run(
                [
                    "pacman", "-Sii",
                    "--sysroot", str(self._cache_path),
                    selection["name"],
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.decode("utf-8")

            info = _parse_package_info(text)

            packages.append({
                "name": selection["name"],
                "version": selection["version"],
                "url": selection["url"],

                "arch": info["Architecture"],

                "license": info.get("Licenses"),
                "description": info.get("Description"),
                "buildtime": info.get("Build Date"),
            })

        return {
            "solver": "pacman",
            "packages": packages,
            "repos": self._repositories,
        }

    def dump(self):
        raise NotImplementedError()

    def search(self, _):
        raise NotImplementedError()
