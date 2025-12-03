#!/usr/bin/python3
import glob
import os
import re


def replace(target, patterns):
    """replace patterns in a file using regex"""
    finder = [(re.compile(p), s) for p, s in patterns]
    newfile = target + ".replace"

    with open(target, "r", encoding="utf8") as i, open(newfile, "w", encoding="utf8") as o:
        for line in i:
            for p, s in finder:
                line = p.sub(s, line)
            o.write(line)
    os.rename(newfile, target)


def rglob(pathname, *, fatal=False):
    """rglob yields a uniqe list of files from the pathname glob"""
    seen = set()
    for f in glob.iglob(pathname):
        if f not in seen:
            seen.add(f)
            yield f
    if fatal and not seen:
        raise IOError(f"nothing matching {pathname}")
