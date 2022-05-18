/// You are reading the source code for the `org-osbuild-http` source module. This file is part of
/// the [osbuild](https://osbuild.org/) project to build repeatable operating system images and can
/// be found in the [osbuild repository](https://github.com/osbuild/osbuild).
///
/// The `org-osbuild-http` module provides the capability to download sources over HTTP(s), it
/// verifies each file after it has been downloaded with the checksum required by the manifest
/// passed to `osbuild`. The module also caches all requests to make sure a request is not
/// performed multiple times unless absolutely necessary.
///
/// Requests can be made with secrets, which are TLS client certificates to authorize downloading
/// of private sources.
///
/// When this module starts it connects to an AF_UNIX socket it receives through its arguments, it
/// will receive a list of files to download over that socket and send any progress and output over
/// the same socket.
///
/// `org-osbuild-http` takes two arguments that can be of help, the `-s/--schema` argument will
/// have the program output its expected schema for use in manifest files. The `-m/--meta` argument
/// will output the protocol spoken by `org-osbuild-http`.
///
/// This file is licensed under the Apache-2.0 license located in the root of this repository.

pub mod osbuild {
  /// `osbuild` speaks a wire between the host executable and machine and binaries that perform
  /// its actions. These binaries are called modules and can be ran either inside or outside of a
  /// sandbox.
  ///
  /// TODO: This would move to a separate library once multiple modules are implemented in the Rust
  /// language.
  ///
  /// TODO: This currently only implements what is necessary to get `org-osbuild-http` set up and
  /// running, it's possible that it needs to be extended for other (types of) modules but
  /// hopefully not changed.

  pub mod wire {
    /// Traits and structs related to the wire protocol itself, how to transport data and how to
    /// encode data for transport. Transports determine how data moves around, they have no
    /// insight in what is being sent over them. Encodings determine the bytes that are sent over
    /// the transports for various messages.

    use std::os::unix::net::{UnixDatagram};

    use serde_json;
    use log::{trace};

    use format::{Envelope, Message, Signal, Method, Reply, Exception};

    pub trait Transport {
      fn new_client(conn_path: &str) -> std::io::Result<Self> where Self: Sized;
      fn new_server(bind_path: &str) -> std::io::Result<Self> where Self: Sized;

      fn accept(&self);
      fn listen(&self, backlog: i32);
      fn close(&self);

      fn recv(&self, buf: &mut [u8]) -> std::io::Result<usize>;
      fn send(&self);

      fn send_and_recv(&self);
    }

    pub struct UnixSocket {
      socket: UnixDatagram
    }

    impl Transport for UnixSocket {
      fn new_client(conn_path: &str) -> std::io::Result<Self> {
        let socket = UnixDatagram::unbound()?;

        match socket.connect(conn_path) {
          Ok(socket) => socket,
          Err(e) => {
            return Err(e);
          }
        }

        Ok(Self{ socket: socket })
      }

      fn new_server(bind_path: &str) -> std::io::Result<Self> {
        Ok(Self{ socket: UnixDatagram::bind(bind_path)? })
      }

      fn accept(&self) { }
      fn listen(&self, backlog: i32) { }
      fn close(&self) { }

      fn recv(&self, buf: &mut [u8]) -> std::io::Result<usize> {
        trace!("UnixSocket.recv: waiting for socket data");
        let received = self.socket.recv(buf).unwrap();
        trace!("UnixSocket.recv: received {} of socket data", received);
        Ok(received)
      }

      fn send(&self) {
        self.socket.send(b"hi there!").unwrap();
      }

      fn send_and_recv(&self) { }
    }

    pub trait Encoding {
      fn new() -> Self where Self: Sized;

      fn encode_message(&self, message: Message) -> Vec<u8>;
      fn decode_message(&self, message: &str) -> Message;

      fn encode_method(&self, method: Method) -> Vec<u8>;
      fn decode_method(&self, method: &str) -> Method;

      fn encode_reply(&self, reply: Reply) -> Vec<u8>;
      fn decode_reply(&self, reply: &str) -> Reply;

      fn encode_signal(&self, signal: Signal) -> Vec<u8>;
      fn decode_signal(&self, signal: &str) -> Signal;

      fn encode_exception(&self, exception: Exception) -> Vec<u8>;
      fn decode_exception(&self, exception: &str) -> Exception;
    }

    pub struct JSON { }

    impl Encoding for JSON {
      fn new() -> Self {
        Self{}
      }

      fn encode_message(&self, message: Message) -> Vec<u8> {
        trace!("encoding message");

        serde_json::to_string(&message).unwrap().as_str().as_bytes().to_vec()
      }

      fn decode_message(&self, message: &str) -> Message {
        Message{}
      }

      fn encode_method(&self, method: Method) -> Vec<u8> {
        trace!("encoding method");

        serde_json::to_string(&method).unwrap().as_str().as_bytes().to_vec()
      }

      fn decode_method(&self, method: &str) -> Method {
        Method{}
      }

      fn encode_reply(&self, reply: Reply) -> Vec<u8> {
        trace!("encoding reply");

        serde_json::to_string(&reply).unwrap().as_str().as_bytes().to_vec()
      }

