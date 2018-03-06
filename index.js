const fs = require('fs'),
      path = require('path'),
      nconf = require('nconf'),
      Web3 = require('web3'),
      MatrixSdk = require('matrix-js-sdk'),
      read = require('read'),
      express = require('express'),
      bodyParser = require('body-parser');

// initializers
nconf.argv()
  .env({ separator: '__', lowerCase: true })
  .file({ file: 'config.json' });

let matrix;
const web3 = new Web3(nconf.get('eth:endpoint'));
const app = express();

app.use(bodyParser.json());


// helpers / utilities
function asyncMiddleware(fn) {
  return (req, res, next) => {
    const routePromise = fn(req, res, next);
    if (routePromise.catch) {
      routePromise.catch(err => next(err));
    }
  };
}


// express routes
app.post('/send', asyncMiddleware(async (req, res) => {
  let msg = JSON.stringify(req.body);
  const sig = await web3.eth.sign(msg+'\n'+matrix.getUserId(), web3.eth.defaultAccount);
  for (let room of matrix.getRooms()) {
    await matrix.sendTextMessage(room.roomId, msg+'\n'+sig);
  }
  return res.send([web3.eth.defaultAccount, matrix.getUserId(), sig].join('\n'));
}));


// init functions
async function initMatrix(acc) {
  let user = nconf.get(`matrix:user:${acc}`);
  if (!user) {
    matrix = MatrixSdk.createClient(nconf.get('matrix:server'));
    // password is last 16 characters of signature of 'password' by account
    const password = (await web3.eth.sign('password', acc)).slice(-16);
    let username, i = 0;
    while (!username) {
      if (i >= 5)
        throw new Error('Could not register or login!');
      username = acc.toLowerCase();
      if (i++)
        username += `.${i}`;

      try {
        if (await matrix.isUsernameAvailable(username).catch(() => false)) {
          user = await matrix.register(username, password, undefined, { type: "m.login.dummy" });
          console.log('REGISTER', username, password, user, matrix.getAccessToken());
        } else {
          user = await matrix.loginWithPassword(username, password);
          console.log('LOGIN', username, password, user, matrix.getAccessToken());
        }
        if (!user.access_token) {
          throw new Error('Could not find accessToken');
        }
        matrix = MatrixSdk.createClient({
          baseUrl: nconf.get('matrix:server'),
          userId: user.user_id,
          accessToken: user.access_token,
        });
        nconf.set(`matrix:user:${acc}`, user);
        nconf.save();
        break;
      } catch (err) {
        console.warn('Error trying user:', username, password, err);
        username = null;
      }
    }
  } else {
    matrix = MatrixSdk.createClient({
      baseUrl: nconf.get('matrix:server'),
      userId: user.user_id,
      accessToken: user.access_token,
    });
  }
  console.log('LOGGED', matrix.getUserId());
  matrix.setDisplayName(await web3.eth.sign(matrix.getUserId(), web3.eth.defaultAccount));

  // events handlers
  matrix.on("RoomMember.membership", (event, member) => {
    if (member.membership === "invite" && member.userId === myUserId) {
      matrix.joinRoom(member.roomId)
        .done(() => console.log("Auto-joined %s", member.roomId));
    }
  });

  matrix.on("Room.timeline", function(event, room, toStartOfTimeline) {
    if (toStartOfTimeline) {
        return; // don't print paginated results
    }
    if (event.getType() !== "m.room.message") {
        return; // only print messages
    }
    try {
      let body = event.getContent().body,
          lastn = body.lastIndexOf('\n'),
          msg = body.substr(0, lastn),
          sig = body.substr(lastn + 1),
          senderAddr = web3.eth.accounts.recover(msg+'\n'+event.getSender(), sig),
          isValid = event.getSender().toLowerCase().includes(senderAddr.toLowerCase());
      if (isValid) {
        console.log("VALID SIGNATURE: [%s]{%s} => '%s'", event.getSender(), senderAddr, msg);
      }
    } catch (err) {
    }
  });

  let syncedPromise = new Promise((resolve) =>
    matrix.on('sync', function listener(state, prevState, data) {
      if (state !== 'PREPARED') return;
      matrix.removeListener('sync', listener);
      resolve();
      console.log('synced!');
    }));

  for (let room of nconf.get('matrix:rooms')) {
    let roomInfo = await matrix.getRoomIdForAlias(room);
    await matrix.joinRoom(roomInfo.room_id)
    console.log('Join room', room);
    setInterval(() => matrix.sendTyping(roomInfo.room_id, true, 1e3), 5e3);
  }

  matrix.startClient();
  await syncedPromise;
}


// main start method
async function main() {
  let acc = nconf.get('eth:account'),
      pw = nconf.get('eth:password');
  const accounts = await web3.eth.getAccounts();
  if (!(accounts.length > 0)) {
    throw new Error('No accounts found in eth node');
  } else if (!acc) {
    console.log('Please, type account index to be used:');
    for (let i=0; i<accounts.length; i++)
      console.log('  [%s] %s', i, accounts[i]);
    acc = await new Promise((resolve, reject) =>
      read({ prompt: "ETH Account: " }, (err, res) =>
        err ? reject(err) :
        (res != +res || +res < 0 || +res >= accounts.length) ? reject(new Error('Invalid index')) :
        resolve(accounts[+res])));
  } else if (accounts.indexOf(acc) < 0) {
    throw new Error('Configured account not found');
  }
  web3.eth.defaultAccount = acc;

  try {
    // config[eth:password] === false => ask password
    if (pw === false) {
      pw = await new Promise((resolve, reject) =>
        read({ prompt: "ETH Key Password: ", silent: true, replace: "*" }, (err, res) =>
          err ? reject(err) : resolve(res)));
    }
    if (typeof pw === 'string')
      console.log('Unlocked:', await web3.eth.personal.unlockAccount(acc, pw));
  } catch (err) {
    console.warn('Failed to unlock account. Per-request approval will be used.');
  }

  await initMatrix(acc);

  const port = nconf.get('server:port'),
        host = nconf.get('server:host');
  await new Promise((resolve, reject) =>
    app.listen(
      port,
      host,
      resolve
    ).once('error', reject));
  console.log('Listening on http://%s:%s/', host, port);
}


// call async main
main()
  .catch((err) => ( console.error('FATAL:', err), process.exit() ));
