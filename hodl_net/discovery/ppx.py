import time
import logging

from hodl_net.models import Peer, Message
from socket import gethostbyname


class PublicPeerExchange:
    def __init__(self, core, bootstrap_servers=["startnode.hodleum.org:8000"]):
        self.core = core
        for i in bootstrap_servers:
            _addr = i.split(":")
            addr = gethostbyname(_addr[0])
            d_port = _addr[1]

            peer = Peer(self.core.udp)
            peer.addr = f"{addr}:{d_port}"
            print(peer.request(Message("ping", data={'msg': "av_check"})))

# TODO: Finish module, Fix PEER Checker
