"""Introspection and validation for osbuild

This module contains utilities that help to introspect parts
that constitute the inner parts of osbuild, i.e. its stages,
assemblers and sources. Additionally, it provides classes and
functions to do schema validation of OSBuild manifests and
module options.

A central `Index` class can be used to obtain stage and schema
information. For the former a `ModuleInfo` class is returned via
`Index.get_module_info`, which contains meta-information about
the individual stages. Schemata, obtained via `Index.get_schema`
is represented via a `Schema` class that can in turn be used
to validate the individual components.
Additionally, the `Index` also provides meta information about
the different formats and version that are supported to read
manifest descriptions and write output data. Fir this a class
called `FormatInfo` together with `Index.get_format_inf` and
`Index.list_formats` is provided. A `FormatInfo` can also be
inferred for a specific manifest description via a helper
method called `detect_format_info`
"""
import ast
import contextlib
import copy
import importlib.util
import json
import os
import pkgutil
import sys
from collections import deque
from typing import (Any, Deque, Dict, List, Optional, Sequence, Set, Tuple,
                    Union)

import jsonschema

from .util import osrelease

FAILED_TITLE = "JSON Schema validation failed"
FAILED_TYPEURI = "https://osbuild.org/validation-error"


class ValidationError:
    """Describes a single failed validation

    Consists of a `message` member describing the error
    that occurred and a `path` that points to the element
    that caused the error.
    Implements hashing, equality and less-than and thus
    can be sorted and used in sets and dictionaries.
    """

    def __init__(self, message: str):
        self.message = message
        self.path: Deque[Union[int, str]] = deque()

    @classmethod
    def from_exception(cls, ex):
        err = cls(ex.message)
        err.path = ex.absolute_path
        return err

    @property
    def id(self):
        if not self.path:
            return "."

        result = ""
        for p in self.path:
            if isinstance(p, str):
                if " " in p:
                    p = f"'{p}'"
                result += "." + p
            elif isinstance(p, int):
                result += f"[{p}]"
            else:
                raise AssertionError("new type")

        return result

    def as_dict(self):
        """Serializes this object as a dictionary

        The `path` member will be serialized as a list of
        components (string or integer) and `message` the
        human readable message string.
        """
        return {
            "message": self.message,
            "path": list(self.path)
        }

    def rebase(self, path: Sequence[str]):
        """Prepend the `path` to `self.path`"""
        rev = reversed(path)
        self.path.extendleft(rev)

    def __hash__(self):
        return hash((self.id, self.message))

    def __eq__(self, other: object):
        if not isinstance(other, ValidationError):
            raise ValueError("Need ValidationError")

        if self.id != other.id:
            return False
        return self.message == other.message

    def __lt__(self, other: "ValidationError"):
        if not isinstance(other, ValidationError):
            raise ValueError("Need ValidationError")

        return self.id < other.id

    def __str__(self):
        return f"ValidationError: {self.message} [{self.id}]"


