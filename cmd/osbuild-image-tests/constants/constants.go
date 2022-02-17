package constants

import "os/exec"

func GetOsbuildCommand(store, outputDirectory string, exports []string) *exec.Cmd {
	cmd := exec.Command(
		"osbuild",
		"--store", store,
		"--output-directory", outputDirectory,
		"--checkpoint", "build",
		"--json",
		"-",
	)
	for _, export := range exports {
		cmd.Args = append(cmd.Args, "--export", export)
	}
	return cmd
}

func GetImageInfoCommand(imagePath string) *exec.Cmd {
	return exec.Command(
		"/usr/libexec/osbuild-test/image-info",
		imagePath,
	)
}

var TestPaths = struct {
	ImageInfo          string
	TestCasesDirectory string
}{
	ImageInfo:          "/usr/libexec/osbuild-test/image-info",
	TestCasesDirectory: "/usr/share/tests/osbuild/image-info",
}
