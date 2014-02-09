import threading
import brc
import obelisk

def hash_transaction(self, raw_tx):
    return obelisk.Hash(raw_tx)[::-1]

def test_callback(ratio):
    print "Ratio:", ratio

class Broadcaster:

    broadcast_hosts = 10
    radar_hosts = 20

    def __init__(self):
        self._monitor_tx = {}
        self._monitor_lock = threading.Lock()
        self._brc = brc.Broadcaster()
        self._brc.start(
            1, Broadcaster.broadcast_hosts, Broadcaster.radar_hosts,
            self._new_tx, self._started)

    def _started(self, ec):
        print "Started broadcaster:", ec

    def _increment_monitored_tx(self, tx_hash):
        with self._monitor_lock:
            self._monitor_tx[tx_hash][0] += 1
            return self._monitor_tx[tx_hash]

    def _new_tx(self, tx_hash):
        try:
            count, notify_callback = self._increment_monitored_tx(tx_hash)
        except KeyError:
            # This tx was not broadcasted by us.
            return
        # Percentage propagation throughout network.
        ratio = float(count) / Broadcaster.radar_hosts
        # Maybe one node reports a tx back to us twice.
        # No biggie. We just cover it up, and pretend it didn't happen.
        ratio = min(ratio, 1.0)
        # Call callback to notify tx was seen
        notify_callback(ratio)

    def _monitor(self, tx_hash, notify_callback):
        # Add tx to monitor list for radar
        with self._monitor_lock:
            self._monitor_tx[tx_hash] = [0, notify_callback]

    def broadcast(self, raw_tx, notify_callback):
        #self._brc.broadcast(raw_tx)
        tx_hash = hash_transaction(raw_tx)
        self._monitor(tx_hash, notify_callback)

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

    def handle_request(self, socket_handler, request):
        if request["command"] != "broadcast_transaction":
            return
        if not request["params"]:
            logging.error("No param for broadcast specified.")
            return
        raw_tx = request["params"][0].decode("hex")
        request_id = request["id"]
        notify = NotifyCallback(socket_handler, request_id)
        self._brc.broadcast(raw_tx, notify)

