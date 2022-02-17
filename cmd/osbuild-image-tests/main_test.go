package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"io/ioutil"
	"os"
	"path"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/osbuild/osbuild/cmd/osbuild-image-tests/constants"
)

type testcaseStruct struct {
	ComposeRequest struct {
		Distro   string
		Arch     string
		Filename string
	} `json:"compose-request"`
	Manifest  json.RawMessage
	ImageInfo json.RawMessage `json:"image-info"`
	Boot      *struct {
		Type string
	}
}

type strArrayFlag []string

func (a *strArrayFlag) String() string {
	return fmt.Sprintf("%+v", []string(*a))
}

func (a *strArrayFlag) Set(value string) error {
	*a = append(*a, value)
	return nil
}

var disableLocalBoot bool
var failLocalBoot bool
var skipSELinuxCtxCheck bool
var skipTmpfilesdPaths strArrayFlag

func init() {
	flag.BoolVar(&disableLocalBoot, "disable-local-boot", false, "when this flag is given, no images are booted locally using qemu (this does not affect testing in clouds)")
	flag.BoolVar(&failLocalBoot, "fail-local-boot", true, "when this flag is on (default), local boot will fail. Usually indicates missing cloud credentials")
	flag.BoolVar(&skipSELinuxCtxCheck, "skip-selinux-ctx-check", false, "when this flag is on, the 'selinux/context-mismatch' part is removed from the image-info report before it is checked.")
	flag.Var(&skipTmpfilesdPaths, "skip-tmpfilesd-path", "when this flag is given, the provided path is removed from the 'tmpfiles.d' section of the image-info report before it is checked.")
}

// runOsbuild runs osbuild with the specified manifest and output-directory.
func runOsbuild(manifest []byte, store, outputDirectory string, exports []string) error {
	cmd := constants.GetOsbuildCommand(store, outputDirectory, exports)

	cmd.Stdin = bytes.NewReader(manifest)
	var outBuffer, errBuffer bytes.Buffer
	cmd.Stdout = &outBuffer
	cmd.Stderr = &errBuffer

	err := cmd.Run()
	if err != nil {
		fmt.Println("stdout:")
		// stdout is json, indent it, otherwise we get a huge one-liner
		var formattedStdout bytes.Buffer
		indentErr := json.Indent(&formattedStdout, outBuffer.Bytes(), "", "  ")
		if indentErr == nil {
			fmt.Println(formattedStdout.String())
		} else {
			// fallback to raw output if json indent failed
			fmt.Println(outBuffer.String())
		}

		// stderr isn't structured, print it as is
		fmt.Printf("stderr:\n%s", errBuffer.String())

		return fmt.Errorf("running osbuild failed: %v", err)
	}

	return nil
}

// Delete the 'selinux/context-mismatch' part of the image-info report to
// workaround https://bugzilla.redhat.com/show_bug.cgi?id=1973754
func deleteSELinuxCtxFromImageInfoReport(imageInfoReport interface{}) {
	imageInfoMap := imageInfoReport.(map[string]interface{})
	selinuxReport, exists := imageInfoMap["selinux"]
	if exists {
		selinuxReportMap := selinuxReport.(map[string]interface{})
		delete(selinuxReportMap, "context-mismatch")
	}
}

// Delete the provided path form the 'tmpfiles.d' section of the image-info
// report. This is useful to workaround issues with non-deterministic content
// of dynamically generated tmpfiles.d configuration files present on the image.
func deleteTmpfilesdPathFromImageInfoReport(imageInfoReport interface{}, path string) {
	dir := filepath.Dir(path)
	file := filepath.Base(path)
	imageInfoMap := imageInfoReport.(map[string]interface{})
	tmpfilesdReport, exists := imageInfoMap["tmpfiles.d"]
	if exists {
		tmpfilesdReportMap := tmpfilesdReport.(map[string]interface{})
		tmpfilesdConfigDir, exists := tmpfilesdReportMap[dir]
		if exists {
			tmpfilesdConfigDirMap := tmpfilesdConfigDir.(map[string]interface{})
			delete(tmpfilesdConfigDirMap, file)
		}
	}
}

// testImageInfo runs image-info on image specified by imageImage and
// compares the result with expected image info
func testImageInfo(t *testing.T, imagePath string, rawImageInfoExpected []byte) {
	var imageInfoExpected interface{}
	err := json.Unmarshal(rawImageInfoExpected, &imageInfoExpected)
	require.NoErrorf(t, err, "cannot decode expected image info: %v", err)

	cmd := constants.GetImageInfoCommand(imagePath)
	cmd.Stderr = os.Stderr
	reader, writer := io.Pipe()
	cmd.Stdout = writer

	err = cmd.Start()
	require.NoErrorf(t, err, "image-info cannot start: %v", err)

	var imageInfoGot interface{}
	err = json.NewDecoder(reader).Decode(&imageInfoGot)
	require.NoErrorf(t, err, "decoding image-info output failed: %v", err)

	err = cmd.Wait()
	require.NoErrorf(t, err, "running image-info failed: %v", err)

	if skipSELinuxCtxCheck {
		fmt.Println("ignoring 'selinux/context-mismatch' part of the image-info report")
		deleteSELinuxCtxFromImageInfoReport(imageInfoExpected)
		deleteSELinuxCtxFromImageInfoReport(imageInfoGot)
	}

	for _, path := range skipTmpfilesdPaths {
		fmt.Printf("ignoring %q path from the 'tmpfiles.d' part of the image-info report\n", path)
		deleteTmpfilesdPathFromImageInfoReport(imageInfoExpected, path)
		deleteTmpfilesdPathFromImageInfoReport(imageInfoGot, path)
	}

	assert.Equal(t, imageInfoExpected, imageInfoGot)
}

