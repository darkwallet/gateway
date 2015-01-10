import struct
import sys
import threading
import tx_sentinel
import zmq

def started():
    print "TxRadar started."

class TxRadar:

    radar_hosts = 20
    display_output = False
    number_threads = 1

    def __init__(self):
        self._monitor_tx = {}
        self._monitor_lock = threading.Lock()
        self._sentinel = tx_sentinel.TxSentinel()
        self._sentinel.start(
            TxRadar.display_output, TxRadar.number_threads,
            TxRadar.radar_hosts, self._new_tx, started)

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
        ratio = float(count) / TxRadar.radar_hosts
        # Maybe one node reports a tx back to us twice.
        # No biggie. We just cover it up, and pretend it didn't happen.
        ratio = min(ratio, 1.0)
        # Call callback to notify tx was seen
        notify_callback(ratio)

    def monitor(self, tx_hash, notify_callback):
        # Add tx to monitor list for radar
        with self._monitor_lock:
            self._monitor_tx[tx_hash] = [0, notify_callback]

    @property
    def total_connections(self):
        return self._sentinel.total_connections

if __name__ == "__main__":
    txradar = TxRadar()
    context = zmq.Context()
    monitor_socket = context.socket(zmq.PULL)
    monitor_socket.bind("tcp://*:7674")
    pulse_socket = context.socket(zmq.PUB)
    pulse_socket.bind("tcp://*:7675")
    while True:
        tx_hash = monitor_socket.recv()
        def notify(ratio):
            value = int(ratio * 100)
            print "Sending", value, "for", tx_hash
            data = struct.pack("<B", value)
            pulse_socket.send(tx_hash)
            pulse_socket.send(data)
        txradar.monitor(tx_hash, notify)

