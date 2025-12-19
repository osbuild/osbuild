package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"unsafe"

	"golang.org/x/sys/unix"
)

var debug bool

func setDebug(enabled bool) {
	debug = enabled
}

func debugln(format string, args ...interface{}) {
	if debug {
		fmt.Printf(format+"\n", args...)
	}
}

func mkdirP(path string) error {
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return os.MkdirAll(path, 0755)
	}
	return nil
}

func createStaticDevices() error {
	debugln("Creating static device nodes")

	devices := []struct {
		path  string
		major uint32
		minor uint32
		mode  uint32
	}{
		{"/dev/kvm", 10, 232, 0660},
		{"/dev/loop-control", 10, 237, 0660},
		{"/dev/fuse", 10, 229, 0666},
	}

	for _, dev := range devices {
		debugln("Creating %s", dev.path)
		parent := filepath.Dir(dev.path)
		if parent != "/dev" {
			if err := mkdirP(parent); err != nil {
				return err
			}
		}

		devNum := unix.Mkdev(dev.major, dev.minor)
		if err := unix.Mknod(dev.path, unix.S_IFCHR|dev.mode, int(devNum)); err != nil && !os.IsExist(err) {
			return err
		}
	}

	symlinks := []struct {
		linkPath string
		target   string
	}{
		{"/dev/fd", "/proc/self/fd"},
		{"/dev/stdin", "/proc/self/fd/0"},
		{"/dev/stdout", "/proc/self/fd/1"},
		{"/dev/stderr", "/proc/self/fd/2"},
	}

	for _, link := range symlinks {
		debugln("Creating %s", link.linkPath)
		if err := os.Symlink(link.target, link.linkPath); err != nil && !os.IsExist(err) {
			return err
		}
	}

	return nil
}

func readCmdline() (string, error) {
	debugln("Reading /proc/cmdline")
	data, err := os.ReadFile("/proc/cmdline")
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(data)), nil
}

func cmdlineGet(cmdline, key string) (string, bool) {
	for _, param := range strings.Fields(cmdline) {
		if param == key {
			return "", true
		}
		if strings.HasPrefix(param, key+"=") {
			value := strings.TrimPrefix(param, key+"=")
			return value, true
		}
	}
	return "", false
}

func cmdlineGetMounts(cmdline string) []struct {
	tag      string
	readOnly bool
} {
	var mounts []struct {
		tag      string
		readOnly bool
	}

	for _, param := range strings.Fields(cmdline) {
		if strings.HasPrefix(param, "mount=") {
			tag := strings.TrimPrefix(param, "mount=")
			if tag != "" {
				mounts = append(mounts, struct {
					tag      string
					readOnly bool
				}{tag, false})
			}
		} else if strings.HasPrefix(param, "mount-ro=") {
			tag := strings.TrimPrefix(param, "mount-ro=")
			if tag != "" {
				mounts = append(mounts, struct {
					tag      string
					readOnly bool
				}{tag, true})
			}
		}
	}

	return mounts
}

func mountAPIs() error {
	mounts := []struct {
		source string
		target string
		fstype string
		flags  uintptr
		data   string
	}{
		{"sysfs", "/sys", "sysfs", unix.MS_NOSUID | unix.MS_NOEXEC | unix.MS_NODEV, ""},
		{"devtmpfs", "/dev", "devtmpfs", unix.MS_NOSUID, "seclabel,mode=0755,size=4m"},
		{"proc", "/proc", "proc", unix.MS_NOSUID | unix.MS_NOEXEC | unix.MS_NODEV, ""},
		{"tmpfs", "/run", "tmpfs", unix.MS_NOSUID | unix.MS_NODEV, "seclabel,mode=0755,size=64m"},
		{"tmpfs", "/tmp", "tmpfs", unix.MS_NOSUID | unix.MS_NODEV, "seclabel,mode=0755,size=128m"},
	}

	for _, m := range mounts {
		debugln("Mounting %s", m.target)
		if err := unix.Mount(m.source, m.target, m.fstype, m.flags, m.data); err != nil {
			return err
		}
	}

	return nil
}

func moveMount(src, dest string) error {
	debugln("Moving %s to %s", src, dest)
	return unix.Mount(src, dest, "", unix.MS_MOVE, "")
}

