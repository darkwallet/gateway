import time
import math
import logging

VALID_SECTIONS = ['b', 'coinjoin', 'tmp', 'chat']
MAX_THREADS = 2000
MAX_DATA_SIZE = 20000

class DataTooBigError(Exception):
    def __str__(self):
        return  "Data is too big"
class InvalidSectionError(Exception):
    def __str__(self):
        return "Invalid section, valid are: " + ", ".join(VALID_SECTIONS)
class MissingThread(Exception):
    def __str__(self):
        return "Thread doesnt exist"
class IncorrectThreadId(Exception):
    def __str__(self):
        return "Thread id must be alphanumeric"

class JsonChanSection(object):
    max_threads = MAX_THREADS
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
        if len(data) > MAX_DATA_SIZE:
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
        if thread_id in self._threads:
            return self._threads[thread_id]
        raise MissingThread()

    def get_threads(self):
        return self._threads.keys()

class JsonChan(object):
    def __init__(self):
        self._sections = {}

    def post(self, section_name, thread_id, data):
        section = self.get_section(section_name)
        return section.post(thread_id, data)

    def get_threads(self, section_name):
        section = self.get_section(section_name)
        return section.get_threads()

    def get_section(self, name):
        if not name in self._sections:
            if name in VALID_SECTIONS:
                self._sections[name] = JsonChanSection(name)
            else:
                raise InvalidSectionError()
        return self._sections[name]

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
    def process(self, params):
        self._json_chan.post(params[0], params[1], params[2])
        self.process_response(None, {'result': 'ok', 'method': 'post'})

class ObJsonChanList(JsonChanHandlerBase):
    def process(self, params):
        threads = self._json_chan.get_threads(params[0])
        self.process_response(None, {'result': 'ok', 'method': 'list', 'threads': threads})

class ObJsonChanGet(JsonChanHandlerBase):
    def process(self, params):
        thread = self._json_chan.get_section(params[0]).get_thread(params[1])
        self.process_response(None, {'result': 'ok', 'method': 'get', 'thread': thread})


class JsonChanHandler:

    handlers = {
        "chan_post":                ObJsonChanPost,
        "chan_list":                ObJsonChanList,
        "chan_get":                 ObJsonChanGet
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
        try:
            handler.process(params)
        except Exception as e:
            handler.process_response(str(e), {})
        return True

if __name__ == '__main__':
    site = JsonChan()
    first_thread = site.post('b', 'first', "fooo!")
    for idx1 in xrange(1000):
        site.post('b', 'first', "more!")
        for idx2 in xrange(100):
            site.post('b', 'myid'+str(idx1)+'x'+str(idx2), "{'a': 'b'}")
    print len(site.get_section('b').get_threads()), site.get_section('b').get_thread('first')
