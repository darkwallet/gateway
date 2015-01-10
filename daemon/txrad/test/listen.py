import zmq
context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.setsockopt(zmq.SUBSCRIBE, "")
socket.connect("tcp://localhost:7675")
while True:
    print "tx hash:", socket.recv()
    print "ratio (%):", socket.recv()

