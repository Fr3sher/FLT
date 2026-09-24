"""Shared exception identities for the versioned Cloud product contract."""


class LivePodError(RuntimeError):
    """A rental refusal or failure suitable for the Live rail."""


class VastError(RuntimeError):
    """A sanitized provider API failure."""


__all__ = ['LivePodError', 'VastError']
