# Setup

To run the tests in vagrant virtual machine, please follow this tutorial:
https://developer.fedoraproject.org/tools/vagrant/vagrant-libvirt.html

(run also `sudo systemctl start libvirtd`)

# Using Vagrant

To start a Vagrant box by hand, run `vagrant up` in this directory. To stop and remove all volumes run `vagrant destroy` again in this directory.

# Troubleshooting

In case you accidentally deleted `.vagrant` directory, you can use some of these commands in order to get rid of running instance:
```
$ virsh list # this should display test_default
$ virsh managedsave-remove test_default
$ virsh undefine test_default
# or using vagrant cli tool
$ vagrant global-status
$ vagrant destroy <id>
$ vagrant global-status --prune
```
