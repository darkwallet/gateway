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

from tornado.web import asynchronous, HTTPError

# Install Tornado reactor loop into Twister
# http://www.tornadoweb.org/en/stable/twisted.html

# from tornado.platform.twisted import TwistedIOLoop
# from twisted.internet import reactor
# TwistedIOLoop().install()

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)


class ObeliskApplication(tornado.web.Application):

    def __init__(self):

        settings = dict(debug=True)

        self.client = obelisk.ObeliskOfLightClient('tcp://85.25.198.97:8081')

        handlers = [
            (r"/block/([^/]*)(?:/)?", BlockHeaderHandler), #/block/<block hash>
            (r"/block/([^/]*)/transactions(?:/)?", BlockTransactionsHandler), #/block/<block hash>/transactions
            (r"/tx(?:/)?", TransactionPoolHandler), #/tx/
            (r"/tx/([^/]*)(?:/)?", TransactionHandler), # /tx/<txid>
            (r"/address/([^/]*)(?:/)?", AddressHistoryHandler), #/address/<address>
            (r"/height(?:/)?", HeightHandler), #/height

            (r"/ws(?:/)?", ObWebsocket) #/ws
        ]

        tornado.web.Application.__init__(self, handlers, **settings)


class BlockHeaderHandler(tornado.web.RequestHandler):

    @asynchronous
    def get(self, blk_hash=None):
        if blk_hash is None:
            raise HTTPError(400, reason="No block hash")

        try:
            blk_hash = blk_hash.decode("hex")
        except ValueError:
            raise HTTPError(400, reason="Invalid hash")

        self.application.client.fetch_block_header(blk_hash ,self.on_fetch)

    def on_fetch(self, ec, header):
        block = {
            "version": header.version,
            "prev_hash": header.previous_block_hash.encode("hex"),
            "merkle": header.merkle.encode("hex"),
            "timestamp": header.timestamp,
            "bits": header.bits,
            "nonce": header.nonce
        }

        self.finish(json.dumps(block))


class BlockTransactionsHandler(tornado.web.RequestHandler):

    @asynchronous
    def get(self, blk_hash=None):
        if blk_hash is None:
            raise HTTPError(400, reason="No block hash")

        try:
            blk_hash = blk_hash.decode("hex")
        except ValueError:
            raise HTTPError(400, reason="Invalid hash")

        self.application.client.fetch_block_transaction_hashes(blk_hash ,self.on_fetch)

    def on_fetch(self, ec, tx_list):
        for i, tx_hash in enumerate(tx_list):
            tx_list[i] = tx_hash.encode("hex")

        self.finish(json.dumps({"transactions": tx_list}))


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

        self.application.client.fetch_transaction(tx_hash ,self.on_fetch)

    def on_fetch(self, ec, tx):

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

        self.finish(json.dumps(tx_dict))


class AddressHistoryHandler(tornado.web.RequestHandler):

    @asynchronous
    def get(self, address=None):
        if address is None:
            raise HTTPError(400, reason="No address")

        try:
            from_height = long(self.get_argument("from_height", 0))
        except:
            HTTPError(400)

        self.application.client.fetch_history(address, self.on_fetch, from_height=from_height)

    def on_fetch(self, ec, history):

        # Write in place as the address history can be very large and leads to memory exhaustion
        # This is currently pretty bad, it would be better to go to a lower frame level and stream the
        # data as we recieve it from upstream
        self.write('{ "history" : [')

        for i, row in enumerate(history):
            o_hash, o_index, o_height, value, s_hash, s_index, s_height = row

            row_dict = {
                "output_hash": o_hash.encode("hex"),
                "output_index": o_index,
                "output_height": o_height,
                "value": value,
                "spend_hash": s_hash.encode("hex"),
                "spend_index": s_index,
                "spend_height": s_height
            }

            self.write(json.dumps(row_dict))

            if i == len(history)-1:
                self.write('] }')
            else:
                self.write('], [')

            # Flush every 100 rows (~8.8 KB)
            if i % 100 == 0:
                self.flush()

        self.finish()


class HeightHandler(tornado.web.RequestHandler):

    @asynchronous
    def get(self):
        self.application.client.fetch_last_height(self.on_fetch)

    def on_fetch(self, ec, height):
        self.finish(str(height))

ioloop = tornado.ioloop.IOLoop.instance()
listeners = set() # set of WebsocketHandler
listen_lock = threading.Lock() # protects listeners

class ObWebsocket(tornado.websocket.WebSocketHandler):
    def open(self):
        with listen_lock:
            listeners.add(self)

    def on_message(self, message):
        try:
            request = json.loads(message)
        except:
            logging.error("Error decoding message: %s", message, exc_info=True)

        self.application.client.fetch_last_height(self.on_fetch)

        # if self.application.client.handle_request(self, request):
            # return
        # logging.warning("Unhandled command. Dropping request.")


    def on_fetch(self, ec, height):
        print "fetched ", height
        ioloop.add_callback(self.write_message, str(height))

    def on_close(self):
        with listen_lock:
            listeners.remove(self)

# Safely write through websocket using 
# tornado.ioloop.IOLoop.instance().add_callback(listeners[i].write_message, "Hi")
# Can probably handle subscriptions in python, avoids having to retransmit renew messages.

if __name__ == "__main__":
    application = ObeliskApplication()

    # Auto reload for testing.
    ioloop = tornado.ioloop.IOLoop.instance()
    tornado.autoreload.start(ioloop)

    application.listen(8888)
    tornado.ioloop.IOLoop.instance().start()

