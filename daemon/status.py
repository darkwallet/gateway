import json
import tornado.web

class StatusHandler(tornado.web.RequestHandler):
    def __init__(self, *args, **kwargs):
        tornado.web.RequestHandler.__init__(self, *args)
        self.app = kwargs['app']
    def get(self):
        stats = {
            'brc': self.app.brc_handler._brc.last_nodes,
            'radar': self.app.brc_handler._radar.radar_hosts,
        }
        self.write(json.dumps(stats))


