#!/usr/bin/env python

import logging
import tornado.options
import tornado.web
import tornado.websocket
import os.path
import obelisk
import obelisk.deserialize
import json
import threading

import rest_handlers

# Install Tornado reactor loop into Twister
# http://www.tornadoweb.org/en/stable/twisted.html
from tornado.platform.twisted import TwistedIOLoop
from twisted.internet import reactor
TwistedIOLoop().install()

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)

global ioloop
ioloop = tornado.ioloop.IOLoop.instance()

class ObeliskApplication(tornado.web.Application):

    def __init__(self, service):

        settings = dict(debug=True)

        self.client = obelisk.ObeliskOfLightClient(service)
        self._obelisk_handler = ObeliskHandler(self.client)

        handlers = [
            # /block/<block hash>
            (r"/block/([^/]*)(?:/)?", rest_handlers.BlockHeaderHandler),

            # /block/<block hash>/transactions
            (r"/block/([^/]*)/transactions(?:/)?",
                rest_handlers.BlockTransactionsHandler),

            # /tx/
            (r"/tx(?:/)?", rest_handlers.TransactionPoolHandler),

            # /tx/<txid>
            (r"/tx/([^/]*)(?:/)?", rest_handlers.TransactionHandler),

            # /address/<address>
            (r"/address/([^/]*)(?:/)?", rest_handlers.AddressHistoryHandler),

            # /height
            (r"/height(?:/)?", rest_handlers.HeightHandler),

            # /
            (r"/", QuerySocketHandler)
        ]

        tornado.web.Application.__init__(self, handlers, **settings)

class QuerySocketHandler(tornado.websocket.WebSocketHandler):

    # Set of WebsocketHandler
    listeners = set()
    # Protects listeners
    listen_lock = threading.Lock()

    def initialize(self):
        self._obelisk_handler = ObeliskHandler(self.application.client)

    def open(self):
        logging.info("OPEN")
        with QuerySocketHandler.listen_lock:
            self.listeners.add(self)

    def on_close(self):
        logging.info("CLOSE")
        with QuerySocketHandler.listen_lock:
            self.listeners.remove(self)

    def on_message(self, message):
        try:
            request = json.loads(message)
        except:
            logging.error("Error decoding message: %s", message, exc_info=True)
        logging.info("Request: %s", request)
        if self._obelisk_handler.handle_request(self, request):
            return
        logging.warning("Unhandled command. Dropping request.")

    def on_fetch(self, response):
        self.write_message(json.dumps(response))

class ObeliskCallbackBase(object):

    def __init__(self, handler, request_id):
        self._handler = handler
        self._request_id = request_id

    def __call__(self, *args):
        assert len(args) > 1
        error = args[0]
        assert error is None or type(error) == str
        result = self.translate_response(args[1:])
        response = {
            "id": self._request_id,
            "error": error,
            "result": result
        }
        try:
            # calling write_message or the socket is not thread safe
            ioloop.add_callback(self._handler.on_fetch, response)
        except:
            logging.error("Error adding callback", exc_info=True)

    def translate_arguments(self, params):
        return params

    def translate_response(self, result):
        return result

# Utils used for decoding arguments.

def check_params_length(params, length):
    if len(params) != length:
        raise ValueError("Invalid parameter list length")

def decode_hash(encoded_hash):
    decoded_hash = encoded_hash.decode("hex")
    if len(decoded_hash) != 32:
        raise ValueError("Not a hash")
    return decoded_hash

def unpack_index(index):
    if type(index) == unicode:
        index = str(index)
    if type(index) != str and type(index) != int:
        raise ValueError("Unknown index type")
    if type(index) == str:
        index = index.decode("hex")
        if len(index) != 32:
            raise ValueError("Invalid length for hash index")
    return index

# The actual callback specialisations.

class ObFetchLastHeight(ObeliskCallbackBase):

    def translate_response(self, result):
        assert len(result) == 1
        return result

class ObFetchTransaction(ObeliskCallbackBase):

    def translate_arguments(self, params):
        check_params_length(params, 1)
        tx_hash = decode_hash(params[0])
        return (tx_hash,)

    def translate_response(self, result):
        assert len(result) == 1
        tx = result[0].encode("hex")
        return (tx,)

