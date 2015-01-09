from tx_sentinel import *

def started(ec):
    print "started:", ec

def newtx(tx_hash):
    print "tx:", tx_hash.encode("hex")

number_threads = 1
number_hosts = 10
# Whether to display output.
display_output = True

sentinel = TxSentinel()
# b.start(number_threads, number_hosts, ...)
# If we set the number of monitoring hosts to N, then when we
# broadcast a tx we expect to hear the tx back N times.
# You can use this to construct a 'transaction radar'. i.e if you connect
# to 100 nodes, then 100 responses back = 100% propagation through network.
sentinel.start(display_output, number_threads, number_hosts, newtx, started)
# Wait for user input. sentinel runs in the background.
raw_input()
print "Total connections:", sentinel.total_connections
raw_input()
# You must stop otherwise exception is thrown.
sentinel.stop()