class ValidationResult:
    """Result of a JSON Schema validation"""

    def __init__(self, origin: Optional[str]):
        self.origin = origin
        self.errors: Set[ValidationError] = set()

    def fail(self, msg: str) -> ValidationError:
        """Add a new `ValidationError` with `msg` as message"""
        err = ValidationError(msg)
        self.errors.add(err)
        return err

    def add(self, err: ValidationError):
        """Add a `ValidationError` to the set of errors"""
        self.errors.add(err)
        return self

    def merge(self, result: "ValidationResult", *, path=None):
        """Merge all errors of `result` into this

        Merge all the errors of in `result` into this,
        adjusting their the paths be pre-pending the
        supplied `path`.
        """
        for err in result:
            err = copy.deepcopy(err)
            err.rebase(path or [])
            self.errors.add(err)

    def as_dict(self):
        """Represent this result as a dictionary

        If there are not errors, returns an empty dict;
        otherwise it will contain a `type`, `title` and
        `errors` field. The `title` is a human readable
        description, the `type` is a URI identifying
        the validation error type and errors is a list
        of `ValueErrors`, in turn serialized as dict.
        Additionally, a `success` member is provided to
        be compatible with pipeline build results.
        """
        errors = [e.as_dict() for e in self]
        if not errors:
            return {}

        return {
            "type": FAILED_TYPEURI,
            "title": FAILED_TITLE,
            "success": False,
            "errors": errors
        }

    @property
    def valid(self):
        """Returns `True` if there are zero errors"""
        return len(self) == 0

    def __iadd__(self, error: ValidationError):
        return self.add(error)

    def __bool__(self):
        return self.valid

    def __len__(self):
        return len(self.errors)

    def __iter__(self):
        return iter(sorted(self.errors))

    def __str__(self):
        return f"ValidationResult: {len(self)} error(s)"

    def __getitem__(self, key):
        if not isinstance(key, str):
            raise ValueError("Only string keys allowed")

        lst = list(filter(lambda e: e.id == key, self))
        if not lst:
            raise IndexError(f"{key} not found")

        return lst


class Schema:
    """JSON Schema representation

    Class that represents a JSON schema. The `data` attribute
    contains the actual schema data itself. The `klass` and
    (optional) `name` refer to entity this schema belongs to.
    The schema information can be used to validate data via
    the `validate` method.

    The class can be created with empty schema data. In that
    case it represents missing schema information. Any call
    to `validate` will then result in a failure.

    The truth value of this objects corresponds to it having
    schema data.
    """

    def __init__(self, schema: Optional[Dict], name: Optional[str] = None):
        self.data = schema
        self.name = name
        self._validator: Optional[jsonschema.Draft4Validator] = None

    def check(self) -> ValidationResult:
        """Validate the `schema` data itself"""
        res = ValidationResult(self.name)

        # validator is assigned if and only if the schema
        # itself passes validation (see below). Therefore
        # this can be taken as an indicator for a valid
        # schema and thus we can and should short-circuit
        if self._validator:
            return res

        if not self.data:
            msg = "could not find schema information"

            if self.name:
                msg += f" for '{self.name}'"

            res.fail(msg)

            return res

        try:
            Validator = jsonschema.Draft4Validator
            Validator.check_schema(self.data)
            self._validator = Validator(self.data)
        except jsonschema.exceptions.SchemaError as err:
            res += ValidationError.from_exception(err)

        return res

    def validate(self, target) -> ValidationResult:
        """Validate the `target` against this schema

        If the schema information itself is missing, it
        will return a `ValidationResult` in failed state,
        with 'missing schema information' as the reason.
        """
        res = self.check()

        if not res:
            return res

        if not self._validator:
            raise RuntimeError("Trying to validate without validator.")

        for error in self._validator.iter_errors(target):
            res += ValidationError.from_exception(error)

        return res

    def __bool__(self):
        return self.check().valid


