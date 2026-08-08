"""Dependency-free helpers used while starting the LDS web server."""
import socket


def _wildcard_is_free(port: int) -> bool:
    """Is the port free for EVERY address, not just the one we were asked about?

    A listener on the wildcard address (0.0.0.0 / ::) collides with a bind to any
    specific address on the same port — but Windows does not report it that way.
    It lets the more specific bind succeed, because 127.0.0.1 is a closer match
    than 0.0.0.0. So probing only the configured host answers "free" while the
    port is very much taken, and the second server starts anyway: two processes
    on one port, the specific one capturing loopback traffic, no error at all.

    That is the real collision LDS hits — a second launch while the first is
    still running in LAN mode, which binds the wildcard.

    A family we cannot even create a socket for is not holding anything, so it is
    skipped rather than counted as occupied; treating an IPv6-less host as "every
    port is taken" would push the search through all its attempts and then fail.
    """
    for family, address in ((socket.AF_INET, ("0.0.0.0", port)),
                            (socket.AF_INET6, ("::", port))):
        try:
            probe = socket.socket(family, socket.SOCK_STREAM)
        except OSError:
            continue
        with probe:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(address)
            except OSError:
                return False
    return True


def can_bind(host: str, port: int) -> bool:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM,
                                       flags=socket.AI_PASSIVE)
    except socket.gaierror:
        return False
    bound_any = False
    for family, socktype, proto, _, sockaddr in addresses:
        try:
            with socket.socket(family, socktype, proto) as candidate:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    candidate.setsockopt(socket.SOL_SOCKET,
                                         socket.SO_EXCLUSIVEADDRUSE, 1)
                candidate.bind(sockaddr)
            bound_any = True
        except OSError:
            # A hostname such as localhost can resolve to IPv4 and IPv6. If
            # either address is occupied, Werkzeug may choose it and fail.
            return False
    # Binding the requested address is necessary but NOT sufficient: a wildcard
    # listener makes that bind succeed while the port is taken. See above.
    return bound_any and _wildcard_is_free(port)


def find_available_port(host: str, preferred_port: int, max_attempts: int = 100) -> int:
    if not 1 <= preferred_port <= 65535:
        raise ValueError(f"Invalid server port: {preferred_port}")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    stop = min(65536, preferred_port + max_attempts)
    for port in range(preferred_port, stop):
        if can_bind(host, port):
            return port
    raise OSError(f"No available TCP port found from {preferred_port} to {stop - 1}")
