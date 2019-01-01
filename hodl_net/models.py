# TODO: docstring

from hodl_net.cryptogr import get_random, verify, sign, encrypt, decrypt
from sqlalchemy import Column, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import TypeVar, List, Any, Dict
from threading import RLock
from .errors import *
import logging
import uuid
import attr
import time
import json
import os

log = logging.getLogger(__name__)

Base = declarative_base()
lock = RLock()

T = TypeVar('T', int, str)
S = TypeVar('S', str, List[str])

with open('net2/config.json') as _fp:
    Configs = type('Configs', (object,), json.load(_fp))

engine = create_engine(f'sqlite:///db/{Configs.name}_db.sqlite', echo=False,
                       connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine)
session = Session()


class TempStructure:
    update_time = 5
    expire = 60

    def __init__(self):
        self.last_check = time.time()


class TempDict(dict, TempStructure):
    def __init__(self, *args, factory=list):
        dict.__init__(self, *args)
        TempStructure.__init__(self)
        self.factory = factory

    def __setitem__(self, key: T, value: Any):
        self.check()
        super().__setitem__(key, {
            'time': time.time(),
            'value': value
        })

    def __getitem__(self, key: T):
        self.check()
        if key not in self and self.factory:
            value = self.factory()
            self[key] = value
            return value
        return super().__getitem__(key)['value']

    def check(self):
        if time.time() - self.last_check < self.update_time:
            return
        for key, value in self.copy().items():
            if time.time() - value['time'] >= self.expire:
                del self[key]


@attr.s
class Message:
    """Message"""
    name = attr.ib(type=str)
    data = attr.ib(factory=dict)
    salt = attr.ib(type=str)
    callback = attr.ib(factory=lambda: str(uuid.uuid4()))

    @salt.default
    def _salt_gen(self):
        return get_random()

    @data.validator
    @name.validator
    def _check_type(self, attribute, value):
        if attribute.name == 'name' and not isinstance(value, str) or \
                attribute.name == 'data' and not isinstance(value, dict):
            raise BadRequest

    def dump(self):
        return attr.asdict(self)

    def to_json(self):
        return json.dumps(self.dump())

    @classmethod
    def from_json(cls, data):
        return cls(**json.loads(data))


@attr.s
class MessageWrapper:
    """Wrapper for message"""
    message = attr.ib(type=Message, default=None)
    type = attr.ib(type=str, default='message')
    sender = attr.ib(type=str, default=None)
    encoding = attr.ib(default='json')
    id = attr.ib(type=str)
    sign = attr.ib(type=str, default=None)
    tunnel_id = attr.ib(type=str, default=None)

    acceptable_types = ['message', 'request', 'shout']
    acceptable_encodings = ['json']

    @id.default
    def _id_gen(self):
        return str(uuid.uuid4())

    @classmethod
    def from_bytes(cls, wrapper: bytes) -> 'MessageWrapper':
        """
        Decrypts bytes to `MessageWrapper`. Can raise `BadRequest` exception
        """
        try:
            wrapper = json.loads(wrapper.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            raise BadRequest
        message_type = wrapper.get('type')
        if not message_type or message_type not in cls.acceptable_types:
            raise BadRequest('Wrong message type')
        sender = wrapper.get('sender')
        if message_type != 'request' and (not sender or
                                          not isinstance(sender, str)):
            raise BadRequest('Sender name required')

        message = wrapper.get('message')
        if not message:
            raise BadRequest('Message required')
        if isinstance(message, dict):
            message = Message(**message)
        encoding = wrapper.get('encoding')
        if encoding not in cls.acceptable_encodings:
            raise BadRequest('Bad encoding')
        uid = wrapper.get('id')
        if not uid or not isinstance(uid, str):
            raise BadRequest('Id required')
        signature = wrapper.get('sign')
        if message_type != 'request' and (not signature or
                                          not isinstance(signature, str)):
            raise BadRequest('Sign required')
        tunnel_id = wrapper.get('tunnel_id')
        if tunnel_id and not isinstance(tunnel_id, str):
            raise BadRequest('Wrong metadata')

        wrapper = cls(
            message,
            message_type,
            sender,
            encoding,
            uid,
            signature,
            tunnel_id
        )
        return wrapper

    def encrypt(self, public_key: str):
        """
        Encrypt wrapper with message inside (`self.message` type must be `Message`)
        """
        return encrypt(self.message.to_json(), public_key)

    def decrypt(self, private_key: str):
        """
        Decrypt `Message` from string (`self.message type must be `str`)
        """
        self.message = json.loads(decrypt(self.message, private_key))

    def create_sign(self, private_key: str):
        self.sign = sign(self.message.to_json(), private_key)

    def verify(self, public_key: str):
        """
        Verify message in wrapper
        """
        if self.type == 'request':
            return
        if not verify(self.message.to_json(), self.sign, public_key):
            raise VerificationFailed('Bad sign')

    def prepare(self, private_key: str = None, public_key: str = None):
        """
        Prepare wrapper for send
        """
        assert self.type != 'request' or not self.sender
        if private_key and self.type != 'request':
            self.sign = sign(self.message.to_json(), private_key)
            self.message: Message = self.encrypt(public_key)

    def to_json(self):
        return json.dumps(attr.asdict(self))


class Peer(Base):
    __tablename__ = 'peers'

    addr = Column(String, primary_key=True)

    def __init__(self, proto, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.proto = proto

    def copy(self):
        return self

    def send(self, wrapper: MessageWrapper):
        """
        Send prepared Message with wrapper to peer.

        WARNING! Don't try to send Message without wrapper.
        Use Peer.request
        """
        if isinstance(wrapper, Message):
            log.warning('`Peer.send` method for sending requests is deprecated! '
                        'Use `Peer.request` instead')
            return self.request(wrapper)
        self.proto._send(wrapper, self.addr)

    def request(self, message: Message):
        """
        Send request to Peer.

        WARNING! Requests are unsafe.
        Don't try to send private information via Peer.request
        """
        log.debug(f'{self}: Send request {message}')
        wrapper = MessageWrapper(message, 'request')
        self.proto._send(wrapper, self.addr)

    def dump(self) -> Dict[str, str]:
        return {
            'address': self.addr
        }

    def __repr__(self):
        return f'<Peer {self.addr}>'


class User(Base):
    __tablename__ = 'users'

    public_key = Column(String)
    name = Column(String, primary_key=True)

    def __init__(self, proto, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.proto = proto

    def send(self, message: Message):
        log.debug(f'{self}: Send {message}')
        self.proto.send(message, self.name)

    def dump(self) -> Dict[str, str]:
        return {
            'key': self.public_key,
            'name': self.name
        }


class Tunnels(TempDict):
    expire = 6000

    def add(self, tunnel_id: str, backward_peer: Peer, forward_peer: Peer):
        # TODO: docstring
        self[tunnel_id] = [backward_peer, forward_peer]

    def send(self, message: MessageWrapper):
        # TODO: docstring
        peers = self.get(message.tunnel_id)
        if not peers:
            return
        peers[1]._send(message)


def create_db():
    Base.metadata.create_all(engine)
    session.commit()


def drop_db():
    try:
        os.remove(f'db/{Configs.name}_db.sqlite')
    except FileNotFoundError:
        pass
