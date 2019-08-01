
import contextlib
import errno
import hashlib
import json
import os
import socket
import shutil
import subprocess
import sys
import tempfile
import osbuild.remoteloop as remoteloop


__all__ = [
    "Assembler",
    "AssemblerFailed",
    "BuildRoot",
    "load",
    "Pipeline",
    "Stage",
    "StageFailed",
]


RESET = "\033[0m"
BOLD = "\033[1m"


class StageFailed(Exception):
    def __init__(self, name, returncode, output):
        super(StageFailed, self).__init__()
        self.name = name
        self.returncode = returncode
        self.output = output


class AssemblerFailed(Exception):
    def __init__(self, name, returncode, output):
        super(AssemblerFailed, self).__init__()
        self.name = name
        self.returncode = returncode
        self.output = output


class TmpFs:
    def __init__(self, path="/run/osbuild"):
        self.path = path
        self.root = None
        self.mounted = False

    def __enter__(self):
        self.root = tempfile.mkdtemp(prefix="osbuild-tmpfs-", dir=self.path)
        try:
            subprocess.run(["mount", "-t", "tmpfs", "-o", "mode=0755", "tmpfs", self.root], check=True)
            self.mounted = True
        except subprocess.CalledProcessError:
            os.rmdir(self.root)
            self.root = None
            raise
        return self.root

    def __exit__(self, exc_type, exc_value, exc_tb):
        if not self.root:
            return
        if self.mounted:
            subprocess.run(["umount", "--lazy", self.root], check=True)
            self.mounted = False
        os.rmdir(self.root)
        self.root = None


def treesum(m, dir_fd):
    """Compute a content hash of a filesystem tree

    Parameters
    ----------
    m : hash object
        the hash object to append the treesum to
    dir_fd : int
        directory file descriptor number to operate on

    The hash is stable between runs, and guarantees that two filesystem
    trees with the same hash, are functionally equivalent from the OS
    point of view.

    The file, symlink and directory names and contents are recursively
    hashed, together with security-relevant metadata."""

    with os.scandir(dir_fd) as it:
        for dirent in sorted(it, key=(lambda d: d.name)):
            stat_result = dirent.stat(follow_symlinks=False)
            metadata = {}
            metadata["name"] = os.fsdecode(dirent.name)
            metadata["mode"] = stat_result.st_mode
            metadata["uid"] = stat_result.st_uid
            metadata["gid"] = stat_result.st_gid
            # include the size of symlink target/file-contents so we don't have to delimit it
            metadata["size"] = stat_result.st_size
            # getxattr cannot operate on a dir_fd, so do a trick and rely on the entries in /proc
            stable_file_path = os.path.join(f"/proc/self/fd/{dir_fd}", dirent.name)
            try:
                selinux_label = os.getxattr(stable_file_path, b"security.selinux", follow_symlinks=False)
            except OSError as e:
                # SELinux support is optional
                if e.errno != errno.ENODATA:
                    raise
            else:
                metadata["selinux"] = os.fsdecode(selinux_label)
            # hash the JSON representation of the metadata to stay unique/stable/well-defined
            m.update(json.dumps(metadata, sort_keys=True).encode())
            if dirent.is_symlink():
                m.update(os.fsdecode(os.readlink(dirent.name, dir_fd=dir_fd)).encode())
            else:
                fd = os.open(dirent.name, flags=os.O_RDONLY, dir_fd=dir_fd)
                try:
                    if dirent.is_dir(follow_symlinks=False):
                        treesum(m, fd)
                    elif dirent.is_file(follow_symlinks=False):
                        # hash a page at a time (using f with fd as default is a hack to please pylint)
                        for byte_block in iter(lambda f=fd: os.read(f, 4096), b""):
                            m.update(byte_block)
                    else:
                        raise ValueError("Found unexpected filetype on OS image")
                finally:
                    os.close(fd)


