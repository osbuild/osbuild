This directory contains custom self-signed and worthless certs used
during testing. They are not dynamically generated to avoid the extra
compuation time during tests (but they could be).

Files `cert{1,2}.pem` and `key{1,2}.pem` were generated via:

```
$ openssl req -new -newkey rsa:2048  -nodes -x509  \
   -subj "/C=DE/ST=Berlin/L=Berlin/O=Org/CN=localhost"   \
   -days 36500 \
   -keyout "key1.pem" -out "cert1.pem"
```

The following files were generated via a shell script named `generate-test-certs` and can be used for MTLS testing:

* `test-ca.crt`: Certificate Authority
* `test-ca.key`: Certificate Authority key without any password
* `localhost-server.crt`: MTLS server certificate signed by `test-ca.crt`
* `localhost-server.key`: MTLS server certificate key without any password
* `client1-client.crt`: MTLS client certificate signed by `test-ca.crt`
* `client1-client.key`: MTLS client certificate key without any password
