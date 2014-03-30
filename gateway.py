#!/usr/bin/env python

import logging
import tornado.options
import tornado.web
import tornado.websocket
import os.path
import obelisk
import json
import threading
import code

# Install Tornado reactor loop into Twister
# http://www.tornadoweb.org/en/stable/twisted.html
from tornado.platform.twisted import TwistedIOLoop
from twisted.internet import reactor
TwistedIOLoop().install()

from tornado.options import define, options

import rest_handlers
import obelisk_handler
import jsonchan
import broadcast
import ticker

define("port", default=8888, help="run on the given port", type=int)

global ioloop
ioloop = tornado.ioloop.IOLoop.instance()

class GatewayApplication(tornado.web.Application):

    def __init__(self, service):

        settings = dict(debug=True)

        client = obelisk.ObeliskOfLightClient(service)
        self.obelisk_handler = obelisk_handler.ObeliskHandler(client)
        self.brc_handler = broadcast.BroadcastHandler()
        self.json_chan_handler = jsonchan.JsonChanHandler()
        self.ticker_handler = ticker.TickerHandler()

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
        self._brc_handler = self.application.brc_handler
        self._json_chan_handler = self.application.json_chan_handler
        self._ticker_handler = self.application.ticker_handler

    def open(self):
        logging.info("OPEN")
        with QuerySocketHandler.listen_lock:
            self.listeners.add(self)

    def on_close(self):
        logging.info("CLOSE")
        with QuerySocketHandler.listen_lock:
            self.listeners.remove(self)

    def _check_request(self, request):
        return request.has_key("command") and request.has_key("id") and \
            request.has_key("params") and type(request["params"]) == list

    def on_message(self, message):
        try:
            request = json.loads(message)
        except:
            logging.error("Error decoding message: %s", message, exc_info=True)
        logging.info("Request: %s", request)
        # Check request is correctly formed.
        if not self._check_request(request):
            logging.error("Malformed request: %s", request, exc_info=True)
            return
        # Try different handlers until one accepts request and
        # processes it.
        if self._json_chan_handler.handle_request(self, request):
            return
        if self._obelisk_handler.handle_request(self, request):
            return
        if self._brc_handler.handle_request(self, request):
            return
        if self._ticker_handler.handle_request(self, request):
            return
        logging.warning("Unhandled command. Dropping request: %s",
            request, exc_info=True)

    def _send_response(self, response):
        try:
            self.write_message(json.dumps(response))
        except tornado.websocket.WebSocketClosedError:
            logging.warning("Dropping response to closed socket: %s",
               response, exc_info=True)

    def queue_response(self, response):
        try:
            # calling write_message or the socket is not thread safe
            ioloop.add_callback(self._send_response, response)
        except:
            logging.error("Error adding callback", exc_info=True)

class DebugConsole(threading.Thread):

    daemon = True

    def __init__(self, application):
        self.application = application
        super(DebugConsole, self).__init__()
        self.start()

    def run(self):
        console = code.InteractiveConsole()
        code.interact(local=dict(globals(), **locals()))

def main(service):
    application = GatewayApplication(service)
    tornado.autoreload.start(ioloop)
    application.listen(8888)
    debug_console = DebugConsole(application)
    reactor.run()

if __name__ == "__main__":
    service = "tcp://127.0.0.1:9091"
    main(service)