class ModuleInfo:
    """Meta information about a stage

    Represents the information about a osbuild pipeline
    modules, like a stage, assembler or source.
    Contains the short description (`desc`), a longer
    description (`info`) and the raw schema data for
    its valid options (`opts`). To use the schema data
    the `get_schema` method can be used to obtain a
    `Schema` object.

    Normally this class is instantiated via its `load` method.
    """

    # Known modules and their corresponding directory name
    MODULES = {
        "Assembler": "assemblers",
        "Device": "devices",
        "Input": "inputs",
        "Mount": "mounts",
        "Source": "sources",
        "Stage": "stages",
    }

    def __init__(self, klass: str, name: str, path: str, info: Dict):
        self.name = name
        self.type = klass
        self.path = path

        self.info = info["info"]
        self.desc = info["desc"]
        self.opts = info["schema"]
        self.caps = info["caps"]

    def _load_opts(self, version, fallback=None):
        raw = self.opts[version]
        if not raw and fallback:
            raw = self.opts[fallback]
        if not raw:
            raise ValueError(f"Unsupported version: {version}")
        return raw

    def _make_options(self, version):
        if version == "2":
            raw = self.opts["2"]
            if not raw:
                return self._make_options("1")
        elif version == "1":
            raw = {"options": self.opts["1"]}
        else:
            raise ValueError(f"Unsupported version: {version}")

        return raw

    def get_schema(self, version="1"):
        schema = {
            "title": f"Pipeline {self.type}",
            "type": "object",
            "additionalProperties": False,
        }

        if self.type in ("Stage", "Assembler"):
            type_id = "type" if version == "2" else "name"
            opts = self._make_options(version)
            schema["properties"] = {
                type_id: {"enum": [self.name]},
                **opts,
            }
            if "mounts" not in schema["properties"]:
                schema["properties"]["mounts"] = {
                    "type": "array"
                }
            schema["required"] = [type_id]
        elif self.type in ("Device"):
            schema["additionalProperties"] = True
            opts = self._load_opts(version, "1")
            schema["properties"] = {
                "type": {"enum": [self.name]},
                "options": opts
            }
        elif self.type in ("Mount"):
            opts = self._load_opts("2")
            schema.update(opts)
            schema["properties"]["type"] = {
                "enum": [self.name],
            }
        else:
            opts = self._load_opts(version, "1")
            schema.update(opts)

        # if there are is a definitions node, it needs to be at
        # the top level schema node, since the schema inside the
        # stages is written as-if they were the root node and
        # so are the references
        props = schema.get("properties", {})
        if "definitions" in props:
            schema["definitions"] = props["definitions"]
            del props["definitions"]

        options = props.get("options", {})
        if "definitions" in options:
            schema["definitions"] = options["definitions"]
            del options["definitions"]

        return schema

    @classmethod
    def _parse_schema(cls, klass, name, node):
        if not node:
            return {}

        value = node.value
        if not isinstance(value, ast.Str):
            return {}

        try:
            return json.loads("{" + value.s + "}")
        except json.decoder.JSONDecodeError as e:
            msg = "Invalid schema: " + e.msg
            line = e.doc.splitlines()[e.lineno - 1]
            fullname = cls.MODULES[klass] + "/" + name
            lineno = e.lineno + node.lineno - 1
            detail = fullname, lineno, e.colno, line
            raise SyntaxError(msg, detail) from None

    @classmethod
    def _parse_caps(cls, _klass, _name, node):
        if not node:
            return set()

        return {e.s for e in node.value.elts}

    @classmethod
    def load(cls, root, klass, name) -> Optional["ModuleInfo"]:
        base = cls.MODULES.get(klass)
        if not base:
            raise ValueError(f"Unsupported type: {klass}")
        path = os.path.join(root, base, name)

        try:
            return cls._load_from_json(path, klass, name)
        except FileNotFoundError:
            # should we print a deprecation warning here?
            pass
        return cls._load_from_py(path, klass, name)

    @classmethod
    def _load_from_json(cls, path, klass, name) -> Optional["ModuleInfo"]:
        # ideas welcome for a better filename/suffix :)
        meta_json_suffix = ".meta-json"
        with open(path + meta_json_suffix, encoding="utf-8") as fp:
            meta = json.load(fp)

        long_description = meta.get("description", "no description provided")
        if isinstance(long_description, list):
            long_description = "\n".join(long_description)

        info = {
            "schema": {
                "1": meta.get("schema", {}),
                "2": meta.get("schema_2", {}),
            },
            "desc": meta.get("summary", "no summary provided"),
            "info": long_description,
            "caps": meta.get("capabilities", set()),
        }
        return cls(klass, name, path, info)

    @classmethod
    def _load_from_py(cls, path, klass, name) -> Optional["ModuleInfo"]:
        names = ["SCHEMA", "SCHEMA_2", "CAPABILITIES"]

        def filter_type(lst, target):
            return [x for x in lst if isinstance(x, target)]

        def targets(a):
            return [t.id for t in filter_type(a.targets, ast.Name)]

        try:
            with open(path, encoding="utf8") as f:
                data = f.read()
        except FileNotFoundError:
            return None

        # using AST here and not importlib because we can read/parse
        # even if some python imports that the module may need are missing
        tree = ast.parse(data, name)

        docstring = ast.get_docstring(tree)
        doclist = docstring.split("\n") if docstring else []
        summary = doclist[0] if len(doclist) > 0 else ""
        long_description = "\n".join(doclist[1:]) if len(doclist) > 0 else ""

        assigns = filter_type(tree.body, ast.Assign)
        values = {
            t: a
            for a in assigns
            for t in targets(a)
            if t in names
        }

        def parse_schema(node):
            return cls._parse_schema(klass, name, node)

        def parse_caps(node):
            return cls._parse_caps(klass, name, node)

        info = {
            'schema': {
                "1": parse_schema(values.get("SCHEMA")),
                "2": parse_schema(values.get("SCHEMA_2")),
            },
            'desc': summary,
            'info': long_description,
            'caps': parse_caps(values.get("CAPABILITIES"))
        }
        return cls(klass, name, path, info)


