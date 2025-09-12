#!/usr/bin/python3
import io
import re
import sys
from typing import List

import osbuild.api


class ValidationError(ValueError):

    def __init__(self, field: str, value: str, reason, *kargs):
        super().__init__(*kargs)

        self.field = field
        self.value = value
        self.reason = reason

    def __str__(self):
        return f"Error: sysuser entry '{self.field}={self.value}' is invalid: {self.reason}"


# This regex needs to be kept in sync with the regex in the .meta.json schema
SYSUSER_NAME_REGEX = r'^([a-z]+(?:[-_][a-zA-Z0-9_-]{0,30})?|-)$'


class SysusersEntry:
    def __init__(self, entry_type: str, name: str, entry_id: str, gecos: str, home: str, shell: str):
        self.type = entry_type
        self.name = name
        self.id = entry_id
        self.gecos = gecos
        self.home = home
        self.shell = shell

    def validate_type(self):
        valid_types = ["u", "u!", "g", "m", "r"]
        if self.type not in valid_types:
            raise ValidationError("Type", self.type, f"type needs to be one of: {valid_types}")

    def validate_name(self):
        if self.type == "r" and self.name != "-":
            raise ValidationError("Name", self.name, "name needs to be '-' for type 'r'")
        if re.fullmatch(SYSUSER_NAME_REGEX, self.name) is None:
            raise ValidationError("Name", self.name, f"name needs to match regex '{SYSUSER_NAME_REGEX}'")

    def validate_id(self):
        reserved_ids = [65535, 4294967295]

        def check(delim: str):
            parts = self.id.split(delim)
            if len(parts) > 2:
                raise ValidationError("ID", self.id, "invalid format")
            for part in parts:
                if int(part) in reserved_ids:
                    raise ValidationError("ID", self.id, f"id can not be {reserved_ids}")

        if self.type == "m":
            if re.fullmatch(SYSUSER_NAME_REGEX, self.id) is None:
                raise ValidationError("ID", self.id, "id should be group name for m entry")
        elif self.type == "r":
            check("-")
        else:
            if self.id == "-":
                return
            check(":")

    def validate(self):
        self.validate_type()
        self.validate_name()
        self.validate_id()

        if self.type != "u":
            if self.gecos not in ["", "-"]:
                raise ValidationError("GECOS", self.gecos, "gecos only used for type 'u'")
            if self.home not in ["", "-"]:
                raise ValidationError("Home", self.gecos, "home directory only used for type 'u'")
            if self.shell not in ["", "-"]:
                raise ValidationError("Shell", self.gecos, "shell only used for type 'u'")


class SysusersFile:

    def __init__(self, entries: List[SysusersEntry]):
        self.entries = entries

    def validate(self):
        for entry in self.entries:
            entry.validate()

    def write(self, dest: io.BufferedWriter):
        for entry in self.entries:
            gecos = entry.gecos if entry.gecos == "-" else f"\"{entry.gecos}\""
            line = f"{entry.type} {entry.name} {entry.id} {gecos} {entry.home} {entry.shell}".strip() + "\n"
            dest.write(line)


def main(args):
    tree = args["tree"]
    options = args["options"]

    config = options.get("config", None)
    if config is None:
        raise ValueError("'config' is required")

    sysuser_d_dir = "usr/lib/sysusers.d"
    path_prefix = config.get("path-prefix")
    if path_prefix == "etc":
        sysuser_d_dir = "etc/sysusers.d"

    filename = config.get("filename", "")
    if not filename:
        raise ValueError("'filename' is required")
    if not filename.endswith(".conf"):
        raise ValueError(f"Name of file '{filename}' needs to have .conf file extension")
    entries = config.get("entries", [])
    if not entries:
        raise ValueError("'entries' is required")

    sysuser_file = SysusersFile([])
    for entry in entries:
        sysuser_file.entries.append(
            SysusersEntry(
                entry.get("type", ""),
                entry.get("name", ""),
                entry.get("id", "-"),
                entry.get("gecos", "-"),
                entry.get("home", "-"),
                entry.get("shell", "-"),
            )
        )
    sysuser_file.validate()

    with open(f"{tree}/{sysuser_d_dir}/{filename}", "w", encoding="utf-8") as f:
        sysuser_file.write(f)
    print(f"Wrote file '{sysuser_d_dir}/{filename}'")

    return 0


if __name__ == '__main__':
    parsed_args = osbuild.api.arguments()
    r = main(parsed_args)
    sys.exit(r)
