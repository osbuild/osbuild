This directory contains custom self-signed and worthless certs used
during testing. They are not dynamically generated to avoid the extra
compuation time during tests (but they could be).

Generated via:
```
$ openssl req -new -newkey rsa:2048  -nodes -x509  \
   -subj "/C=DE/ST=Berlin/L=Berlin/O=Org/CN=localhost"   \
   -keyout "key1.pem" -out "cert1.pem"
```