class FormatInfo:
    """Meta information about a format

    Class the can be used to get meta information about
    the the different formats in which osbuild accepts
    manifest descriptions and writes results.
    """

    def __init__(self, module):
        self.module = module
        self.version = getattr(module, "VERSION")
        docs = getattr(module, "__doc__")
        info, desc = docs.split("\n", 1)
        self.info = info.strip()
        self.desc = desc.strip()

    @classmethod
    def load(cls, name):
        mod = sys.modules.get(name)
        if not mod:
            mod = importlib.import_module(name)
        if not mod:
            raise ValueError(f"Could not load module {name}")
        return cls(mod)


class RunnerInfo:
    """Information about a runner

    Class that represents an actual available runner for a
    specific distribution and version.
    """

    def __init__(self, distro: str, version: int, path: str) -> None:
        self.distro = distro
        self.version = version
        self.path = path

    @classmethod
    def from_path(cls, path: str):
        name = os.path.basename(path)
        distro, version = cls.parse_name(name)
        return cls(distro, version, path)

    @staticmethod
    def parse_name(name: str) -> Tuple[str, int]:
        """Parses a runner name into a string & version tuple

        The name is assumed to be "<name><version>" and version
        to be a single integer. If the name does not contain a
        version suffix it will default to 0.
        """
        version = 0

        i = len(name) - 1

        while i > 0 and name[i].isdigit():
            i -= 1

        vstr = name[i + 1:]
        if vstr:
            version = int(vstr)

        return name[:i + 1], version


