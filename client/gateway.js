function GatewayClient(connect_uri, handle_connect)
{
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

GatewayClient.prototype.on_close = function(evt)
{
    write_to_screen("DISCONNECTED");
}
GatewayClient.prototype.on_error = function(evt)
{
    write_to_screen('<span style="color: red;">ERROR:</span> ' + evt.data);
}
GatewayClient.prototype.on_message = function(evt)
{
    response = JSON.parse(evt.data);
    id = response["id"];
    handler = this.handler_map[id];
    handler(response);
}

function random_integer()
{
    return Math.floor((Math.random() * 4294967296)); 
}

GatewayClient.prototype.fetch_last_height = function(handle_fetch)
{
    id = random_integer();
    var request = {
        "id": id,
        "command": "fetch_last_height",
        "params": []
    };
    message = JSON.stringify(request);
    write_to_screen("SENT: " + message); 
    this.websocket.send(message);
    this.handler_map[id] = function(response) {
        handle_fetch(response["error"], response["result"][0]);
    };
}

GatewayClient.prototype.fetch_transaction = function(tx_hash, handle_fetch)
{
    id = random_integer();
    var request = {
        "id": id,
        "command": "fetch_transaction",
        "params": [tx_hash]
    };
    message = JSON.stringify(request);
    write_to_screen("SENT: " + message); 
    this.websocket.send(message);
    this.handler_map[id] = function(response) {
        handle_fetch(response["error"], response["result"][0]);
    };
}

GatewayClient.prototype.fetch_history = function(address, handle_fetch)
{
    id = random_integer();
    var request = {
        "id": id,
        "command": "fetch_history",
        "params": [address]
    };
    message = JSON.stringify(request);
    write_to_screen("SENT: " + message); 
    this.websocket.send(message);
    this.handler_map[id] = function(response) {
        handle_fetch(response["error"], response["result"][0]);
    };
}

