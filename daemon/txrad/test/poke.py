import zmq
context = zmq.Context()
socket = context.socket(zmq.PUSH)
socket.connect("tcp://localhost:7674")
socket.send("106c370590c0cd20a868721e8a582496c129aabafbb72bcb0d17d516950c467f".decode("hex"))

