import time
import logging

from hodl_net.models import Peer, Message
from socket import gethostbyname

log = logging.getLogger(__name__)


class PublicPeerExchange:
    def __init__(self, core, bootstrap_servers=None):

        if bootstrap_servers is None:
            bootstrap_servers = ["startnode.hodleum.org:8000"]

        self.core = core

        log.info("Starting Public Peer Exchange mechanism")

        for i in bootstrap_servers:
            _addr = i.split(":")
            addr = gethostbyname(_addr[0])
            d_port = _addr[1]

            peer = Peer(self.core.udp)
            peer.addr = f"{addr}:{d_port}"

            logging.info(f"Connecting to peer {i}")

            peer.request(Message("ping", data={'msg': "av_check"}))

