from hodl_net.models import *
from hodl_net.server import peer, protocol, server, session, call_from_thread
from hodl_net.database import db_worker
import sqlalchemy.exc


@server.handle('share', 'request')
@db_worker.with_session
async def share_peers(_):
    peers = [_peer.dump() for _peer in session.query(Peer).all() if not _peer.local]
    users = [_user.dump() for _user in session.query(User).all()]
    peer.request(Message(
        name='share_info',
        data={
            'users': users,
            'peers': peers
        }
    ))


@server.handle('new_user', 'shout')
@db_worker.with_session
async def record_new_user(message):
    data = message.data
    new_user = session.query(User).filter_by(name=name).first()
    if not new_user:
        new_user = User(protocol, public_key=data['key'], name=data['name'])
        session.add(new_user)
        session.commit()
        protocol.send_all(Message(
            name='new_user',
            data=new_user.dump()
        ))


@server.handle('share_info', 'request')
@db_worker.with_session
async def record_peers(message):
    for data in message.data['peers']:
        if not session.query(Peer).filter_by(addr=data['address']).first():
            try:
                new_peer = Peer(protocol, addr=data['address'])
                session.add(new_peer)  # TODO: test new peers
            except sqlalchemy.exc.IntegrityError as e:
                log.warning("Fail on peer adding. Probably already exists. More info:")
                log.debug(e)

    for data in message.data['users']:
        if not session.query(User).filter_by(name=data['name']):
            new_user = Peer(protocol, public_key=data['key'], name=data['name'])
            session.add(new_user)
    call_from_thread(session.commit)


@server.handle('ping', 'request')
async def ping(_):
    pass


@server.handle('echo', 'request')
async def echo(message):
    peer.response(message, Message('echo_resp', {
        'msg': message.data['msg']
    }))


if __name__ == '__main__':
    server.run()
