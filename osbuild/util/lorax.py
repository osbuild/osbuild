#!/usr/bin/python3
"""
Lorax related utilities: Template parsing and execution

This module contains a re-implementation of the Lorax
template engine, but for osbuild. Not all commands in
the original scripting language are support, but all
needed to run the post install and cleanup scripts.
"""

import contextlib
import fnmatch
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
        self._pkgnames = None

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

    def _all_pkgnames(self):
        """ Get the list of all package names installed
        On first call it runs rpm -qa and caches the results
        """
        if not self._pkgnames:
            cmd = ["rpm", "-qa", "--root", self.tree, "--qf=%{name}\n"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE,
                                 check=True, encoding="utf8")
            self._pkgnames = sorted(res.stdout.splitlines())
        return self._pkgnames

    def _get_pkgfiles(self, pkg):
        """ Get a list of the files installed by a package """
        cmd = ["rpm", "-ql", "--root", self.tree, pkg]
        res = subprocess.run(cmd, stdout=subprocess.PIPE,
                             check=True, encoding="utf8")
        return sorted(res.stdout.splitlines())

    def _filelist(self, *pkg_specs):
        """ Return the list of files in the packages matching the globs """
        pkglist = []
        for pkg in self._all_pkgnames():
            if any(fnmatch.fnmatch(pkg, spec) for spec in pkg_specs):
                pkglist.append(pkg)

        # Return the files, not directories
        return set(f for pkg in pkglist for f in self._get_pkgfiles(pkg) if not os.path.isdir(self.tree_path(f)))

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

    @command
    def removepkg(self, *pkgs):
        """
        removepkg PKGGLOB [PKGGLOB...]
          Delete the named package(s).

        IMPLEMENTATION NOTES:
          RPM scriptlets (%preun/%postun) are *not* run.
          Files are deleted, but directories are left behind.
        """
        for p in pkgs:
            filepaths = [f.lstrip('/') for f in self._filelist(p)]
            if filepaths:
                self.remove(*filepaths)
            else:
                print(f"removepkg {p}: no files to remove!")

    @command
    def removefrom(self, pkg, *globs):
        """
        removefrom PKGGLOB [--allbut] FILEGLOB [FILEGLOB...]
          Remove all files matching the given file globs from the package
          (or packages) named.
          If '--allbut' is used, all the files from the given package(s) will
          be removed *except* the ones which match the file globs.

          Examples:
            removefrom usbutils /usr/bin/*
            removefrom xfsprogs --allbut /bin/*
        """
        cmd = f"{pkg} {' '.join(globs)}"  # save for later logging
        keepmatches = False
        if globs[0] == '--allbut':
            keepmatches = True
            globs = globs[1:]
        # get pkg filelist and find files that match the globs
        filelist = self._filelist(pkg)
        matches = set()
        for g in globs:
            globs_re = re.compile(fnmatch.translate(g))
            m = [f for f in filelist if globs_re.match(f)]
            if m:
                matches.update(m)
            else:
                print(f"removefrom {pkg} {g}: no files matched!")
        if keepmatches:
            remove_files = filelist.difference(matches)
        else:
            remove_files = matches
        # remove the files
        if remove_files:
            self.remove(*remove_files)
        else:
            print(f"removefrom {cmd}: no files to remove!")

    # pylint: disable=anomalous-backslash-in-string
    @command
    def removekmod(self, *globs):
        '''
        removekmod GLOB [GLOB...] [--allbut] KEEPGLOB [KEEPGLOB...]
          Remove all files and directories matching the given file globs from the kernel
          modules directory.

          If '--allbut' is used, all the files from the modules will be removed *except*
          the ones which match the file globs. There must be at least one initial GLOB
          to search and one KEEPGLOB to keep. The KEEPGLOB is expanded to be *KEEPGLOB*
          so that it will match anywhere in the path.

          This only removes files from under /lib/modules/\\*/kernel/

          Examples:
            removekmod sound drivers/media drivers/hwmon drivers/video
            removekmod drivers/char --allbut virtio_console hw_random
        '''
        cmd = " ".join(globs)
        if "--allbut" in globs:
            idx = globs.index("--allbut")
            if idx == 0:
                raise ValueError("removekmod needs at least one GLOB before --allbut")

            # Apply keepglobs anywhere they appear in the path
            keepglobs = globs[idx + 1:]
            if len(keepglobs) == 0:
                raise ValueError("removekmod needs at least one GLOB after --allbut")

            globs = globs[:idx]
        else:
            # Nothing to keep
            keepglobs = []

        filelist = set()
        for g in globs:
            for top_dir in rglob(self.tree_path(f"/lib/modules/*/kernel/{g}")):
                for root, _dirs, files in os.walk(top_dir):
                    filelist.update(f"{root}/{f}" for f in files)

        # Remove anything matching keepglobs from the list
        matches = set()
        for g in keepglobs:
            globs_re = re.compile(fnmatch.translate(f"*{g}*"))
            m = [f for f in filelist if globs_re.match(f)]
            if m:
                matches.update(m)
            else:
                print(f"removekmod {g}: no files matched!")
        remove_files = filelist.difference(matches)

        if remove_files:
            list(os.unlink(f) for f in remove_files)
        else:
            print(f"removekmod {cmd}: no files to remove!")


def brace_expand(s):
    if not ('{' in s and ',' in s and '}' in s):
        return [s]

    result = []
    right = s.find('}')
    left = s[:right].rfind('{')
    prefix, choices, suffix = s[:left], s[left + 1:right], s[right + 1:]
    for choice in choices.split(','):
        result.extend(brace_expand(prefix + choice + suffix))

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
