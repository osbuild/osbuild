"""Introspection and validation for osbuild

This module contains utilities that help to introspect parts
that constitute the inner parts of osbuild, i.e. its stages
and assembler (which is also considered a type of stage in
this context). Additionally, it provides classes and functions
to do schema validation of OSBuild manifests and stage options.

A central `Index` class can be used to obtain stage and schema
information. For the former a `StageInfo` class is returned via
`Index.get_stage_info`, which contains meta-information about
the individual stages. Schemata, obtained via `Index.get_schema`
is represented via a `Schema` class that can in turn be used
to validate the individual components.

The high level `validate` function can be used to check a given
manifest (parsed form JSON input in dictionary form) against all
available schemata. The result is a `ValidationResult` which
contains a single `ValidationError` for each error detected in
the manifest. See the individual documentation for details.
"""
import ast
import contextlib
import copy
import os
import json
from collections import deque
from typing import Dict, Iterable, Optional

import jsonschema


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
        self.path = deque()

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
                assert "new type"

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

    def rebase(self, path: Iterable[str]):
        """Prepend the `path` to `self.path`"""
        rev = reversed(path)
        self.path.extendleft(rev)

    def __hash__(self):
        return hash((self.id, self.message))

    def __eq__(self, other: "ValidationError"):
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
        self.errors = set()

    def fail(self, msg: str) -> ValidationError:
        """Add a new `ValidationError` with `msg` as message"""
        err = ValidationError(msg)
        self.errors.add(err)
        return err

    def add(self, err: ValidationError):
        """Add a `ValidationError` to the set of errors"""
        self.errors.add(err)
        return self

    def merge(self, result: "ValidationResult", *, path=[]):
        """Merge all errors of `result` into this

        Merge all the errors of in `result` into this,
        adjusting their the paths be pre-pending the
        supplied `path`.
        """
        for err in result:
            err = copy.deepcopy(err)
            err.rebase(path)
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

    def __init__(self, schema: str, name: Optional[str] = None):
        self.data = schema
        self.name = name
        self._validator = None

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
            res.fail("missing schema information")
            return res

        try:
            Validator = jsonschema.Draft7Validator
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

        for error in self._validator.iter_errors(target):
            res += ValidationError.from_exception(error)

        return res

    def __bool__(self):
        return self.check().valid


class StageInfo:
    """Meta information about a stage

    Represents the information about a osbuild pipeline
    stage or assembler (here also considered to be a stage).
    Contains the short description (`desc`), a longer
    description (`info`) and the JSON schema of valid options
    (`opts`). The `validate` method will check a the options
    of a stage instance against the JSON schema.

    Normally this class is instantiated via its `load` method.
    """

    def __init__(self, klass: str, name: str, info: str):
        self.name = name
        self.type = klass

        opts = info.get("STAGE_OPTS") or ""
        self.info = info.get("STAGE_INFO")
        self.desc = info.get("STAGE_DESC")
        self.opts = info.get("STAGE_OPTS")
        self.opts = json.loads("{" + opts + "}")

    @property
    def schema(self):
        schema = {
            "title": f"Pipeline {self.type}",
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "options": {
                    "type": "object",
                    **self.opts
                }
            },
            "required": ["name"]
        }

        # if there are is a definitions node, it needs to be at
        # the top level schema node, since the schema inside the
        # stages is written as-if they were the root node and
        # so are the references
        definitions = self.opts.get("definitions")
        if definitions:
            schema["definitions"] = definitions
            del schema["properties"]["options"]["definitions"]

        return schema

    @classmethod
    def load(cls, root, klass, name) -> Optional["StageInfo"]:
        names = ['STAGE_INFO', 'STAGE_DESC', 'STAGE_OPTS']

        def value(a):
            v = a.value
            if isinstance(v, ast.Str):
                return v.s
            return ""

        def filter_type(lst, target):
            return [x for x in lst if isinstance(x, target)]

        def targets(a):
            return [t.id for t in filter_type(a.targets, ast.Name)]

        mapping = {
            "Stage": "stages",
            "Assembler": "assemblers"
        }

        if klass not in mapping:
            raise ValueError(f"Unsupported type: {klass}")

        base = mapping[klass]

        path = os.path.join(root, base, name)
        try:
            with open(path) as f:
                data = f.read()
        except FileNotFoundError:
            return None

        tree = ast.parse(data, name)
        assigns = filter_type(tree.body, ast.Assign)
        targets = [(t, a) for a in assigns for t in targets(a)]
        info = {k: value(v) for k, v in targets if k in names}
        return cls(klass, name, info)


class Index:
    """Index of stages and assemblers

    Class that can be used to get the meta information about
    osbuild stages and assemblers as well as JSON schemata.
    """

    def __init__(self, path: str):
        self.path = path
        self._stage_info = {}
        self._schemata = {}

    def get_stage_info(self, klass, name) -> Optional[StageInfo]:
        """Obtain `StageInfo` for a given stage or assembler"""

        if (klass, name) not in self._stage_info:

            info = StageInfo.load(self.path, klass, name)
            self._stage_info[(klass, name)] = info

        return self._stage_info[(klass, name)]

    def get_schema(self, klass, name=None) -> Schema:
        """Obtain a `Schema` for `klass` and `name` (optional)

        Returns a `Schema` for the entity identified via `klass`
        and `name` (if given). Always returns a `Schema` even if
        no schema information could be found for the entity. In
        that case the actual schema data for `Schema` will be
        `None` and any validation will fail.
        """
        schema = self._schemata.get((klass, name))
        if schema is not None:
            return schema

        if klass == "Manifest":
            path = f"{self.path}/schemas/osbuild1.json"
            with contextlib.suppress(FileNotFoundError):
                with open(path, "r") as f:
                    schema = json.load(f)
        elif klass in ["Stage", "Assembler"]:
            info = self.get_stage_info(klass, name)
            if info:
                schema = info.schema
        else:
            raise ValueError(f"Unknown klass: {klass}")

        schema = Schema(schema, name or klass)
        self._schemata[(klass, name)] = schema

        return schema


def validate(manifest: Dict, index: Index) -> ValidationResult:
    """Validate a OSBuild manifest

    This function will validate a OSBuild manifest, including
    all its stages and assembler and build manifests. It will
    try to validate as much as possible and not stop on errors.
    The result is a `ValidationResult` object that can be used
    to check the overall validation status and iterate all the
    individual validation errors.
    """

    schema = index.get_schema("Manifest")
    result = schema.validate(manifest)

    # main pipeline
    pipeline = manifest.get("pipeline", {})

    # recursively validate the build pipeline  as a "normal"
    # pipeline in order to validate its stages and assembler
    # options; for this it is being re-parented in a new plain
    # {"pipeline": ...} dictionary. NB: Any nested structural
    # errors might be detected twice, but de-duplicated by the
    # `ValidationResult.merge` call
    build = pipeline.get("build", {}).get("pipeline")
    if build:
        res = validate({"pipeline": build}, index=index)
        result.merge(res, path=["pipeline", "build"])

    stages = pipeline.get("stages", [])
    for i, stage in enumerate(stages):
        name = stage["name"]
        schema = index.get_schema("Stage", name)
        res = schema.validate(stage)
        result.merge(res, path=["pipeline", "stages", i])

    asm = pipeline.get("assembler", {})
    if asm:
        name = asm["name"]
        schema = index.get_schema("Assembler", name)
        res = schema.validate(asm)
        result.merge(res, path=["pipeline", "assembler"])

    return result
