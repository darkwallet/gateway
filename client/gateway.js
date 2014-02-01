/**
 * Client to connect to a darkwallet gateway.
 *
 * @param {String}   connect_uri Gateway websocket URI
 * @param {Function} handle_connect Callback to run when connected
 */
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
        self._on_message(evt);
    };
}

/**
 * Get last height
 *
 * @param {Function} handle_fetch Callback to handle the returned height
 */
GatewayClient.prototype.fetch_last_height = function(handle_fetch) {
    GatewayClient._checkFunction(handle_fetch);

    this.make_request("fetch_last_height", [], function(response) {
        handle_fetch(response["error"], response["result"][0]);
    });
};

/**
 * Fetch transaction
 *
 * @param {String}   tx_hash Transaction identifier hash
 * @param {Function} handle_fetch Callback to handle the JSON object representing
 * the transaction 
 */
GatewayClient.prototype.fetch_transaction = function(tx_hash, handle_fetch) {
    GatewayClient._checkFunction(handle_fetch);

    this.make_request("fetch_transaction", [tx_hash], function(response) {
        handle_fetch(response["error"], response["result"][0]);
    });
};

/**
 * Fetch history
 *
 * @param {String}   address
 * @param {Function} handle_fetch Callback to handle the JSON object representing
 * the history of the address
 */
GatewayClient.prototype.fetch_history = function(address, handle_fetch) {
    GatewayClient._checkFunction(handle_fetch);

    this.make_request("fetch_history", [address], function(response) {
        handle_fetch(response["error"], response["result"][0]);
    });
};

/**
 * Make requests to the server
 *
 * @param {String} command
 * @param {Array} params
 * @param {Function} handler 
 */
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

/**
 * Close event handler
 *
 * @param {Object} evt event
 */
GatewayClient.prototype.on_close = function(evt) {
};

/**
 * Error event handler
 *
 * @param {Object} evt event
 *
 * @throws {Object}
 */
GatewayClient.prototype.on_error = function(evt) {
    throw evt;
};

/**
 * After triggering message event, calls to the handler of the petition
 *
 * @param {Object} evt event
 * @private
 */
GatewayClient.prototype._on_message = function(evt) {
    this.on_message(evt)
    var response = JSON.parse(evt.data);
    var id = response["id"];
    var handler = this.handler_map[id];
    handler(response);
};

/**
 * Message event handler
 *
 * @param {Object} evt event
 */
GatewayClient.prototype.on_message = function(evt) {
}

/**
 * (Pseudo-)Random integer generator
 *
 * @return {Number} Random integer
 * @private
 */
GatewayClient._random_integer = function() {
    return Math.floor((Math.random() * 4294967296)); 
};

/**
 * Checks if param can be executed
 *
 * @param {Function} Function to be checked
 *
 * @throws {String} Parameter is not a function
 * @protected
 */
GatewayClient._checkFunction = function(func) {
    if (typeof func !== 'function') {
        throw "Parameter is not a function";
    }
};

