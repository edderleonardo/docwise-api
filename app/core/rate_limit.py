from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """
    Real client IP behind Cloud Run's load balancer.

    Google's front end appends the connecting client's IP as the LAST entry
    of X-Forwarded-For, so earlier entries (which the client can forge) are
    ignored. Locally there is no header and we fall back to the socket peer.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)
