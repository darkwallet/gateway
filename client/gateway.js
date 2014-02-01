function GatewayClient(connect_uri, handle_connect) {
    var self = this;
    this.handler_map = {};
    this.websocket = new WebSocket(connect_uri);
    this.websocket.onopen = function(evt) {
        handle_connect();
    };
    this.websocket.onclose = function(evt) {
        self.on_close(evt);
    };
    this.websocket.onerror = function(evt) {
        self.on_error(evt);
    };
    this.websocket.onmessage = function(evt) {
        self.on_message(evt);
    };
}

GatewayClient.prototype.fetch_last_height = function(handle_fetch) {
    GatewayClient._checkFunction(handle_fetch);

    this.make_request("fetch_last_height", [], function(response) {
        handle_fetch(response["error"], response["result"][0]);
    });
};

GatewayClient.prototype.fetch_transaction = function(tx_hash, handle_fetch) {
    GatewayClient._checkFunction(handle_fetch);

    this.make_request("fetch_transaction", [tx_hash], function(response) {
        handle_fetch(response["error"], response["result"][0]);
    });
};

GatewayClient.prototype.fetch_history = function(address, handle_fetch) {
    GatewayClient._checkFunction(handle_fetch);

    this.make_request("fetch_history", [address], function(response) {
        handle_fetch(response["error"], response["result"][0]);
    });
};

GatewayClient.prototype.make_request = function(command, params, handler) {
    GatewayClient._checkFunction(handler);

    var id = GatewayClient._random_integer();
    var request = {
        "id": id,
        "command": command,
        "params": params
    };
    var message = JSON.stringify(request);
    this.websocket.send(message);
    this.handler_map[id] = handler;
};

GatewayClient.prototype.on_close = function(evt) {
};

GatewayClient.prototype.on_error = function(evt) {
    throw evt;
};

GatewayClient.prototype.on_message = function(evt) {
    var response = JSON.parse(evt.data);
    var id = response["id"];
    var handler = this.handler_map[id];
    handler(response);
};

GatewayClient._random_integer = function() {
    return Math.floor((Math.random() * 4294967296)); 
};

GatewayClient._checkFunction = function(func) {
    if (typeof func !== 'function') {
        throw "Parameter is not a function";
    }
};

