import socket
import pytest
from port_utils import find_available_port


def test_uses_available_preferred_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert find_available_port("127.0.0.1", port) == port


def test_advances_past_occupied_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        occupied = listener.getsockname()[1]
        listener.listen()
        assert find_available_port("127.0.0.1", occupied) > occupied


def test_localhost_does_not_ignore_an_occupied_ipv4_address():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        occupied = listener.getsockname()[1]
        listener.listen()
        assert find_available_port("localhost", occupied) > occupied


def test_a_wildcard_listener_makes_the_port_unavailable_for_a_specific_host():
    """The collision that actually happens: LDS is already running in LAN mode,
    so it holds 0.0.0.0:<port>, and the second launch asks for 127.0.0.1:<port>.

    Windows lets a bind to a SPECIFIC address succeed while another socket holds
    the wildcard — the specific address is the more precise match. So the probe
    answers "free", the second server starts on the same port, and two servers
    end up sharing it with the specific one capturing loopback traffic. Nothing
    raises; it simply looks like it worked.

    The question worth asking is "is this PORT free", not "can I bind THIS
    address" — the two only diverge here, which is exactly the case users hit."""
    with socket.socket() as listener:
        listener.bind(("0.0.0.0", 0))
        occupied = listener.getsockname()[1]
        listener.listen()
        assert find_available_port("127.0.0.1", occupied) > occupied


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_rejects_invalid_ports(port):
    with pytest.raises(ValueError, match="Invalid server port"):
        find_available_port("127.0.0.1", port)


def test_rejects_empty_search_range():
    with pytest.raises(ValueError, match="max_attempts"):
        find_available_port("127.0.0.1", 5050, max_attempts=0)
