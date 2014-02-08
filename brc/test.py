from _brc import *

def started(ec):
    print ec

def newtx(tx_hash):
    print "tx:", tx_hash.encode("hex")

b = Broadcaster()
# b.start(number_thread, number_broadcast_hosts, number_monitor_hosts, ...)
# If we set the number of monitoring hosts to N, then when we
# broadcast a tx to the broadcast group, we expect to hear
# the tx back N times.
# You can use this to construct a 'transaction radar'. i.e if you connect
# to 100 nodes, then 100 responses back = 100% propagation through network.
b.start(1, 10, 4, newtx, started)
# To broadcast a tx use:
#   b.broadcast(raw_tx)
# Where raw_tx is the raw tx data bytes.
raw_input()
# You must stop otherwise exception is thrown.
b.stop()

