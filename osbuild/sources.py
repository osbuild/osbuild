import asyncio
import json
import subprocess
import threading
from .util import jsoncomm


class SourcesServer:
    # pylint: disable=too-many-instance-attributes
    def __init__(self, socket_address, sources_libdir, options, cache, output, secrets=None):
        self.socket_address = socket_address
        self.sources_libdir = sources_libdir
        self.cache = cache
        self.output = output
        self.options = options or {}
        self.secrets = secrets or {}
        self.event_loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop)
        self.barrier = threading.Barrier(2)

    def _run_source(self, source, checksums):
        msg = {
            "options": self.options.get(source, {}),
            "secrets": self.secrets.get(source, {}),
            "cache": f"{self.cache}/{source}",
            "output": f"{self.output}/{source}",
            "checksums": checksums
        }

        r = subprocess.run(
            [f"{self.sources_libdir}/{source}"],
            input=json.dumps(msg),
            stdout=subprocess.PIPE,
            encoding="utf-8",
            check=False)

        try:
            return json.loads(r.stdout)
        except ValueError:
            return {"error": f"source returned malformed json: {r.stdout}"}

    def _dispatch(self, server):
        request, _, addr = server.recv()
        reply = self._run_source(request["source"], request["checksums"])
        server.send(reply, destination=addr)

    def _run_event_loop(self):
        with jsoncomm.Socket.new_server(self.socket_address) as server:
            self.barrier.wait()
            self.event_loop.add_reader(server, self._dispatch, server)
            asyncio.set_event_loop(self.event_loop)
            self.event_loop.run_forever()
            self.event_loop.remove_reader(server)

    def __enter__(self):
        self.thread.start()
        self.barrier.wait()
        return self

    def __exit__(self, *args):
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.thread.join()


def get(source, checksums, api_path="/run/osbuild/api/sources"):
    with jsoncomm.Socket.new_client(api_path) as client:
        msg = {
            "source": source,
            "checksums": checksums
        }
        client.send(msg)
        reply, _, _ = client.recv()
        if "error" in reply:
            raise RuntimeError(f"{source}: " + reply["error"])
        return reply
