"""UDP compatibility endpoint for the original simulator test hook."""

import socket

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.responses import json_success

router = APIRouter()


@router.get("/udp/sendMsg")
def send_msg():
    """Send the same fixed test datagram as the Java `UdpController`."""

    settings = get_settings()
    message = "45a4d5as4d5asd\u6309\u65f6\u8270\u82e6\u6253\u4e0a\u770b"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(message.encode("utf-8"), (settings.udp_target_host, settings.udp_target_port))
    return json_success(None)
