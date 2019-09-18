import copy
import fnmatch
import json
import subprocess
from dataclasses import dataclass
from typing import List


def compare_trees(a, b):
    result = subprocess.run(["./tree-diff", a, b], stdout=subprocess.PIPE, check=True)
    return json.loads(result.stdout)


@dataclass
class File:
    path: str
    mode: bool = False
    uid: bool = False
    gid: bool = False
    selinux: bool = False
    content: bool = False


def assert_tree_changes(tree_diff, added=[], deleted=[], modified: List[File] = [], ignored: List[str] = [],
                        allow_other_changes=False):
    pending_additions: List[str] = copy.copy(tree_diff['added_files'])
    pending_deletions: List[str] = copy.copy(tree_diff['deleted_files'])
    pending_modifications = copy.copy(tree_diff['differences'])

    for file in added:
        actually_added = fnmatch.filter(tree_diff['added_files'], file)
        if not actually_added:
            raise AssertionError(f"File {file} expected to be added but it was not!")
        for to_remove in actually_added:
            pending_additions.remove(to_remove)

    for file in deleted:
        actually_deleted = fnmatch.filter(tree_diff['deleted_files'], file)
        if not actually_deleted:
            raise AssertionError(f"File {file} expected to be deleted but it was not!")
        for to_remove in actually_deleted:
            pending_deletions.remove(to_remove)

    for file in modified:
        allowed_changes = [key for (key, value) in file.__dict__.items() if value and key != 'path']
        matching_modifications = fnmatch.filter(tree_diff['differences'].keys(), file.path)
        if not matching_modifications:
            raise AssertionError(f"File {file.path} expected to be modified!")
        for mod in matching_modifications:
            differences = tree_diff['differences'][mod]
            for allowed_change in allowed_changes:
                if allowed_change not in differences:
                    raise AssertionError(f"File {file.path} expected to have {allowed_change} modification!")
                del differences[allowed_change]

    for file in ignored:
        matching_modifications = fnmatch.filter(pending_modifications.keys(), file)
        for mod in matching_modifications:
            del pending_modifications[mod]

        matching_additions = fnmatch.filter(pending_additions, file)
        for add in matching_additions:
            pending_additions.remove(add)

        matching_deletions = fnmatch.filter(pending_deletions, file)
        for add in matching_deletions:
            pending_deletions.remove(add)

    for path in list(pending_modifications):
        if not pending_modifications[path]:
            del pending_modifications[path]

    if not allow_other_changes:
        if pending_additions or pending_deletions or pending_modifications:
            report = {'added': pending_additions, 'deleted': pending_deletions, 'differences': pending_modifications}
            raise AssertionError(f"Unspecified changes are not allowed, but found:\n{json.dumps(report, indent=2)}")
