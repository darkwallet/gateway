import obelisk
import zmq
import txrad
import config

def hash_transaction(raw_tx):
    return obelisk.Hash(raw_tx)[::-1]

class Broadcaster:

    def __init__(self):
        self._ctx = zmq.Context()
        self._socket = self._ctx.socket(zmq.PUSH)
        self._socket.connect(config.get("broadcaster-url", "tcp://localhost:9109"))

    def broadcast(self, raw_tx):
        self._socket.send(raw_tx)

class NotifyCallback:

    def __init__(self, socket_handler, request_id):
        self._handler = socket_handler
        self._request_id = request_id

    def __call__(self, count):
        response = {
            "id": self._request_id,
            "error": None,
            "result": [count]
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
        # Broadcast...
        self._brc.broadcast(raw_tx)
        # And monitor.
        notify = NotifyCallback(socket_handler, request_id)
        tx_hash = hash_transaction(raw_tx)
        self._txrad.monitor(tx_hash, notify)
        notify(0.0)
        return True

