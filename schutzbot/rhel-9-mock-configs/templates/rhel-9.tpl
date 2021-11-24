# inspired by https://gitlab.com/redhat/centos-stream/ci-cd/zuul/jobs/-/blob/master/playbooks/files/centos-stream9-x86_64.cfg

config_opts['root'] = 'rhel-9-{{ target_arch }}'


config_opts['chroot_setup_cmd'] = 'install tar gcc-c++ redhat-rpm-config redhat-release which xz sed make bzip2 gzip gcc coreutils unzip shadow-utils diffutils cpio bash gawk rpm-build info patch util-linux findutils grep'
config_opts['dist'] = 'el8'  # only useful for --resultdir variable subst
config_opts['releasever'] = '8'
config_opts['package_manager'] = 'dnf'
config_opts['extra_chroot_dirs'] = [ '/run/lock', ]
config_opts['bootstrap_image'] = 'registry-proxy.engineering.redhat.com/rh-osbs/ubi9'

config_opts['dnf.conf'] = """
[main]
keepcache=1
debuglevel=2
reposdir=/dev/null
logfile=/var/log/yum.log
retries=20
obsoletes=1
gpgcheck=0
assumeyes=1
syslog_ident=mock
syslog_device=
mdpolicy=group:primary
best=1
protected_packages=
module_platform_id=platform:el9
user_agent={{ user_agent }}

[rhel9-baseos]
name=RHEL 9 BaseOS
baseurl=http://download.eng.bos.redhat.com/rhel-9/nightly/RHEL-9/latest-RHEL-9/compose/BaseOS/$basearch/os/
enabled=1
gpgcheck=0

[rhel9-appstream]
name=RHEL 9 AppStream
baseurl=http://download.eng.bos.redhat.com/rhel-9/nightly/RHEL-9/latest-RHEL-9/compose/AppStream/$basearch/os/
enabled=1
gpgcheck=0

[rhel9-crb]
name=RHEL 9 CRB
baseurl=http://download.eng.bos.redhat.com/rhel-9/nightly/RHEL-9/latest-RHEL-9/compose/CRB/$basearch/os/
enabled=1
gpgcheck=0

[rhel9-buildroot]
name=RHEL 9 Buildroot
baseurl=http://download.eng.bos.redhat.com/rhel-9/nightly/BUILDROOT-9/latest-BUILDROOT-9-RHEL-9/compose/Buildroot/$basearch/os
enabled=1
gpgcheck=0
"""

