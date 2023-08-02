#!/usr/bin/python3
#
# Small script that returns 0 if all the requested mount flags
# are present for a given mount and returns 1 otherwise

import argparse
import os
import sys

# from /usr/include/sys/mount.h
# these are file-system independent
MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8

KNOWN_FLAGS = {"ro": MS_RDONLY, "nosuid": MS_NOSUID, "nodev": MS_NODEV, "noexec": MS_NOEXEC}


def main():
    parser = argparse.ArgumentParser(description="Check for mount flags")
    parser.add_argument("path", metavar="PATH", help="path for the file-system to check for read-only status")
    parser.add_argument("flags", metavar="FLAGS", help="comma separated list of flags to check for")
    args = parser.parse_args(sys.argv[1:])

    want = 0
    strflags = [x.strip() for x in args.flags.split(",")]
    for flag in strflags:
        num = KNOWN_FLAGS.get(flag, None)
        if flag is None:
            print(f"Unknown flag: '{flag}'")
            sys.exit(2)
        want |= num

    sb = os.statvfs(args.path)
    have = sb.f_flag
    ok = (have & want) == want
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