func mountVirtiofs(tag, mountpoint string, readOnly bool) error {
	debugln("Mounting %s at %s (read_only: %v)", tag, mountpoint, readOnly)
	var flags uintptr
	if readOnly {
		flags = unix.MS_RDONLY
	}
	return unix.Mount(tag, mountpoint, "virtiofs", flags, "")
}

func switchRoot(newroot string) error {
	debugln("Switching root to %s", newroot)

	if err := syscall.Chdir(newroot); err != nil {
		return err
	}

	oldRoot, err := os.Open("/")
	if err != nil {
		return err
	}
	defer oldRoot.Close()

	if err := moveMount(".", "/"); err != nil {
		return err
	}

	if err := syscall.Chroot("."); err != nil {
		return err
	}

	if err := syscall.Chdir("/"); err != nil {
		return err
	}

	return nil
}

func loadKernelModule(modulePath string) error {
	debugln("Loading module: %s", modulePath)
	moduleData, err := os.ReadFile(modulePath)
	if err != nil {
		return err
	}

	_, _, errno := unix.Syscall(unix.SYS_INIT_MODULE, uintptr(unsafe.Pointer(&moduleData[0])), uintptr(len(moduleData)), uintptr(unsafe.Pointer(&[]byte{0}[0])))
	if errno != 0 {
		return errno
	}

	return nil
}

func loadKernelModules(modulesDir string) error {
	if _, err := os.Stat(modulesDir); os.IsNotExist(err) {
		return nil
	}

	entries, err := os.ReadDir(modulesDir)
	if err != nil {
		return err
	}

	var modulePaths []string
	for _, entry := range entries {
		if !entry.IsDir() {
			path := filepath.Join(modulesDir, entry.Name())
			if strings.HasSuffix(entry.Name(), ".ko") {
				modulePaths = append(modulePaths, path)
			}
		}
	}

	sort.Strings(modulePaths)

	for _, path := range modulePaths {
		if err := loadKernelModule(path); err != nil {
			fmt.Fprintf(os.Stderr, "Failed to load module %s: %v\n", path, err)
		}
	}

	return nil
}

func doInit() error {
	dirs := []string{"/sysroot", "/sys", "/dev", "/proc", "/run", "/tmp"}
	for _, dir := range dirs {
		if err := mkdirP(dir); err != nil {
			return err
		}
	}

	if err := mountAPIs(); err != nil {
		return err
	}

	if err := mkdirP("/run/mnt"); err != nil {
		return err
	}

	cmdline, err := readCmdline()
	if err != nil {
		return err
	}

	if _, ok := cmdlineGet(cmdline, "debug"); ok {
		setDebug(true)
	}

	if err := createStaticDevices(); err != nil {
		return err
	}

	if err := loadKernelModules("/usr/lib/modules"); err != nil {
		return err
	}

	rootfsTag := "rootfs"
	if tag, ok := cmdlineGet(cmdline, "rootfs"); ok && tag != "" {
		rootfsTag = tag
	}
	if err := mountVirtiofs(rootfsTag, "/sysroot", true); err != nil {
		return err
	}

	additionalMounts := cmdlineGetMounts(cmdline)
	for _, mount := range additionalMounts {
		mountPath := filepath.Join("/run/mnt", mount.tag)
		if err := mkdirP(mountPath); err != nil {
			return err
		}
		if err := mountVirtiofs(mount.tag, mountPath, mount.readOnly); err != nil {
			return err
		}
	}

	survivingMounts := []string{"/run", "/dev", "/proc", "/sys", "/tmp"}
	for _, mountPoint := range survivingMounts {
		dest := filepath.Join("/sysroot", mountPoint)
		if _, err := os.Stat(dest); err == nil {
			if err := moveMount(mountPoint, dest); err != nil {
				return err
			}
		} else {
			if err := unix.Unmount(mountPoint, 0); err != nil {
				return err
			}
		}
	}

	if err := switchRoot("/sysroot"); err != nil {
		return err
	}

	initProgram := "/bin/sh"
	if prog, ok := cmdlineGet(cmdline, "init"); ok && prog != "" {
		initProgram = prog
	}
	debugln("Executing init: %s", initProgram)

	initName := filepath.Base(initProgram)

	if err := syscall.Exec(initProgram, []string{initName}, os.Environ()); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to execute %s: %v\n", initProgram, err)
		return err
	}

	return nil
}

func main() {
	if err := doInit(); err != nil {
		fmt.Fprintf(os.Stderr, "Unexpected error: %v\n", err)
	}
}
