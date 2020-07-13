#
# Test for monitoring classes and integration
#

import json
import os
import multiprocessing as mp
import sys
import tempfile
import unittest

import osbuild
import osbuild.meta
from osbuild.api import API
from osbuild.monitor import LogMonitor
from osbuild.util import jsoncomm
from .. import test


def setup_stdio(path):
    """Copy of what the osbuild runners do to setup stdio"""
    with jsoncomm.Socket.new_client(path) as client:
        req = {'method': 'setup-stdio'}
        client.send(req)
        msg, fds, _ = client.recv()
        for sio in ['stdin', 'stdout', 'stderr']:
            target = getattr(sys, sio)
            source = fds[msg[sio]]
            os.dup2(source, target.fileno())
        fds.close()


def echo(path):
    """echo stdin to stdout after setting stdio up via API

    Meant to be called as the main function in a process
    simulating an osbuild runner and a stage run which does
    nothing but returns the supplied options to stdout again.
    """
    setup_stdio(path)
    data = json.load(sys.stdin)
    json.dump(data, sys.stdout)
    sys.exit(0)


class TestMonitor(unittest.TestCase):
    def test_log_monitor_api(self):
        # Basic log and API integration check
        with tempfile.TemporaryDirectory() as tmpdir:
            args = {"foo": "bar"}
            path = os.path.join(tmpdir, "osbuild-api")
            logfile = os.path.join(tmpdir, "log.txt")

            with open(logfile, "w") as log, \
                 API(path, args, LogMonitor(log.fileno())) as api:
                p = mp.Process(target=echo, args=(path, ))
                p.start()
                p.join()
                self.assertEqual(p.exitcode, 0)
                output = api.output
                assert output

            self.assertEqual(json.dumps(args), output)
            with open(logfile) as f:
                log = f.read()
            self.assertEqual(log, output)

    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    def test_log_monitor_vfuncs(self):
        # Checks the basic functioning of the LogMonitor
        pipeline = osbuild.Pipeline("org.osbuild.linux")
        pipeline.add_stage("org.osbuild.noop", {}, {
            "isthisthereallife": False
        })
        pipeline.set_assembler("org.osbuild.noop")

        with tempfile.TemporaryDirectory() as tmpdir:
            storedir = os.path.join(tmpdir, "store")
            outputdir = os.path.join(tmpdir, "output")

            logfile = os.path.join(tmpdir, "log.txt")

            with open(logfile, "w") as log:
                monitor = LogMonitor(log.fileno())
                res = pipeline.run(storedir,
                                   monitor,
                                   libdir=os.path.abspath(os.curdir),
                                   output_directory=outputdir)

                with open(logfile) as f:
                    log = f.read()

            assert res
            self.assertIn(pipeline.stages[0].id, log)
            self.assertIn(pipeline.assembler.id, log)
            self.assertIn("isthisthereallife", log)