class ObSubscribe(ObeliskCallbackBase):

    def translate_arguments(self, params):
        check_params_length(params, 1)
        return params[0], self.callback_update

    def callback_update(self, address_version, address_hash,
                        height, block_hash, tx):
        address = obelisk.bitcoin.hash_160_to_bc_address(
            address_hash, address_version)
        tx_data = obelisk.deserialize.BCDataStream()
        tx_data.write(tx)
        response = {
            "type": "update",
            "address": address,
            "height": height,
            "block_hash": block_hash.encode('hex'),
            "tx": obelisk.deserialize.parse_Transaction(tx_data)
        }
        try:
            self._socket.write_message(json.dumps(response))
        except:
            logging.error("Error sending message", exc_info=True)


class ObFetchHistory(ObeliskCallbackBase):

    def translate_response(self, result):
        assert len(result) == 1
        history = []
        for row in result[0]:
            o_hash, o_index, o_height, value, s_hash, s_index, s_height = row
            o_hash = o_hash.encode("hex")
            s_hash = s_hash.encode("hex")
            if s_index == 4294967295:
                s_hash = None
                s_index = None
                s_height = None
            history.append(
                (o_hash, o_index, o_height, value, s_hash, s_index, s_height))
        return (history,)

class ObFetchBlockHeader(ObeliskCallbackBase):

    def translate_arguments(self, params):
        check_params_length(params, 1)
        index = unpack_index(params[0])
        return (index,)

    def translate_response(self, result):
        assert len(result) == 1
        header = result[0].encode("hex")
        return (header,)

class ObFetchBlockTransactionHashes(ObeliskCallbackBase):

    def translate_arguments(self, params):
        check_params_length(params, 1)
        index = unpack_index(params[0])
        return (index,)

    def translate_response(self, result):
        assert len(result) == 1
        tx_hashes = []
        for tx_hash in result[0]:
            assert len(tx_hash) == 32
            tx_hashes.append(tx_hash.encode("hex"))
        return (tx_hashes,)

class ObFetchSpend(ObeliskCallbackBase):

    def translate_arguments(self, params):
        check_params_length(params, 1)
        if len(params[0]) != 2:
            raise ValueError("Invalid outpoint")
        outpoint = obelisk.models.OutPoint()
        outpoint.hash = params[0][0].decode("hex")
        outpoint.index = params[0][1]
        return (outpoint,)

    def translate_response(self, result):
        assert len(result) == 1
        outpoint = result[0]
        outpoint = (outpoint.hash.encode("hex"), outpoint.index)
        return (outpoint,)

class ObFetchTransactionIndex(ObeliskCallbackBase):

    def translate_arguments(self, params):
        check_params_length(params, 1)
        return (params[0],)

class ObFetchBlockHeight(ObeliskCallbackBase):

    def translate_arguments(self, params):
        check_params_length(params, 1)
        return (params[0],)

# Note to self: make tests for remaining methods.

class ObeliskHandler:

    handlers = {
        "fetch_last_height":                ObFetchLastHeight,
        "fetch_transaction":                ObFetchTransaction,
        "fetch_history":                    ObFetchHistory,
        "fetch_block_header":               ObFetchBlockHeader,
        "fetch_block_transaction_hashes":   ObFetchBlockTransactionHashes,
        "fetch_spend":                      ObFetchSpend,
        "fetch_transaction_index":          ObFetchTransactionIndex,
        "fetch_block_height":               ObFetchBlockHeight,
        # Address stuff
        "renew_address":                    ObSubscribe,
        "subscribe_address":                ObSubscribe,
    }

    def __init__(self, client):
        self._client = client

    def handle_request(self, handler, request):
        command = request["command"]
        if command not in self.handlers:
            return False
        method = getattr(self._client, request["command"])
        params = request["params"]
        # Create callback handler to write response to the socket.
        handler = self.handlers[command](handler, request["id"])
        try:
            params = handler.translate_arguments(params)
        except:
            logging.error("Bad parameters specified", exc_info=True)
            return True
        method(*params, cb=handler)
        return True



def main(service):
    application = ObeliskApplication(service)

    tornado.autoreload.start(ioloop)

    application.listen(8888)
    reactor.run()

if __name__ == "__main__":
    service = "tcp://85.25.198.97:9091"
    main(service)

