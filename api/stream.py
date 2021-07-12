import json

import websocket


def send(ws, msg):
    o = json.dumps(msg)
    print(f"> {str(o)}")
    ws.send(o)


def send_pong(ws):
    sub = dict(op="pong")
    send(ws, sub)


def on_error(ws, error):
    print(error)


def on_close(ws):
    print("### closed ###")


def on_message(ws, message):
    content = json.loads(message)
    m = content['m']
    if m == 'depth':
        print(content)
    elif m == "ping":
        send_pong(ws)
    else:
        print(f"ignore message {m}")




url = "wss://api-test.ascendex-sandbox.io:443/api/pro/v2/stream"


ws = websocket.WebSocketApp(
    url,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

ws.run_forever()
