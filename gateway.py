#!/usr/bin/env python

import logging
import tornado.options
import tornado.web
import tornado.websocket
import os.path
import json
import obelisk
import json
import threading
import random
import base58

from tornado.web import asynchronous, HTTPError

# Install Tornado reactor loop into Twister
# http://www.tornadoweb.org/en/stable/twisted.html

# from tornado.platform.twisted import TwistedIOLoop
# from twisted.internet import reactor
# TwistedIOLoop().install()

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)


global ioloop
ioloop = tornado.ioloop.IOLoop.instance()


class ObeliskApplication(tornado.web.Application):

    def __init__(self):

        settings = dict(debug=True)

        self.client = obelisk.ObeliskOfLightClient('tcp://85.25.198.97:8081')
        self._obelisk_handler = ObeliskHandler(self.client)

        handlers = [
            (r"/block/([^/]*)(?:/)?", BlockHeaderHandler), #/block/<block hash>
            (r"/block/([^/]*)/transactions(?:/)?", BlockTransactionsHandler), #/block/<block hash>/transactions
            (r"/tx(?:/)?", TransactionPoolHandler), #/tx/
            (r"/tx/([^/]*)(?:/)?", TransactionHandler), # /tx/<txid>
            (r"/address/([^/]*)(?:/)?", AddressHistoryHandler), #/address/<address>
            (r"/height(?:/)?", HeightHandler), #/height

            (r"/", QuerySocketHandler) #/
        ]

        tornado.web.Application.__init__(self, handlers, **settings)


# Implements the on_fetch method for all HTTP requests.
class BaseHTTPHandler(tornado.web.RequestHandler):
    def on_fetch(self, response):
        self.finish(json.dumps(response))


class BlockHeaderHandler(tornado.web.RequestHandler):
    @asynchronous
    def get(self, blk_hash=None):
        if blk_hash is None:
            raise HTTPError(400, reason="No block hash")

        try:
            blk_hash = blk_hash.decode("hex")
        except ValueError:
            raise HTTPError(400, reason="Invalid hash")

        request = {
            "id": random.randint(0, 2**32-1),
            "command":"fetch_block_header",
            "params": [blk_hash]
        }

        self.application._obelisk_handler.handle_request(self, request)


class BlockTransactionsHandler(tornado.web.RequestHandler):
    @asynchronous
    def get(self, blk_hash=None):
        if blk_hash is None:
            raise HTTPError(400, reason="No block hash")

        try:
            blk_hash = blk_hash.decode("hex")
        except ValueError:
            raise HTTPError(400, reason="Invalid hash")

        request = {
            "id": random.randint(0, 2**32-1),
            "command":"fetch_block_transaction_hashes",
            "params": [blk_hash]
        }

        self.application._obelisk_handler.handle_request(self, request)

class TransactionPoolHandler(tornado.web.RequestHandler):
    @asynchronous
    # Dump transaction pool to user
    def get(self):
        raise NotImplementedError

    def on_fetch(self, ec, pool):
        raise NotImplementedError

    # Send tx if it is valid,
    # validate if ?validate is in url...
    def post(self):
        raise NotImplementedError


class TransactionHandler(tornado.web.RequestHandler):
    @asynchronous
    def get(self, tx_hash=None):
        if tx_hash is None:
            raise HTTPError(400, reason="No block hash")

        try:
            tx_hash = tx_hash.decode("hex")
        except ValueError:
            raise HTTPError(400, reason="Invalid hash")

        request = {
            "id": random.randint(0, 2**32-1),
            "command":"fetch_transaction",
            "params": [tx_hash]
        }

        self.application._obelisk_handler.handle_request(self, request)

class AddressHistoryHandler(tornado.web.RequestHandler):
    @asynchronous
    def get(self, address=None):
        if address is None:
            raise HTTPError(400, reason="No address")

        try:
            from_height = long(self.get_argument("from_height", 0))
        except:
            raise HTTPError(400)

        address_decoded = base58.b58decode(address)
        address_version = address_decoded[0]
        address_hash = address_decoded[1:21]

        request = {
            "id": random.randint(0, 2**32-1),
            "command":"fetch_history",
            "params": [address_version, address_hash, from_height]
        }

        self.application._obelisk_handler.handle_request(self, request)


class BaseHTTPHandler(tornado.web.RequestHandler):
    def on_fetch(self, response):
        self.finish(response)


class HeightHandler(BaseHTTPHandler):
    @asynchronous
    def get(self):
        request = {
            "id": random.randint(0, 2**32-1),
            "command":"fetch_last_height",
            "params": None
        }

        self.application._obelisk_handler.handle_request(self, request)


listeners = set() # set of WebsocketHandler
listen_lock = threading.Lock() # protects listeners


class QuerySocketHandler(tornado.websocket.WebSocketHandler):

    def initialize(self, obelisk_client):
        # self._obelisk_handler = ObeliskHandler(obelisk_client)
        self._obelisk_handler = ObeliskHandler(self.application.obelisk_client)

    def open(self):
        logging.info("OPEN")
        with listen_lock:
            self.listeners.add(self)

    def on_close(self):
        logging.info("CLOSE")
        with listen_lock:
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

class ObFetchLastHeight(ObeliskCallbackBase):

    def translate_response(self, result):
        assert len(result) == 1
        return result

class ObFetchTransaction(ObeliskCallbackBase):

    def translate_arguments(self, params):
        if len(params) != 1:
            raise ValueError("Invalid parameter list length")
        tx_hash = params[0].decode("hex")
        if len(tx_hash) != 32:
            raise ValueError("Not a tx hash")
        return (tx_hash,)

    def translate_response(self, result):
        assert len(result) == 1
        tx = result[0]
        tx_dict = {
            "version": tx.version,
            "locktime": tx.locktime,
            "inputs": [],
            "outputs": []
        }
        for input in tx.inputs:
            input_dict = {
                "previous_output": [
                    input.previous_output.hash.encode("hex"),
                    input.previous_output.index
                ],
                "script": input.script.encode("hex"),
                "sequence": input.sequence
            }
            tx_dict["inputs"].append(input_dict)
        for output in tx.outputs:
            output_dict = {
                "value": output.value,
                "script": output.script.encode("hex")
            }
            tx_dict["outputs"].append(output_dict)
        return (tx_dict,)

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


class ObeliskHandler:

    valid_messages = ['fetch_block_header', 'fetch_history', 'subscribe',
        'fetch_last_height', 'fetch_transaction', 'fetch_spend',
        'fetch_transaction_index', 'fetch_block_transaction_hashes',
        'fetch_block_height', 'update', 'renew']

    handlers = {
        "fetch_last_height": ObFetchLastHeight,
        "fetch_transaction": ObFetchTransaction,
        "fetch_history":     ObFetchHistory,
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



if __name__ == "__main__":
    application = ObeliskApplication()

    tornado.autoreload.start(ioloop)

    application.listen(8888)
    ioloop.start()

