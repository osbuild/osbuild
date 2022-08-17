#!/usr/bin/python3
"""
Lorax related utilities: Template parsing and execution

This module contains a re-implementation of the Lorax
template engine, but for osbuild. Not all commands in
the original scripting language are support, but all
needed to run the post install and cleanup scripts.
"""

import contextlib
import glob
import os
import re
import shlex
import shutil
import subprocess
from typing import Any, Dict

import mako.template


def replace(target, patterns):
    finder = [(re.compile(p), s) for p, s in patterns]
    newfile = target + ".replace"

    with open(target, "r", encoding="utf8") as i, open(newfile, "w", encoding="utf8") as o:
        for line in i:
            for p, s in finder:
                line = p.sub(s, line)
            o.write(line)
    os.rename(newfile, target)


def rglob(pathname, *, fatal=False):
    seen = set()
    for f in glob.iglob(pathname):
        if f not in seen:
            seen.add(f)
            yield f
    if fatal and not seen:
        raise IOError(f"nothing matching {pathname}")


class Script:

    # all built-in commands in a name to method map
    commands: Dict[str, Any] = {}

    # helper decorator to register builtin methods
    class command:
        def __init__(self, fn):
            self.fn = fn

        def __set_name__(self, owner, name):
            bultins = getattr(owner, "commands")
            bultins[name] = self.fn
            setattr(owner, name, self.fn)

    # Script class starts here
    def __init__(self, script, build, tree):
        self.script = script
        self.tree = tree
        self.build = build

    def __call__(self):
        for i, line in enumerate(self.script):
            cmd, args = line[0], line[1:]
            ignore_error = False
            if cmd.startswith("-"):
                cmd = cmd[1:]
                ignore_error = True

            method = self.commands.get(cmd)

            if not method:
                raise ValueError(f"Unknown command: '{cmd}'")

            try:
                method(self, *args)
            except Exception:
                if ignore_error:
                    continue
                print(f"Error on line: {i} " + str(line))
                raise

    def tree_path(self, target):
        dest = os.path.join(self.tree, target.lstrip("/"))
        return dest

    @command
    def append(self, filename, data):
        target = self.tree_path(filename)
        dirname = os.path.dirname(target)
        os.makedirs(dirname, exist_ok=True)
        print(f"append '{target}' '{data}'")
        with open(target, "a", encoding="utf8") as f:
            f.write(bytes(data, "utf8").decode("unicode_escape"))
            f.write("\n")

    @command
    def mkdir(self, *dirs):
        for d in dirs:
            print(f"mkdir '{d}'")
            os.makedirs(self.tree_path(d), exist_ok=True)

    @command
    def move(self, src, dst):
        src = self.tree_path(src)
        dst = self.tree_path(dst)

        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src))

        print(f"move '{src}' -> '{dst}'")
        os.rename(src, dst)

    @command
    def install(self, src, dst):
        dst = self.tree_path(dst)
        for s in rglob(os.path.join(self.build, src.lstrip("/")), fatal=True):
            with contextlib.suppress(shutil.Error):
                print(f"install {s} -> {dst}")
                shutil.copy2(os.path.join(self.build, s), dst)

    @command
    def remove(self, *files):
        for g in files:
            for f in rglob(self.tree_path(g)):
                if os.path.isdir(f) and not os.path.islink(f):
                    shutil.rmtree(f)
                else:
                    os.unlink(f)
                print(f"remove '{f}'")

    @command
    def replace(self, pat, repl, *files):
        found = False
        for g in files:
            for f in rglob(self.tree_path(g)):
                found = True
                print(f"replace {f}: {pat} -> {repl}")
                replace(f, [(pat, repl)])

        if not found:
            assert found, f"No match for {pat} in {' '.join(files)}"

    @command
    def runcmd(self, *args):
        print("run ", " ".join(args))
        subprocess.run(args, cwd=self.tree, check=True)

    @command
    def symlink(self, source, dest):
        target = self.tree_path(dest)
        if os.path.exists(target):
            self.remove(dest)
        print(f"symlink '{source}' -> '{target}'")
        os.symlink(source, target)

    @command
    def systemctl(self, verb, *units):
        assert verb in ('enable', 'disable', 'mask')
        self.mkdir("/run/systemd/system")
        cmd = ['systemctl', '--root', self.tree, '--no-reload', verb]

        for unit in units:
            with contextlib.suppress(subprocess.CalledProcessError):
                args = cmd + [unit]
                self.runcmd(*args)


def brace_expand(s):
    if not ('{' in s and ',' in s and '}' in s):
        return [s]

    result = []
    right = s.find('}')
    left = s[:right].rfind('{')
    prefix, choices, suffix = s[:left], s[left+1:right], s[right+1:]
    for choice in choices.split(','):
        result.extend(brace_expand(prefix+choice+suffix))

    return result


def brace_expand_line(line):
    return [after for before in line for after in brace_expand(before)]


def render_template(path, args):
    """Render a template at `path` with arguments `args`"""

    with open(path, "r", encoding="utf8") as f:
        data = f.read()

    tlp = mako.template.Template(text=data, filename=path)
    txt = tlp.render(**args)

    lines = map(lambda l: l.strip(), txt.splitlines())
    lines = filter(lambda l: l and not l.startswith("#"), lines)
    commands = map(shlex.split, lines)
    commands = map(brace_expand_line, commands)

    result = list(commands)
    return result
