# matrix-test
Matrix Py/JS test clients

## JavaScript client:

1. Install dependencies with `npm i`
2. Config ETH RPC address in config.json, it'll use the keys there, and try to interactively unlock the accounts. For Parity, make sure to have `--geth --ws-apis eth,net,web3,personal,parity` (for websockets) or `--geth --jsonrpc-apis eth,net,web3,personal,parity` (for http) in command line if you want it to unlock the account and sign the requests by itself. If `personal` API is not enabled or fail (wrong password, for example), it'll still works if you open Parity interface and confirm each signing request popping up there.
3. Start the server with `npm start`. It'll ask for the account (or use the one configured), register with the Matrix server, and start listening in the `3000` port (default), or configured one.
4. To send, e.g. a JSON signed message to the configured rooms, you can use in another terminal:
`curl -vL -H "Content-Type: application/json" -X POST -d '{"foo": "bar"}' http://localhost:3000/send`

## Python client:
1. Create a virtualenv (python3.6+) and install requirements.txt
2. Config ETH RPC as from JS client
3. Run `python main.py`, select and unlock account if desired
4. To send, e.g. a JSON signed message to the configured rooms, you can use in another terminal:
`curl -vL -H "Content-Type: application/json" -X POST -d '{"foo": "bar"}' http://localhost:3000/send`
