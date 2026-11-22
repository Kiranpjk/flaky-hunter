"""A tiny suite with the classic flaky-test causes, used to produce the demo reports.

Run through examples/record_runs.sh, which sets DEMO_SEED per run so results are reproducible.
"""

import os
import random

rng = random.Random(int(os.getenv("DEMO_SEED", "0")))


def cart_total(items):
    return round(sum(price * qty for price, qty in items), 2)


def test_cart_total():
    assert cart_total([(2.5, 2), (1.0, 3)]) == 8.0


def test_empty_cart():
    assert cart_total([]) == 0


def test_payment_timeout():
    # Simulates a race with a slow payment sandbox: the response sometimes arrives too late.
    response_ms = rng.gauss(800, 250)
    assert response_ms < 1000, f"payment API answered after {response_ms:.0f} ms (limit 1000)"


def test_order_ids_unique():
    # Simulates shared state between tests: an ID collision every few runs.
    ids = [rng.randint(1, 60) for _ in range(3)]
    assert len(set(ids)) == len(ids), f"duplicate order id in {ids}"


def test_currency_format_de():
    assert f"{1234.5:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") == "1.234,50"