// testImage performs a series of tests specified in the testcase
// on an image
func testImage(t *testing.T, testcase testcaseStruct, imagePath string) {
	if testcase.ImageInfo != nil {
		t.Run("image info", func(t *testing.T) {
			testImageInfo(t, imagePath, testcase.ImageInfo)
		})
	}
}

// guessPipelineToExport return a best-effort guess about which
// pipeline should be exported when running osbuild for the testcase
//
// If this function detects that this is a version 1 manifest, it
// always returns "assembler"
//
// For manifests version 2, the name of the last pipeline is returned.
func guessPipelineToExport(rawManifest json.RawMessage) string {
	const v1ManifestExportName = "assembler"
	var v2Manifest struct {
		Version   string `json:"version"`
		Pipelines []struct {
			Name string `json:"name,omitempty"`
		} `json:"pipelines"`
	}
	err := json.Unmarshal(rawManifest, &v2Manifest)
	if err != nil {
		// if we cannot unmarshal, let's just assume that it's a version 1 manifest
		return v1ManifestExportName
	}

	if v2Manifest.Version == "2" {
		return v2Manifest.Pipelines[len(v2Manifest.Pipelines)-1].Name
	}

	return v1ManifestExportName
}

// runTestcase builds the pipeline specified in the testcase and then it
// tests the result
func runTestcase(t *testing.T, testcase testcaseStruct, store string) {
	_ = os.Mkdir("/var/lib/osbuild-tests", 0755)
	outputDirectory, err := ioutil.TempDir("/var/lib/osbuild-tests", "osbuild-image-tests-*")
	require.NoError(t, err, "error creating temporary output directory")

	defer func() {
		err := os.RemoveAll(outputDirectory)
		require.NoError(t, err, "error removing temporary output directory")
	}()

	exports := []string{guessPipelineToExport(testcase.Manifest)}
	err = runOsbuild(testcase.Manifest, store, outputDirectory, exports)
	require.NoError(t, err)

	for _, export := range exports {
		imagePath := filepath.Join(outputDirectory, export, testcase.ComposeRequest.Filename)
		testImage(t, testcase, imagePath)
	}
}

// getAllCases returns paths to all testcases in the testcase directory
func getAllCases() ([]string, error) {
	cases, err := ioutil.ReadDir(constants.TestPaths.TestCasesDirectory)
	if err != nil {
		return nil, fmt.Errorf("cannot list test cases: %v", err)
	}

	casesPaths := []string{}
	for _, c := range cases {
		if c.IsDir() {
			continue
		}

		casePath := fmt.Sprintf("%s/%s", constants.TestPaths.TestCasesDirectory, c.Name())
		casesPaths = append(casesPaths, casePath)
	}

	return casesPaths, nil
}

func currentArch() string {
	if runtime.GOARCH == "amd64" {
		return "x86_64"
	} else if runtime.GOARCH == "arm64" {
		return "aarch64"
	} else if runtime.GOARCH == "ppc64le" {
		return "ppc64le"
	} else if runtime.GOARCH == "s390x" {
		return "s390x"
	} else {
		panic("unsupported architecture")
	}
}

// runTests opens, parses and runs all the specified testcases
func runTests(t *testing.T, cases []string) {
	_ = os.Mkdir("/var/lib/osbuild-tests", 0755)
	store, err := ioutil.TempDir("/var/lib/osbuild-tests", "osbuild-image-tests-*")
	require.NoError(t, err, "error creating temporary store")

	defer func() {
		err := os.RemoveAll(store)
		require.NoError(t, err, "error removing temporary store")
	}()

	for _, p := range cases {
		t.Run(path.Base(p), func(t *testing.T) {
			f, err := os.Open(p)
			if err != nil {
				t.Skipf("%s: cannot open test case: %v", p, err)
			}

			var testcase testcaseStruct
			err = json.NewDecoder(f).Decode(&testcase)
			require.NoErrorf(t, err, "%s: cannot decode test case", p)

			currentArch := currentArch()
			if testcase.ComposeRequest.Arch != currentArch {
				t.Skipf("the required arch is %s, the current arch is %s", testcase.ComposeRequest.Arch, currentArch)
			}

			runTestcase(t, testcase, store)
		})

	}
}

func TestImages(t *testing.T) {
	cases := flag.Args()
	// if no cases were specified, run the default set
	if len(cases) == 0 {
		var err error
		cases, err = getAllCases()
		require.NoError(t, err)
	}

	runTests(t, cases)
}
