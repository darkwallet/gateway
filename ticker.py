import threading
import urllib2
import json
import time

class Ticker(threading.Thread):

    daemon = True

    currencies = (
        "EUR",
        "USD"
    )

    def __init__(self):
        super(Ticker, self).__init__()
        self.lock = threading.Lock()
        self.ticker = {}
        self.start()

    def run(self):
        while True:
            self.pull_prices()
            time.sleep(5 * 60)

    def pull_prices(self):
        for currency in Ticker.currencies:
            self.query_ticker(currency)

    def query_ticker(self, currency):
        url = "https://api.bitcoinaverage.com/ticker/global/%s" % currency
        try:
            f = urllib2.urlopen(url)
        except HTTPError:
            return
        ticker_values = json.loads(f.read())
        with self.lock:
            self.ticker[currency] = ticker_values

    def fetch(self, currency):
        with self.lock:
            try:
                return self.ticker[currency]
            except KeyError:
                return None

class TickerHandler:

    def __init__(self):
        self._ticker = Ticker()

    def handle_request(self, socket_handler, request):
        if request["command"] != "fetch_ticker":
            return False
        if not request["params"]:
            logging.error("No param for ticker specified.")
            return True
        currency = request["params"][0]
        ticker_value = self._ticker.fetch(currency)
        response = {
            "id": request["id"],
            "error": None,
            "result": [ticker_value]
        }
        socket_handler.queue_response(response)
        return True