class Index:
    """Index of modules and formats

    Class that can be used to get the meta information about
    osbuild modules as well as JSON schemata.
    """

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._module_info: Dict[Tuple[str, Any], Any] = {}
        self._format_info: Dict[Tuple[str, Any], Any] = {}
        self._schemata: Dict[Tuple[str, Any, str], Schema] = {}
        self._runners: List[RunnerInfo] = []
        self._host_runner: Optional[RunnerInfo] = None

    @staticmethod
    def list_formats() -> List[str]:
        """List all known formats for manifest descriptions"""
        base = "osbuild.formats"
        spec = importlib.util.find_spec(base)

        if not spec:
            raise RuntimeError(f"Could not find spec for {base!r}")

        locations = spec.submodule_search_locations
        modinfo = [
            mod for mod in pkgutil.walk_packages(locations)
            if not mod.ispkg
        ]

        return [base + "." + m.name for m in modinfo]

    def get_format_info(self, name) -> FormatInfo:
        """Get the `FormatInfo` for the format called `name`"""
        info = self._format_info.get(name)
        if not info:
            info = FormatInfo.load(name)
            self._format_info[name] = info
        return info

    def detect_format_info(self, data) -> Optional[FormatInfo]:
        """Obtain a `FormatInfo` for the format that can handle `data`"""
        formats = self.list_formats()
        version = data.get("version", "1")
        for fmt in formats:
            info = self.get_format_info(fmt)
            if info.version == version:
                return info
        return None

    def list_modules_for_class(self, klass: str) -> List[str]:
        """List all available modules for the given `klass`"""
        module_path = ModuleInfo.MODULES.get(klass)

        if not module_path:
            raise ValueError(f"Unsupported nodule class: {klass}")

        path = os.path.join(self.path, module_path)
        modules = filter(lambda f: os.path.isfile(f"{path}/{f}") and not path.endswith(".meta-json"),
                         os.listdir(path))
        return list(modules)

    def get_module_info(self, klass, name) -> Optional[ModuleInfo]:
        """Obtain `ModuleInfo` for a given stage or assembler"""

        if (klass, name) not in self._module_info:

            info = ModuleInfo.load(self.path, klass, name)
            self._module_info[(klass, name)] = info

        return self._module_info[(klass, name)]

    def get_schema(self, klass, name=None, version="1") -> Schema:
        """Obtain a `Schema` for `klass` and `name` (optional)

        Returns a `Schema` for the entity identified via `klass`
        and `name` (if given). Always returns a `Schema` even if
        no schema information could be found for the entity. In
        that case the actual schema data for `Schema` will be
        `None` and any validation will fail.
        """
        cached_schema: Optional[Schema] = self._schemata.get((klass, name, version))
        schema = None

        if cached_schema is not None:
            return cached_schema

        if klass == "Manifest":
            path = f"{self.path}/schemas/osbuild{version}.json"
            with contextlib.suppress(FileNotFoundError):
                with open(path, "r", encoding="utf8") as f:
                    schema = json.load(f)
        elif klass in ModuleInfo.MODULES:
            info = self.get_module_info(klass, name)
            if info:
                schema = info.get_schema(version)
        else:
            raise ValueError(f"Unknown klass: {klass}")

        schema = Schema(schema, name or klass)
        self._schemata[(klass, name, version)] = schema

        return schema

    def list_runners(self, distro: Optional[str] = None) -> List[RunnerInfo]:
        """List all available runner modules

        The list is sorted by distribution and version (ascending).
        If `distro` is specified, only runners matching that distro
        will be returned.
        """
        if not self._runners:
            path = os.path.join(self.path, "runners")
            names = filter(lambda f: os.path.isfile(f"{path}/{f}"),
                           os.listdir(path))
            paths = map(lambda n: os.path.join(path, n), names)
            mapped = map(RunnerInfo.from_path, paths)
            self._runners = sorted(mapped, key=lambda r: (r.distro, r.version))

        runners = self._runners[:]
        if distro:
            runners = [r for r in runners if r.distro == distro]

        return runners

    def detect_runner(self, name) -> RunnerInfo:
        """Detect the runner for the given name

        Name here refers to the combination of distribution with an
        optional version suffix, e.g. `org.osbuild.fedora30`.
        This functions will then return the best existing runner,
        i.e. a candidate with the highest version number that
        fullfils the following criteria:
          1) distribution of the candidate matches exactly
          2) version of the candidate is smaller or equal
        If no such candidate exists, a `ValueError` will be thrown.
        """
        name, version = RunnerInfo.parse_name(name)
        candidate = None

        # Get all candidates for the specified distro (1)
        candidates = self.list_runners(name)

        for candidate in reversed(candidates):
            if candidate.version <= version:
                return candidate

        # candidate None or is too new for version (2)
        raise ValueError(f"No suitable runner for {name}")

    def detect_host_runner(self) -> RunnerInfo:
        """Use os-release(5) to detect the runner for the host"""

        if not self._host_runner:
            osname = osrelease.describe_os(*osrelease.DEFAULT_PATHS)
            self._host_runner = self.detect_runner("org.osbuild." + osname)

        return self._host_runner
