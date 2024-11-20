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

* `ca/cert.pem`: Certificate Authority
* `ca/cert.key`: Certificate Authority key without any password
* `server/cert.pem`: MTLS server certificate signed by `test-ca.crt`
* `server/key.pem`: MTLS server certificate key without any password
* `client/cert.pem`: MTLS client certificate signed by `test-ca.crt`
* `client/key.pem`: MTLS client certificate key without any password

Quick test:

```
openssl s_server -accept 4433 -www \
    -CAfile ./ca/cert.pem \
    -cert ./server/cert.pem \
    -key ./server/key.pem
```

And client:

```
openssl s_client -connect localhost:4433 \
    -CAfile ./ca/cert.pem \
    -cert ./client/cert.pem \
    -key ./client/cert.pem
```

A python server:

```python
import http.server
import ssl

cert_dir = "."
cacert = cert_dir + "ca/cert.pem"
servercert = cert_dir + "server/cert.pem"
serverkey = cert_dir + "server/key.pem"
clientcert = cert_dir + "client/cert.pem"
clientkey = cert_dir + "client/key.pem"
httpd = http.server.HTTPServer(('127.0.0.1', 4433), http.server.SimpleHTTPRequestHandler)
ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile=cacert)
ctx.load_cert_chain(certfile=servercert, keyfile=serverkey)
ctx.verify_mode = ssl.CERT_REQUIRED
httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
httpd.serve_forever()
```
