"""The forecast: what a road costs, and whether the number was measured.

The one input that cannot be looked up is the user's uplink — it belongs to
their line, not to the app or to the pod. So it is measured from the transfers
this app already makes, and when there is no history the estimate SAYS it is an
assumption. A forecast labelled "measured" that was in fact a guess is worth
less than no forecast, because it will be believed.
"""
import pytest

from app.services import pod_transfer_plan as ptp


# --- what the estimate is built on ----------------------------------------------

def test_with_no_history_the_rate_is_labelled_an_assumption(app):
    with app.app_context():
        rate = ptp.uplink_bytes_per_second()
    assert rate['source'] == 'assumed'
    assert rate['samples'] == 0
    assert rate['mbps'] == ptp.ASSUMED_UPLINK_MBPS


def test_one_real_transfer_turns_the_guess_into_a_measurement(app):
    with app.app_context():
        assert ptp.record_uplink_sample(1_000_000_000, 80.0) is True
        rate = ptp.uplink_bytes_per_second()
    assert rate['source'] == 'measured'
    assert rate['samples'] == 1
    assert rate['mbps'] == pytest.approx(100.0, rel=0.01)


def test_the_median_survives_one_sick_host(app):
    """A single transfer throttled by a bad pod would otherwise poison every
    forecast made after it."""
    with app.app_context():
        for _ in range(4):
            ptp.record_uplink_sample(1_000_000_000, 80.0)      # 100 Mbit/s
        ptp.record_uplink_sample(1_000_000_000, 4000.0)        # 2 Mbit/s, sick
        rate = ptp.uplink_bytes_per_second()
    assert rate['mbps'] == pytest.approx(100.0, rel=0.01)


def test_a_tiny_or_instant_transfer_is_not_a_measurement_of_the_line(app):
    """A 2 kB token upload measures latency. Letting it into the median would
    forecast a 26 GB push from the speed of a handshake."""
    with app.app_context():
        assert ptp.record_uplink_sample(2048, 0.4) is False
        assert ptp.record_uplink_sample(10 ** 9, 0.05) is False
        assert ptp.uplink_bytes_per_second()['source'] == 'assumed'


def test_only_the_recent_transfers_count(app):
    with app.app_context():
        for _ in range(ptp._MAX_SAMPLES + 8):
            ptp.record_uplink_sample(10 ** 9, 80.0)
        assert ptp.uplink_bytes_per_second()['samples'] == ptp._MAX_SAMPLES


def test_a_configured_uplink_is_used_but_never_called_measured(app):
    with app.app_context():
        from app import config as cfg
        cfg.save_config({'cloud': {'uplink_mbps': 500}})
        rate = ptp.uplink_bytes_per_second()
    assert rate['source'] == 'configured'
    assert rate['mbps'] == 500


def test_a_real_measurement_beats_a_configured_guess(app):
    """The setting is what someone believes their line does; the samples are
    what it did."""
    with app.app_context():
        from app import config as cfg
        cfg.save_config({'cloud': {'uplink_mbps': 500}})
        ptp.record_uplink_sample(10 ** 9, 80.0)
        rate = ptp.uplink_bytes_per_second()
    assert rate['source'] == 'measured'
    assert rate['mbps'] == pytest.approx(100.0, rel=0.01)


def test_recording_never_raises_on_a_broken_store(app, monkeypatch):
    """A transfer that LANDED must not become an error because a statistic
    about it could not be written."""
    with app.app_context():
        monkeypatch.setattr(ptp.db.session, 'commit',
                            lambda: (_ for _ in ()).throw(RuntimeError('locked')))
        assert ptp.record_uplink_sample(10 ** 9, 80.0) is False


# --- the numbers themselves ------------------------------------------------------

def test_the_gpu_cost_is_price_times_the_time_the_pod_waits(app):
    with app.app_context():
        est = ptp.estimate_direct(10 ** 9, 3.60)
    # 1 GB at the assumed 50 Mbit/s = 160 s, plus the pod-side assembly.
    assert est['transfer_seconds'] == 160
    assert est['gpu_cost'] == pytest.approx(3.60 * est['seconds'] / 3600, abs=0.01)


def test_a_free_pod_costs_nothing_to_wait_for(app):
    with app.app_context():
        assert ptp.estimate_direct(10 ** 9, 0)['gpu_cost'] == 0
        assert ptp.estimate_hub(10 ** 9, 0)['gpu_cost'] == 0


def test_the_hub_rate_is_never_reported_as_measured(app):
    """It is the floor this app refuses to rent below, not something observed
    on this user's runs."""
    with app.app_context():
        ptp.record_uplink_sample(10 ** 9, 80.0)
        assert ptp.estimate_hub(10 ** 9, 1.0)['rate_source'] == 'floor'


def test_the_hub_estimate_includes_the_toll_it_actually_pays(app):
    """The command round-trip and the Hub handshake are not free, and a
    forecast of 'zero seconds' for a small file would read as broken."""
    with app.app_context():
        assert ptp.estimate_hub(0, 1.0)['seconds'] >= ptp._HUB_OVERHEAD_SECONDS


def test_durations_round_UP(app):
    """Rounding 89 minutes down to '1 h' is the kind of small lie that makes a
    whole panel untrustworthy."""
    assert ptp.duration_label(3540) == '59 min'
    assert ptp.duration_label(3541) == '60 min'
    assert ptp.duration_label(5400) == '1.5 h'
    assert ptp.duration_label(0) == '1 s'


def test_sizes_read_the_way_a_human_says_them():
    assert ptp.size_label(26 * 10 ** 9) == '26.0 GB'
    assert ptp.size_label(85 * 10 ** 6) == '85 MB'
