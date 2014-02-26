import time
import math

class DataTooBigError(Exception):
    def __str__(self):
        print "Data is too big"
class IncorrectThreadId(Exception):
    def __str__(self):
        print "Thread id must be alphanumeric"

class JsonChanSection(object):
    max_threads = 200
    def __init__(self, name):
        self._name = name
        self._threads = {}

    def find_last_thread(self):
        sel_thread_id = self._threads.keys()[0]
        first_thread = self._threads[sel_thread_id]
        timestamp = first_thread['timestamp']
        for thread_id, thread in self._threads.iteritems():
            if thread['timestamp'] < timestamp:
                timestamp = thread['timestamp']
                sel_thread_id = thread_id
        return sel_thread_id

    def purge_threads(self):
        while len(self._threads) > self.max_threads:
            last_thread = self.find_last_thread()
            try:
                self._threads.pop(last_thread)
            except KeyError:
                pass # already deleted

    def post(self, thread_id, data):
        if len(data) > 4000:
            raise DataTooBigError()
        if not thread_id.isalnum():
            raise IncorrectThreadId()
        if thread_id in self._threads:
            thread = self._threads[thread_id]
            thread['posts'].append(data)
            thread['timestamp'] = time.time()
        else:
            thread = {'timestamp': time.time(), 'posts': [data]}
            self._threads[thread_id] = thread
        self.purge_threads()
        return thread

    def get_thread(self, thread_id):
        return self._threads[thread_id]

    def get_threads(self):
        return self._threads.keys()

class JsonChan(object):
    def __init__(self):
        self._subsections = {}

    def post(self, section_name, thread_id, data):
        section = self.get_section(section_name)
        return section.post(thread_id, data)

    def get_threads(self, section_name):
        section = self.get_section(section_name)
        return section.get_threads()

    def get_section(self, name):
        if not name in self._subsections:
            self._subsections[name] = JsonChanSection(name)
        return self._subsections[name]

class JsonChanHandlerBase(object):

    def __init__(self, handler, request_id, json_chan):
        self._handler = handler
        self._request_id = request_id
        self._json_chan = json_chan

    def process_response(self, error, raw_result):
        assert error is None or type(error) == str
        result = self.translate_response(raw_result)
        response = {
            "id": self._request_id,
            "result": result
        }
        if error:
            response["error"] = error
        self._handler.queue_response(response)

    def process(self, params):
        print "process jsonchan req", self._json_chan
        self.process_response(None, {'result': 'ok'})

    def translate_arguments(self, params):
        return params

    def translate_response(self, result):
        return result

class ObJsonChanPost(JsonChanHandlerBase):

    def translate_arguments(self, params):
        check_params_length(params, 1)
        tx_hash = decode_hash(params[0])
        return (tx_hash,)

    def translate_response(self, result):
        assert len(result) == 1
        tx = result[0].encode("hex")
        return (tx,)


class JsonChanHandler:

    handlers = {
        "chan_post":                ObJsonChanPost,
        "chan_list":                ObJsonChanPost,
        "chan_get":                 ObJsonChanPost
    }

    def __init__(self):
        self._json_chan = JsonChan()

    def handle_request(self, socket_handler, request):
        command = request["command"]
        if command not in self.handlers:
            return False
        params = request["params"]
        # Create callback handler to write response to the socket.
        handler = self.handlers[command](socket_handler, request["id"], self._json_chan)
        try:
            params = handler.translate_arguments(params)
        except Exception as exc:
            logging.error("Bad parameters specified: %s", exc, exc_info=True)
            return True
        handler.process(params)
        return True

if __name__ == '__main__':
    site = JsonChan()
    first_thread = site.post('b', 'first', "fooo!")
    for idx1 in xrange(1000):
        site.post('b', 'first', "more!")
        for idx2 in xrange(100):
            site.post('b', 'myid'+str(idx1)+'x'+str(idx2), "{'a': 'b'}")
    print len(site.get_section('b').get_threads()), site.get_section('b').get_thread('first')
