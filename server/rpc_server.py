# coding:utf-8
import os
import json
import signal
import socket
import errno
import sys
import asyncore
from kazoo.client import KazooClient


from .rpc_header import RPCHandler

class RPCServer(asyncore.dispatcher):

    zk_root = "/demo"
    zk_rpc = zk_root + "/rpc"

    def __init__(self, host, port):
        asyncore.dispatcher.__init__(self)
        self.host = host
        self.port = port
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(1)
        self.child_pids = []
        if self.prefork(10):  # 产生子进程
            self.register_zk()  # 注册服务
            self.register_parent_signal()  # 父进程善后处理
        else:
            self.register_child_signal()  # 子进程善后处理

    def prefork(self, n):
        for i in range(n):
            pid = os.fork()
            if pid < 0:  # fork error
                raise 1
            if pid > 0:  # parent process
                self.child_pids.append(pid)
                continue
            if pid == 0:
                return False  # child process
        return True

    def register_zk(self):
        self.zk = KazooClient(hosts='127.0.0.1:2181')
        self.zk.start()
        self.zk.ensure_path(self.zk_root)  # 创建根节点
        value = json.dumps({"host": self.host, "port": self.port})
        # 创建服务子节点
        self.zk.create(self.zk_rpc, value, ephemeral=True, sequence=True)

    def exit_parent(self, sig, frame):
        self.zk.stop()  # 关闭 zk 客户端
        self.close()  # 关闭 serversocket
        asyncore.close_all()  # 关闭所有 clientsocket
        pids = []
        for pid in self.child_pids:
            print 'before kill'
            try:
                os.kill(pid, signal.SIGINT)  # 关闭子进程
                pids.append(pid)
            except OSError, ex:
                if ex.args[0] == errno.ECHILD:  # 目标子进程已经提前挂了
                    continue
                raise ex
            print 'after kill', pid
        for pid in pids:
            while True:
                try:
                    os.waitpid(pid, 0)  # 收割目标子进程
                    break
                except OSError, ex:
                    if ex.args[0] == errno.ECHILD:  # 子进程已经割过了
                        break
                    if ex.args[0] != errno.EINTR:
                        raise ex  # 被其它信号打断了，要重试
            print 'wait over', pid

    def reap_child(self, sig, frame):
        print 'before reap'
        while True:
            try:
                info = os.waitpid(-1, os.WNOHANG)  # 收割任意子进程
                break
            except OSError, ex:
                if ex.args[0] == errno.ECHILD:
                    return  # 没有子进程可以收割
                if ex.args[0] != errno.EINTR:
                    raise ex  # 被其它信号打断要重试
        pid = info[0]
        try:
            self.child_pids.remove(pid)
        except ValueError:
            pass
        print 'after reap', pid

    def register_parent_signal(self):
        signal.signal(signal.SIGINT, self.exit_parent)
        signal.signal(signal.SIGTERM, self.exit_parent)
        signal.signal(signal.SIGCHLD, self.reap_child)  # 监听子进程退出

    def exit_child(self, sig, frame):
        self.close()  # 关闭 serversocket
        asyncore.close_all()  # 关闭所有 clientsocket
        print 'all closed'

    def register_child_signal(self):
        signal.signal(signal.SIGINT, self.exit_child)
        signal.signal(signal.SIGTERM, self.exit_child)

    def handle_accept(self):
        pair = self.accept()  # 接收新连接
        if pair is not None:
            sock, addr = pair
            RPCHandler(sock, addr)


if __name__ == '__main__':
    host = sys.argv[1]
    port = int(sys.argv[2])
    RPCServer(host, port)
    asyncore.loop()  # 启动事件循环