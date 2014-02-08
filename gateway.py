#!/usr/bin/env python

import logging
import tornado.options
import tornado.web
import tornado.websocket
import os.path
import obelisk
import json
import threading

# Install Tornado reactor loop into Twister
# http://www.tornadoweb.org/en/stable/twisted.html
from tornado.platform.twisted import TwistedIOLoop
from twisted.internet import reactor
TwistedIOLoop().install()

from tornado.options import define, options

import rest_handlers
import obelisk_handler

define("port", default=8888, help="run on the given port", type=int)

global ioloop
ioloop = tornado.ioloop.IOLoop.instance()

class ObeliskApplication(tornado.web.Application):

    def __init__(self, service):

        settings = dict(debug=True)

        client = obelisk.ObeliskOfLightClient(service)
        self.obelisk_handler = obelisk_handler.ObeliskHandler(client)

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
        self._obelisk_handler = self.application.obelisk_handler

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

def main(service):
    application = ObeliskApplication(service)

    tornado.autoreload.start(ioloop)

    application.listen(8888)
    reactor.run()

if __name__ == "__main__":
    service = "tcp://85.25.198.97:9091"
    main(service)

