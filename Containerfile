FROM quay.io/centos/centos:stream9

RUN dnf -y install dnf-plugins-core && \
    dnf -y install \
      util-linux-core \
      bubblewrap \
      systemd \
      policycoreutils \
      python3-devel \
      python3-setuptools \
      python3-docutils && \
    dnf clean all

# Set the working directory for the subsequent steps.
WORKDIR /src
COPY . .
RUN pip install --prefix=/usr .
RUN mkdir /etc/containers
# mount point for bind mounting the osbuild library
RUN mkdir /usr/lib/osbuild/osbuild

ENTRYPOINT [ "osbuild" ]
