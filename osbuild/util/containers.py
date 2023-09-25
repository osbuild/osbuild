import json
import os
import subprocess

def is_manifest_list(data):
    """Inspect a manifest determine if it's a multi-image manifest-list."""
    media_type = data.get("mediaType")
    #  Check if mediaType is set according to docker or oci specifications
    if media_type in ("application/vnd.docker.distribution.manifest.list.v2+json",
                      "application/vnd.oci.image.index.v1+json"):
        return True

    # According to the OCI spec, setting mediaType is not mandatory. So, if it is not set at all, check for the
    # existence of manifests
    if media_type is None and data.get("manifests") is not None:
        return True

    return False


def parse_manifest_list(manifests):
    """Return a map with single-image manifest digests as keys and the manifest-list digest as the value for each"""
    manifest_files = manifests["data"]["files"]
    manifest_map = {}
    for fname in manifest_files:
        filepath = os.path.join(manifests["path"], fname)
        with open(filepath, mode="r", encoding="utf-8") as mfile:
            data = json.load(mfile)

        for manifest in data["manifests"]:
            digest = manifest["digest"]  # single image manifest digest
            manifest_map[digest] = fname

    return manifest_map


def manifest_digest(path):
    """Get the manifest digest for a container at path, stored in dir: format"""
    return subprocess.check_output(["skopeo", "manifest-digest", os.path.join(path, "manifest.json")]).decode().strip()


def parse_containers_input(inputs):
    manifests = inputs.get("manifest-lists")
    manifest_map = {}
    manifest_files = {}
    if manifests:
        manifest_files = manifests["data"]["files"]
        # reverse map manifest-digest -> manifest-list path
        manifest_map = parse_manifest_list(manifests)

    images = inputs["images"]
    archives = images["data"]["archives"]

    res = {}
    for checksum, data in archives.items():
        filepath = os.path.join(images["path"], checksum)
        list_path = None
        if data["format"] == "dir":
            digest = manifest_digest(filepath)

            # get the manifest list path for this image
            list_digest = manifest_map.get(digest)
            if list_digest:
                # make sure all manifest files are used
                del manifest_files[list_digest]
                list_path = os.path.join(manifests["path"], list_digest)

        res[checksum] = {
            "filepath": filepath,
            "manifest-list": list_path,
            "data": data,
        }

    if manifest_files:
        raise RuntimeError(
            "The following manifest lists specified in the input did not match any of the container images: " +
            ", ".join(manifest_files)
        )

    return res


def merge_manifest(list_manifest, destination):
    """
    Merge the list manifest into the image directory. This preserves the manifest list with the image in the registry so
    that users can run or inspect a container using the original manifest list digest used to pull the container.

    See https://github.com/containers/skopeo/issues/1935
    """
    # calculate the checksum of the manifest of the container image in the destination
    dest_manifest = os.path.join(destination, "manifest.json")
    manifest_checksum = subprocess.check_output(["skopeo", "manifest-digest", dest_manifest]).decode().strip()
    parts = manifest_checksum.split(":")
    assert len(parts) == 2, f"unexpected output for skopeo manifest-digest: {manifest_checksum}"
    manifest_checksum = parts[1]

    # rename the manifest to its checksum
    os.rename(dest_manifest, os.path.join(destination, manifest_checksum + ".manifest.json"))

    # copy the index manifest into the destination
    subprocess.run(["cp", "--reflink=auto", "-a", list_manifest, dest_manifest], check=True)
