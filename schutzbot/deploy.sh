#!/bin/bash
set -euxo pipefail

function retry {
    local count=0
    local retries=5
    until "$@"; do
        exit=$?
        count=$(($count + 1))
        if [[ $count -lt $retries ]]; then
            echo "Retrying command..."
            sleep 1
        else
            echo "Command failed after ${retries} retries. Giving up."
            return $exit
        fi
    done
    return 0
}

# Get OS details.
source /etc/os-release

# Restart systemd to work around some Fedora issues in cloud images.
sudo systemctl restart systemd-journald

# Remove Fedora's modular repositories to speed up dnf.
sudo rm -f /etc/yum.repos.d/fedora*modular*

# Enable fastestmirror and disable weak dependency installation to speed up
# dnf operations.
echo -e "fastestmirror=1\ninstall_weak_deps=0" | sudo tee -a /etc/dnf/dnf.conf

# Add osbuild team ssh keys.
cat schutzbot/team_ssh_keys.txt | tee -a ~/.ssh/authorized_keys > /dev/null

# Set up a dnf repository for the RPMs we built via mock.
sudo cp osbuild-mock.repo /etc/yum.repos.d/osbuild-mock.repo
sudo dnf repository-packages osbuild-mock list

# Install the Image Builder packages.
# Note: installing only -tests to catch missing dependencies
retry sudo dnf -y install osbuild-composer-tests

# Copy the internal repositories into place when needed.
if curl -fs http://download.devel.redhat.com > /dev/null; then

    # Set up a directory to hold repository overrides.
    sudo mkdir -p /etc/osbuild-composer/repositories

    # Clone the latest version of osbuild-composer.
    git clone https://github.com/osbuild/osbuild-composer osbuild-composer

    case "${ID}${VERSION_ID}" in
        fedora31)
            sudo cp osbuild-composer/test/internal-repos/fedora-31.json \
                /etc/osbuild-composer/repositories/fedora-31.json
        ;;
        fedora32)
            sudo cp osbuild-composer/test/internal-repos/fedora-32.json \
                /etc/osbuild-composer/repositories/fedora-32.json
        ;;
        rhel8.2)
            sudo cp osbuild-composer/test/external-repos/rhel-8.json \
                /etc/osbuild-composer/repositories/rhel-8.json
        ;;
        rhel8.3)
            sudo cp osbuild-composer/test/internal-repos/rhel-8.json \
                /etc/osbuild-composer/repositories/rhel-8.json
        ;;
    esac

fi

# Start services.
sudo systemctl enable --now osbuild-rcm.socket
sudo systemctl enable --now osbuild-composer.socket

# Verify that the API is running.
sudo composer-cli status show
sudo composer-cli sources list