class ObjectStore:
    def __init__(self, store):
        self.store = store
        self.objects = f"{store}/objects"
        self.refs = f"{store}/refs"
        os.makedirs(self.store, exist_ok=True)
        os.makedirs(self.objects, exist_ok=True)
        os.makedirs(self.refs, exist_ok=True)

    def has_tree(self, tree_id):
        if not tree_id:
            return False
        return os.access(f"{self.refs}/{tree_id}", os.F_OK)

    @contextlib.contextmanager
    def get_tree(self, tree_id):
        with tempfile.TemporaryDirectory(dir=self.store) as tmp:
            if tree_id:
                subprocess.run(["mount", "-o", "bind,ro,mode=0755", f"{self.refs}/{tree_id}", tmp], check=True)
                try:
                    yield tmp
                finally:
                    subprocess.run(["umount", "--lazy", tmp], check=True)
            else:
                # None was given as tree_id, just return an empty directory
                yield tmp

    @contextlib.contextmanager
    def new_tree(self, tree_id, base_id=None):
        with tempfile.TemporaryDirectory(dir=self.store) as tmp:
            # the tree that is yielded will be added to the content store
            # on success as tree_id

            tree = f"{tmp}/tree"
            link = f"{tmp}/link"
            os.mkdir(tree, mode=0o755)

            if base_id:
                # the base, the working tree and the output tree are all on
                # the same fs, so attempt a lightweight copy if the fs
                # supports it
                subprocess.run(["cp", "--reflink=auto", "-a", f"{self.refs}/{base_id}/.", tree], check=True)

            yield tree

            # if the yield raises an exception, the working tree is cleaned
            # up by tempfile, otherwise, we save it in the correct place:
            fd = os.open(tree, os.O_DIRECTORY)
            try:
                m = hashlib.sha256()
                treesum(m, fd)
                treesum_hash = m.hexdigest()
            finally:
                os.close(fd)
            # the tree is stored in the objects directory using its content
            # hash as its name, ideally a given tree_id (i.e., given config)
            # will always produce the same content hash, but that is not
            # guaranteed
            output_tree = f"{self.objects}/{treesum_hash}"
            try:
                os.rename(tree, output_tree)
            except OSError as e:
                if e.errno == errno.ENOTEMPTY:
                    pass # tree with the same content hash already exist, use that
                else:
                    raise
            # symlink the tree_id (config hash) in the refs directory to the treesum
            # (content hash) in the objects directory. If a symlink by that name
            # alreday exists, atomically replace it, but leave the backing object
            # in place (it may be in use).
            os.symlink(f"../objects/{treesum_hash}", link)
            os.replace(link, f"{self.refs}/{tree_id}")


class BuildRoot:
    def __init__(self, root, path="/run/osbuild"):
        self.root = tempfile.mkdtemp(prefix="osbuild-buildroot-", dir=path)
        self.api = tempfile.mkdtemp(prefix="osbuild-api-", dir=path)
        self.mounts = []
        for p in ["usr", "bin", "sbin", "lib", "lib64"]:
            source = os.path.join(root, p)
            target = os.path.join(self.root, p)
            if not os.path.isdir(source) or os.path.islink(source):
                continue # only bind-mount real dirs
            os.mkdir(target)
            try:
                subprocess.run(["mount", "-o", "bind,ro", source, target], check=True)
            except subprocess.CalledProcessError:
                self.unmount()
                raise
            self.mounts.append(target)

    def unmount(self):
        for path in self.mounts:
            subprocess.run(["umount", "--lazy", path], check=True)
            os.rmdir(path)
        self.mounts = []
        if self.root:
            shutil.rmtree(self.root)
            self.root = None
        if self.api:
            shutil.rmtree(self.api)
            self.api = None

    def run(self, argv, binds=None, readonly_binds=None, **kwargs):
        """Runs a command in the buildroot.

        Its arguments mean the same as those for subprocess.run().
        """

        return subprocess.run([
            "systemd-nspawn",
            "--quiet",
            "--register=no",
            "--as-pid2",
            "--link-journal=no",
            "--property=DeviceAllow=block-loop rw",
            f"--directory={self.root}",
            *[f"--bind={b}" for b in (binds or [])],
            *[f"--bind-ro={b}" for b in [f"{self.api}:/run/osbuild/api"] + (readonly_binds or [])],
            ] + argv, **kwargs)

    @contextlib.contextmanager
    def bound_socket(self, name):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock_path = os.path.join(self.api, name)
        sock.bind(os.path.join(self.api, name))
        try:
            yield sock
        finally:
            os.unlink(sock_path)
            sock.close()

    def __del__(self):
        self.unmount()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.unmount()


def print_header(title, options):
    print()
    print(f"{RESET}{BOLD}{title}{RESET} " + json.dumps(options or {}, indent=2))
    print()


