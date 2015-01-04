import time
import obelisk
import zmq
import txrad
import config
import struct
from collections import defaultdict
from twisted.internet import reactor

def hash_transaction(raw_tx):
    return obelisk.Hash(raw_tx)[::-1]

class Broadcaster:

    def __init__(self):
        self.last_nodes = 0
        self.notifications = defaultdict(list)
        self._ctx = zmq.Context()
        self._socket = self._ctx.socket(zmq.PUSH)
        self._socket.connect(config.get("broadcaster-url", "tcp://localhost:9109"))
        reactor.callInThread(self.status_loop)
        reactor.callInThread(self.feedback_loop)

    def feedback_loop(self, *args):
        # feedback socket
        ctx = zmq.Context()
        socket = ctx.socket(zmq.SUB)
        socket.setsockopt(zmq.SUBSCRIBE, "")
        socket.connect(config.get("broadcaster-error-url", "tcp://localhost:9110"))
        print "brc error connected"
        while True:
            msg = [socket.recv()]
            while socket.getsockopt(zmq.RCVMORE):
                msg.append(socket.recv())
            if len(msg) == 3:
                self.on_feedback_msg(*msg)
            else:
                print "bad feedback message", msg

    def on_feedback_msg(self, hash, num, error):
        try:
            num = struct.unpack("<Q", num)[0]
            #print "error", hash.encode('hex'), num, error
        except:
            print "error decoding brc feedback"
        try:
            # trigger notifications
            for notify in self.notifications[hash]:
                notify(num, 'brc', error)
            del self.notifications[hash]
        except:
            print "error sending client notifications"

    def status_loop(self, *args):
        # feedback socket
        print "connect brc feedback"
        ctx = zmq.Context()
        socket = ctx.socket(zmq.SUB)
        socket.setsockopt(zmq.SUBSCRIBE, "")
        socket.connect(config.get("broadcaster-feedback-url", "tcp://localhost:9112"))
        print "brc connected"
        while True:
            msg = socket.recv()
            nodes = 0
            try:
                nodes = struct.unpack("<Q", msg)[0]
            except:
                print "bad nodes data", msg
            if not nodes == self.last_nodes:
                print "nodes", nodes
                self.last_nodes = nodes

    def broadcast(self, raw_tx, notify):
        tx_hash = hash_transaction(raw_tx)
        self.notifications[tx_hash].append(notify)
        self._socket.send(raw_tx)

class NotifyCallback:

    def __init__(self, socket_handler, request_id):
        self._handler = socket_handler
        self._request_id = request_id

    def __call__(self, count, type='radar', error=None):
        response = {
            "id": self._request_id,
            "error": error or None,
            "result": [count, type]
        }
        self._handler.queue_response(response)

class BroadcastHandler:

    def __init__(self):
        self._brc = Broadcaster()
        self._txrad = txrad.TxRadar()

    def handle_request(self, socket_handler, request):
        if request["command"] != "broadcast_transaction":
            return False
        if not request["params"]:
            logging.error("No param for broadcast specified.")
            return True
        raw_tx = request["params"][0].decode("hex")
        request_id = request["id"]
        # Prepare notifier object
        notify = NotifyCallback(socket_handler, request_id)
        # Broadcast...
        self._brc.broadcast(raw_tx, notify)
        # And monitor.
        tx_hash = hash_transaction(raw_tx)
        self._txrad.monitor(tx_hash, notify)
        notify(0.0)
        return True

