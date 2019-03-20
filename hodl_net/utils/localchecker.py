from netaddr import IPNetwork, IPAddress
import socket


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def check_ip(ip, ip_net=IPNetwork(get_ip()).cidr):
    is_local = False
    if IPAddress(ip) in IPNetwork(ip_net) and IPAddress(ip) != IPAddress(get_ip()):
            is_local = True
    return is_local
