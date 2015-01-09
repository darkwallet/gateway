import sys
import threading
import tx_sentinel

class TxRadar:

    radar_hosts = 20
    display_output = False
    number_threads = 1

    def __init__(self):
        self._monitor_tx = {}
        self._monitor_lock = threading.Lock()
        self._sentinel = tx_sentinel.TxSentinel()
        self._sentinel.start(display_output, number_threads,
            TxRadar.radar_hosts, self._new_tx)

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

