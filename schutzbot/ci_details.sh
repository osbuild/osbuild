#!/bin/bash
# Dumps details about the instance running the CI job.

PRIMARY_IP=$(ip route get 8.8.8.8 | head -n 1 | cut -d' ' -f7)
EXTERNAL_IP=$(curl --retry 5 -s -4 icanhazip.com)
PTR=$(curl --retry 5 -s -4 icanhazptr.com)
CPUS=$(nproc)
MEM=$(free -m | grep -oP '\d+' | head -n 1)
DISK=$(df --output=size -h / | sed '1d;s/[^0-9]//g')
HOSTNAME=$(uname -n)
USER=$(whoami)
ARCH=$(uname -m)
KERNEL=$(uname -r)

echo -e "\033[0;36m"
cat << EOF
------------------------------------------------------------------------------
CI MACHINE SPECS
------------------------------------------------------------------------------

     Hostname: ${HOSTNAME}
         User: ${USER}
   Primary IP: ${PRIMARY_IP}
  External IP: ${EXTERNAL_IP}
  Reverse DNS: ${PTR}
         CPUs: ${CPUS}
          RAM: ${MEM} GB
         DISK: ${DISK} GB
         ARCH: ${ARCH}
       KERNEL: ${KERNEL}

------------------------------------------------------------------------------
EOF
echo -e "\033[0m"

echo "List of system repositories:"
yum repolist -v

echo "------------------------------------------------------------------------------"

echo "List of installed packages:"
rpm -qa | sort
echo "------------------------------------------------------------------------------"

# Ensure cloud-init has completely finished on the instance. This ensures that
# the instance is fully ready to go.
while true; do
  if [[ -f /var/lib/cloud/instance/boot-finished ]]; then
    break
  fi
  echo -e "\n🤔 Waiting for cloud-init to finish running..."
  sleep 5
done
