# SELiunx and osbuild

SELinux labels for files are store as extended attributes under the
`security.selinux` prefix.

## File system tree labelling
All stages, including the `org.osbuild.rpm` stage are run inside a
container which will indicate to all tools, including rpm scriptles
that SELinux is disabled.

Labels are manually applied to the file system tree via a specialised
`org.osbuild.selinux` stage. This stage should therefore be at the
very end of the pipeline that is building the tree so that all files
are properly labelled.

## Container peculiarities and policy differences

SELinux is not namespaced which means there is only one global
policy inside the Linux kernel. Since the kernel is shared by all
containers, the policy that is loaded in the kernel applies to all
containers as well.

Labels are verified against the active policy in the kernel when
writing (`setxattr`) but also when reading them (`getxattr`) as
long as selinux is activated for the kernel (i.e. on the host).

To read or write labels that are not included in the currently
active policy, the `CAP_MAC_ADMIN` capability(7) is needed. If
a process does not have this policy the following will happen
when trying to write or read the label:

When trying to write a label that is unknown to the currently
active policy, the kernel will reject it and the call to
`setxattr` will fail with `EINVAL` resulting in "Invalid argument"
errors from the corresponding tooling.

When trying to read a label that is unknown to the currently
active policy, the kernel will "pretend" the file is not labelled and
return `system_u:object_r:unlabeled_t:s0` as label. Thus a file with
an unknown label (unknown to the host kernel) is indistinguishable
from an unlabelled file.

In RHEL and Fedora's SELinux policy, only very few programs can
gain or retain the`CAP_MAC_ADMIN` capability, even if the current
user is `unconfined` or `sysadm`. Normal tools like `cp`, `ls`,
`stat`, or `tar` do *not* have this capability meaning that
inspecting the labels for files and folders will result in
`unlabeled_t` for unknown (to the host) labels.

### Custom OSBuild SElinux Policy

On RHEL and Fedora, the SELinux policy has a few contexts that
allow `CAP_MAC_ADMIN`, most notably `install_t` and `setfiles_mac`.
The latter is a policy for the `setfiles` binary, which is used
by the`org.osbuild.selinux` stage to label files. But to be able
to transition into `setfiles_mac`, the calling program must have a
special transition rule allowing this. Therefore osbuild uses a
custom policy with specialised labels for osbuild executables such
as stages, runners and the main binary: `osbuild_t`. Then a domain
transition rule is enabled that allows `setfiles` to transition to
`setfiles_mac` from `osbuild`. From `selinux/osbuild.te`:

    # execute setfiles in the setfiles_mac domain
    # when in the osbuild_t domain
    seutil_domtrans_setfiles_mac(osbuild_t)

## Running osbuild in a container

When osbuild is run in a container, it cannot use the default SELinux
container policy. Historically this has been done i using a standard
unconfined policy (`--security-opt label=type:unconfined_t`). However,
the normal `unconfined_t` doamin does not have `CAP_MAC_ADMIN`
capability, nor does it have the ability to use the normal osbuild
policy inside the container. To allow this, there is a another custom
OSBuild SELinux policy called `osbuild-container` which has an unconfined
domain called `osbuild_container_t` domain that has this capability.

This policy can be installed separately (from the
`osbuild-container-selinux` package) and used with the podman option
`--security-opt label=type:osbuild_container_t`.