class Stage:
    def __init__(self, name, base, build, options):
        m = hashlib.sha256()
        m.update(json.dumps(name, sort_keys=True).encode())
        m.update(json.dumps(build, sort_keys=True).encode())
        m.update(json.dumps(base, sort_keys=True).encode())
        m.update(json.dumps(options, sort_keys=True).encode())

        self.id = m.hexdigest()
        self.name = name
        self.options = options

    def description(self):
        description = {}
        description["name"] = self.name
        if self.options:
            description["options"] = self.options
        return description

    def run(self, tree, build_tree, interactive=False, check=True, libdir=None):
        with BuildRoot(build_tree) as buildroot:
            if interactive:
                print_header(f"{self.name}: {self.id}", self.options)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            path = "/run/osbuild/lib" if libdir else "/usr/libexec/osbuild"
            r = buildroot.run(
                [f"{path}/osbuild-run", f"{path}/stages/{self.name}"],
                binds=[f"{tree}:/run/osbuild/tree"],
                readonly_binds=[f"{libdir}:{path}"] if libdir else [],
                encoding="utf-8",
                input=json.dumps(args),
                stdout=None if interactive else subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            if check and r.returncode != 0:
                raise StageFailed(self.name, r.returncode, r.stdout)

            return {
                "name": self.name,
                "returncode": r.returncode,
                "output": r.stdout
            }


class Assembler:
    def __init__(self, name, options):
        self.name = name
        self.options = options

    def description(self):
        description = {}
        description["name"] = self.name
        if self.options:
            description["options"] = self.options
        return description

    def run(self, tree, build_tree, output_dir=None, interactive=False, check=True, libdir=None):
        with BuildRoot(build_tree) as buildroot:
            if interactive:
                print_header(f"Assembling: {self.name}", self.options)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            binds = []
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                binds.append(f"{output_dir}:/run/osbuild/output")
                args["output_dir"] = "/run/osbuild/output"

            path = "/run/osbuild/lib" if libdir else "/usr/libexec/osbuild"
            with buildroot.bound_socket("remoteloop") as sock, \
                remoteloop.LoopServer(sock):
                r = buildroot.run(
                    [f"{path}/osbuild-run", f"{path}/assemblers/{self.name}"],
                    binds=binds,
                    readonly_binds=[f"{tree}:/run/osbuild/tree"] + ([f"{libdir}:{path}"] if libdir else []),
                    encoding="utf-8",
                    input=json.dumps(args),
                    stdout=None if interactive else subprocess.PIPE,
                    stderr=subprocess.STDOUT)
                if check and r.returncode != 0:
                    raise AssemblerFailed(self.name, r.returncode, r.stdout)

            return {
                "name": self.name,
                "returncode": r.returncode,
                "output": r.stdout
            }


class Pipeline:
    def __init__(self, build=None):
        self.build = build
        self.stages = []
        self.assembler = None

    def get_id(self):
        return self.stages[-1].id if self.stages else None

    def add_stage(self, name, options=None):
        build = self.build.get_id() if self.build else None
        stage = Stage(name, build, self.get_id(), options or {})
        self.stages.append(stage)

    def set_assembler(self, name, options=None):
        self.assembler = Assembler(name, options or {})

    def description(self):
        description = {}
        if self.build:
            description["build"] = self.build.description()
        if self.stages:
            description["stages"] = [s.description() for s in self.stages]
        if self.assembler:
            description["assembler"] = self.assembler.description()
        return description

    @contextlib.contextmanager
    def get_buildtree(self, object_store):
        if self.build:
            with object_store.get_tree(self.build.get_id()) as tree:
                yield tree
        else:
            with tempfile.TemporaryDirectory(dir=object_store.store) as tmp:
                subprocess.run(["mount", "-o", "bind,ro,mode=0755", "/", tmp], check=True)
                try:
                    yield tmp
                finally:
                    subprocess.run(["umount", "--lazy", tmp], check=True)

    def run(self, output_dir, store, interactive=False, check=True, libdir=None):
        os.makedirs("/run/osbuild", exist_ok=True)
        object_store = ObjectStore(store)
        results = {
            "stages": []
        }
        if self.build:
            r = self.build.run(None, store, interactive, check, libdir)
            results["build"] = r
            if r["returncode"] != 0:
                results["returncode"] = r["returncode"]
                return results

        with self.get_buildtree(object_store) as build_tree:
            if self.stages:
                if not object_store.has_tree(self.get_id()):
                    # Find the last stage that already exists in the object store, and use
                    # that as the base.
                    base = None
                    base_idx = -1
                    for i in range(len(self.stages) - 1, 0, -1):
                        if object_store.has_tree(self.stages[i].id):
                            base = self.stages[i].id
                            base_idx = i
                            break
                    # The tree does not exist. Create it and save it to the object store. If
                    # two run() calls race each-other, two trees may be generated, and it
                    # is nondeterministic which of them will end up referenced by the tree_id
                    # in the content store. However, we guarantee that all tree_id's and all
                    # generated trees remain valid.
                    with object_store.new_tree(self.get_id(), base_id=base) as tree:
                        for stage in self.stages[base_idx + 1:]:
                            r = stage.run(tree,
                                          build_tree,
                                          interactive=interactive,
                                          check=check,
                                          libdir=libdir)
                            results["stages"].append(r)
                            if r["returncode"] != 0:
                                results["returncode"] = r["returncode"]
                                return results

            if self.assembler:
                with object_store.get_tree(self.get_id()) as tree:
                    r = self.assembler.run(tree,
                                           build_tree,
                                           output_dir=output_dir,
                                           interactive=interactive,
                                           check=check,
                                           libdir=libdir)
                    results["assembler"] = r
                    if r["returncode"] != 0:
                        results["returncode"] = r["returncode"]
                        return results

        results["returncode"] = 0
        return results


def load(description):
    build_description = description.get("build")
    if build_description:
        build = load(build_description)
    else:
        build = None
    pipeline = Pipeline(build)

    for s in description.get("stages", []):
        pipeline.add_stage(s["name"], s.get("options", {}))

    a = description.get("assembler")
    if a:
        pipeline.set_assembler(a["name"], a.get("options", {}))

    return pipeline