      fn decode_reply(&self, reply: &str) -> Reply {
        Reply{}
      }

      fn encode_signal(&self, signal: Signal) -> Vec<u8> {
        trace!("encode signal");

        serde_json::to_string(&signal).unwrap().as_str().as_bytes().to_vec()
      }

      fn decode_signal(&self, signal: &str) -> Signal {
        Signal{}
      }

      fn encode_exception(&self, exception: Exception) -> Vec<u8> {
        trace!("encode exception");

        serde_json::to_string(&exception).unwrap().as_str().as_bytes().to_vec()
      }

      fn decode_exception(&self, exception: &str) -> Exception {
        Exception{}
      }
    }

    pub mod format {
      use serde::{Serialize, Deserialize};

      /// All types of objects are contained inside a wrapper object which contains the type and
      /// the data used.
      #[derive(Serialize, Deserialize, Debug)]
      pub struct Envelope {
        r#type: String,
        data: String 
      }

      /// The various types of objects that can be encoded and passed over the wire.
      #[derive(Serialize, Deserialize, Debug)]
      pub struct Message { }

      #[derive(Serialize, Deserialize, Debug)]
      pub struct Method { }

      #[derive(Serialize, Deserialize, Debug)]
      pub struct Reply { }

      #[derive(Serialize, Deserialize, Debug)]
      pub struct Signal { }

      #[derive(Serialize, Deserialize, Debug)]
      pub struct Exception { }

      impl Envelope {
        fn new() -> Self {
          Self {
            r#type: "bar".to_string(),
            data: "foo".to_string(),
          }
        }
      }
    }
  }

  pub mod module {
    pub mod service {
      /// Traits that services need to implement.

      use super::super::wire::{Encoding, JSON, Transport, UnixSocket};

      pub trait Service<'a> {
        fn from_args(cache: &'a str, path: &'a str) -> std::io::Result<Self> where Self: Sized;
        fn main(&self);
      }
    }

    pub mod kind {
      /// Traits for different module-kinds to implement.

      pub trait Source {
        fn cached(&self, checksum: &str) -> bool;

        fn download(&self);
        fn download_one(&self);
      }
    }
  }
}


static SCHEMA_DATA: &str = r##""additionalProperties": false,
"definitions": {
  "item": {
    "description": "The files to fetch indexed their content checksum",
    "type": "object",
    "additionalProperties": false,
    "patternProperties": {
      "(md5|sha1|sha256|sha384|sha512):[0-9a-f]{32,128}": {
        "oneOf": [
          {
            "type": "string",
            "description": "URL to download the file from."
          },
          {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "url"
            ],
            "properties": {
              "url": {
                "type": "string",
                "description": "URL to download the file from."
              },
              "secrets": {
                "type": "object",
                "additionalProperties": false,
                "required": [
                  "name"
                ],
                "properties": {
                  "name": {
                    "type": "string",
                    "description": "Name of the secrets provider."
                  }
                }
              }
            }
          }
        ]
      }
    }
  }
},
"properties": {
  "items": {"$ref": "#/definitions/item"},
  "urls": {"$ref": "#/definitions/item"}
},
"oneOf": [{
  "required": ["items"]
}, {
  "required": ["urls"]
}]
"##;

use clap::{Parser};
use log::{trace, warn, info, debug};
use stderrlog;

use osbuild::module::service::{Service};
use osbuild::module::kind::{Source};
use osbuild::wire::{Transport, UnixSocket, Encoding, JSON};

#[derive(Parser, Debug)]
#[clap(author, version, about)]
struct Arguments {
    /// Print schema information
    #[clap(short, long)]
    schema: bool,

    /// Print meta information
    #[clap(short, long)]
    meta: bool,
}


struct HttpSource<'a> {
  transport: Box<dyn Transport>,
  encoding: Box<dyn Encoding>,

  cache: &'a str,
}

impl<'a> Service<'a> for HttpSource<'a> {
  fn from_args(cache: &'a str, path: &'a str) -> std::io::Result<Self> where Self: Sized {
    debug!("HttpSource.from_args: cache={}, path={}", cache, path);

    Ok(Self{
      cache: cache,

      transport: Box::new(UnixSocket::new_client(path)?),
      encoding: Box::new(JSON::new()),
    })
  }

  fn main(&self) {
    info!("HttpSource.main: starting main");

    let mut buf = vec![0; 10];

    self.transport.send();
    self.transport.recv(buf.as_mut_slice()).expect("recv failed");

    println!("Service main");
  }
}

impl Source for HttpSource<'_> {
  fn cached(&self, checksum: &str) -> bool {
    false
  }

  fn download(&self) {
  }

  fn download_one(&self) {
  }
}


fn main() {
  stderrlog::new().verbosity(10).module(module_path!()).init().unwrap();

  let args = Arguments::parse();

  if args.schema {
    print!("{}", SCHEMA_DATA);
  } else if args.meta {
    print!("meta!");
  } else {
    trace!("main: Initializing service");

    let service = HttpSource::from_args(
      "/tmp/bar",
      "/tmp/foo"
    ).expect("Could not connect to socket");

    debug!("main: Starting service");

    service.main();
  }
}

// vim: set et ts=2 sw=2:
