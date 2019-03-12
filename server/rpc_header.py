# coding: utf8

import os
import math
import json
import struct
import asyncore
from cStringIO import StringIO


class RPCHandler(asyncore.dispatcher_with_send):

    def __init__(self, sock, addr):
        asyncore.dispatcher_with_send.__init__(self, sock=sock)
        self.addr = addr
        self.handlers = {
            "ping": self.ping,
            "pi": self.pi
        }
        self.rbuf = StringIO()

    def handle_connect(self):
        print self.addr, 'comes'

    def handle_close(self):
        print self.addr, 'bye'
        self.close()

    def handle_read(self):
        while True:
            content = self.recv(1024)
            if content:
                self.rbuf.write(content)
            if len(content) < 1024:
                break
        self.handle_rpc()

    def handle_rpc(self):
        while True:
            self.rbuf.seek(0)
            length_prefix = self.rbuf.read(4)
            if len(length_prefix) < 4:
                break
            length, = struct.unpack("I", length_prefix)
            body = self.rbuf.read(length)
            if len(body) < length:
                break
            request = json.loads(body)
            in_ = request['in']
            params = request['params']
            print os.getpid(), in_, params
            handler = self.handlers[in_]
            handler(params)
            left = self.rbuf.getvalue()[length + 4:]
            self.rbuf = StringIO()
            self.rbuf.write(left)
        self.rbuf.seek(0, 2)

    def ping(self, params):
        self.send_result("pong", params)

    def pi(self, n):
        s = 0.0
        for i in range(n+1):
            s += 1.0/(2*i+1)/(2*i+1)
        result = math.sqrt(8*s)
        self.send_result("pi_r", result)

    def send_result(self, out, result):
        response = {"out": out, "result": result}
        body = json.dumps(response)
        length_prefix = struct.pack("I", len(body))
        self.send(length_prefix)
        self.send(body)