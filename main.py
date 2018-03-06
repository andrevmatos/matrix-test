from gevent import monkey
monkey.patch_all()
import gevent
import gevent.wsgi

import logging
import getpass
import json
import socket

from matrix_client.errors import MatrixRequestError
from web3 import Web3, HTTPProvider
from flask import Flask, request

from gmatrixclient import GMatrixClient
from utils import Config

log = logging.getLogger(__name__)
socket.setdefaulttimeout(600)


class RaidenMatrix:
    def __init__(self, web3: Web3, config: Config):
        self.web3 = web3
        self.config = config
        self.account = None
        self.app = None

    def init_matrix(self, account: str):
        self.account = account
        user = self.config['matrix:user'].get(self.account)
        if not user:
            self.client = GMatrixClient(self.config['matrix:server'])
            password = self.web3.eth.sign(self.account, text='password').hex()[-16:]
            username = None
            i = 0
            while not username:
                assert i < 5, 'Could not register or login!'
                username = self.account.lower()
                if i:
                    username += '.%d' % (i,)
                i += 1

                try:
                    token = self.client.login_with_password(username, password)
                    log.info(
                        'LOGIN: %r => %r',
                        (username, password),
                        token,
                    )
                except MatrixRequestError as e:
                    if e.code != 403:
                        raise
                    log.debug(
                        'Could not login. Trying register: %r',
                        (username, password),
                        exc_info=True
                    )
                    try:
                        token = self.client.register_with_password(username, password)
                        log.info(
                            'REGISTER: %r => %r',
                            (username, password),
                            token,
                        )
                    except MatrixRequestError as e:
                        if e.code != 400:
                            raise
                        log.debug('Username taken. Continuing', exc_info=True)
                        username = None
                        continue

            user = {
                'user_id': self.client.user_id,
                'access_token': self.client.token,
                'home_server': self.client.hs,
            }
            self.config['matrix:user:' + self.account] = user
            self.config.save()
        else:
            self.client = GMatrixClient(
                self.config['matrix:server'],
                user_id=user['user_id'],
                token=user['access_token'],
            )

        name = self.web3.eth.sign(self.account, text=user['user_id']).hex()
        self.client.api.set_display_name(user['user_id'], name)

        for alias in self.config['matrix:rooms']:
            self.client.join_room(alias)

        for room_id, room in self.client.get_rooms().items():
            room.update_aliases()
            if not room.canonical_alias and room.aliases:
                room.canonical_alias = room.aliases[0]
            room.add_listener(self.handle_message)
            log.debug(
                'ROOM: %r => %r',
                room_id,
                room.aliases
            )

        self.client.start_listener_thread()  # greenlet "thread"

    def handle_message(self, room, event):
        if event['type'] != 'm.room.message' or event['content']['msgtype'] != 'm.text':
            return
        msg, sig = event['content']['body'].rsplit('\n', 1)
        sender = event['sender']
        addr = self.web3.eth.account.recoverMessage(text=msg + '\n' + sender, signature=sig)
        if addr.lower() not in sender:
            return
        log.info("VALID SIGNATURE: [%s]{%s} => '%s'", sender, addr, msg)

    def run(self):
        self.app = Flask('raiden')
        self.app.add_url_rule(
            '/send',
            '/send',
            view_func=self._send,
            methods=('POST',)
        )
        self.app.add_url_rule(
            '/block',
            '/block',
            view_func=lambda: str(self.web3.eth.blockNumber),
            methods=('GET',)
        )
        server = gevent.wsgi.WSGIServer(
            (self.config['server:host'], self.config['server:port']),
            self.app,
            log=log,
            error_log=log,
        )
        log.info(
            'Listening on http://%s:%s',
            self.config['server:host'],
            self.config['server:port']
        )
        server.serve_forever()

    def _send(self):
        data = request.get_json()
        msg = json.dumps(data)
        sig = self.web3.eth.sign(self.account, text=msg + '\n' + self.client.user_id).hex()
        for room in self.client.get_rooms().values():
            log.info('_SEND: %r => %r', msg, sig)
            room.send_text(msg + '\n' + sig)
        return '\n'.join([self.account, self.client.user_id, sig])


def main():
    config = Config('config.json')

    web3 = Web3(HTTPProvider(config['eth:endpoint']))
    accounts = web3.eth.accounts
    assert accounts, 'No accounts found in eth node'

    acc, pw = config['eth'].get('account'), config['eth'].get('password')

    if not acc:
        print('Please, type account index to be used:')
        for a in enumerate(accounts):
            print('  [%s] %s' % a)
        acc = input('ETH Account: ')
        assert acc and acc.isdigit() and 0 <= int(acc) < len(accounts), 'Invalid index'
        acc = accounts[int(acc)]
    else:
        assert acc in accounts, 'Configured account not found'

    web3.eth.defaultAccount = acc

    try:
        if pw is False:
            pw = getpass.getpass('ETH Key Password: ')
        if isinstance(pw, str):
            assert web3.personal.unlockAccount(acc, pw)
            log.info('Unlocked: %s', acc)
    except:
        log.warning('Failed to unlock account. Per-request approval will be used.', exc_info=True)

    raiden = RaidenMatrix(web3, config)
    raiden.init_matrix(acc)
    raiden.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    main()
