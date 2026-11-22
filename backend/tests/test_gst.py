"""Unit tests for the GST engine (app/gst.py). Pure functions, no database."""
import pytest

from app.gst import Line, compute, r0, r2


def line(qty, rate, gst=5, discount=0, cat="TAXABLE"):
    return Line(qty=qty, rate=rate, discount=discount, gst_rate=gst, tax_category=cat)


# ---------- rounding helpers ----------
@pytest.mark.parametrize("value, expected", [(2.675, 2.68), (1.005, 1.01), (0.125, 0.13), (-0.005, -0.01),
                                             (None, 0), (10, 10)])
def test_r2_rounds_half_up(value, expected):
    assert r2(value) == expected


@pytest.mark.parametrize("value, expected", [(0.5, 1), (1.5, 2), (2.5, 3), (157.49, 157), (None, 0)])
def test_r0_rounds_half_up(value, expected):
    assert r0(value) == expected


# ---------- exclusive prices ----------
def test_exclusive_intra_state_splits_cgst_sgst():
    ln = line(2, 180)
    t = compute([ln])
    assert (ln.gross, ln.taxable, ln.cgst, ln.sgst, ln.igst, ln.total) == (360, 360, 9, 9, 0, 378)
    assert (t.taxable, t.cgst, t.sgst, t.igst, t.total_tax, t.grand_total, t.round_off) == (360, 9, 9, 0, 18, 378, 0)


def test_exclusive_inter_state_uses_igst():
    ln = line(2, 180)
    t = compute([ln], inter_state=True)
    assert (ln.cgst, ln.sgst, ln.igst) == (0, 0, 18)
    assert (t.cgst, t.sgst, t.igst, t.grand_total) == (0, 0, 18, 378)


def test_mixed_rates_are_taxed_per_line():
    a, b = line(1, 100, gst=5), line(1, 100, gst=18)
    t = compute([a, b], round_to_rupee=False)
    assert (a.cgst, b.cgst) == (2.5, 9)
    assert t.total_tax == 23
    assert t.grand_total == 223


# ---------- inclusive prices ----------
def test_inclusive_price_extracts_tax():
    ln = line(1, 105)
    t = compute([ln], inclusive=True)
    assert (ln.taxable, ln.cgst, ln.sgst, ln.total) == (100, 2.5, 2.5, 105)
    assert t.grand_total == 105


@pytest.mark.parametrize("price", [1, 15, 18, 99, 100, 133, 180, 260, 999.99])
@pytest.mark.parametrize("gst", [5, 12, 18, 28])
@pytest.mark.parametrize("inter", [False, True])
def test_inclusive_line_total_always_equals_price(price, gst, inter):
    """The customer must pay exactly the menu price; any paisa difference goes into the taxable value."""
    ln = line(1, price, gst=gst)
    t = compute([ln], inclusive=True, inter_state=inter, round_to_rupee=False)
    assert ln.total == r2(price)
    assert r2(ln.taxable + ln.cgst + ln.sgst + ln.igst) == r2(price)
    assert t.grand_total == r2(price)


def test_inclusive_inter_state():
    ln = line(1, 118, gst=18)
    compute([ln], inclusive=True, inter_state=True)
    assert (ln.taxable, ln.igst, ln.cgst) == (100, 18, 0)


# ---------- discounts ----------
def test_item_discount_reduces_taxable_value():
    ln = line(3, 15, discount=5)
    t = compute([ln], round_to_rupee=False)
    assert ln.taxable == 40
    assert ln.cgst == ln.sgst == 1
    assert (t.gross, t.item_discount, t.grand_total) == (45, 5, 42)


def test_bill_discount_is_shared_in_proportion():
    a, b = line(1, 100), line(1, 200)
    t = compute([a, b], bill_discount=30, round_to_rupee=False)
    assert (a.bill_discount_share, b.bill_discount_share) == (10, 20)
    assert (a.taxable, b.taxable) == (90, 180)
    assert t.bill_discount == 30
    assert t.taxable == 270


def test_bill_discount_rounding_goes_to_last_line():
    lines = [line(1, 100), line(1, 100), line(1, 100)]
    compute(lines, bill_discount=10)
    shares = [ln.bill_discount_share for ln in lines]
    assert shares == [3.33, 3.33, 3.34]
    assert r2(sum(shares)) == 10


def test_bill_discount_uses_value_after_item_discount():
    a, b = line(1, 100, discount=50), line(1, 50)
    compute([a, b], bill_discount=10)
    assert (a.bill_discount_share, b.bill_discount_share) == (5, 5)


def test_full_bill_discount_gives_zero_bill():
    t = compute([line(2, 50)], bill_discount=100)
    assert (t.taxable, t.total_tax, t.grand_total) == (0, 0, 0)


def test_inclusive_with_bill_discount():
    ln = line(1, 210)
    t = compute([ln], bill_discount=0, inclusive=True)
    assert t.grand_total == 210
    ln2 = line(1, 210)
    t2 = compute([ln2], bill_discount=21, inclusive=True)
    assert t2.grand_total == 189
    assert (ln2.taxable, ln2.cgst) == (180, 4.5)


# ---------- non-taxable lines ----------
@pytest.mark.parametrize("cat", ["EXEMPT", "NIL", "ZERO"])
def test_non_taxable_lines_carry_no_tax(cat):
    taxed, free = line(1, 100), line(1, 40, gst=5, cat=cat)
    t = compute([taxed, free])
    assert (free.cgst, free.sgst, free.igst, free.taxable) == (0, 0, 0, 40)
    assert t.exempt == 40
    assert t.taxable == 100
    assert t.grand_total == 145


# ---------- round off and other charges ----------
def test_round_to_rupee_records_round_off():
    t = compute([line(1, 150)])  # 150 + 7.50 tax
    assert t.grand_total == 158
    assert t.round_off == 0.5


def test_round_off_can_be_negative():
    t = compute([line(1, 148)])  # 148 + 7.40 = 155.40
    assert t.grand_total == 155
    assert t.round_off == -0.4


def test_no_rounding_keeps_paise():
    t = compute([line(1, 150)], round_to_rupee=False)
    assert (t.grand_total, t.round_off) == (157.5, 0)


def test_other_charges_added_after_tax():
    t = compute([line(1, 100)], other_charges=20, round_to_rupee=False)
    assert t.total_tax == 5
    assert t.grand_total == 125


# ---------- validation ----------
@pytest.mark.parametrize("kwargs, lines", [
    ({}, [line(0, 10)]),
    ({}, [line(-1, 10)]),
    ({}, [line(1, -10)]),
    ({}, [line(1, 10, discount=-1)]),
    ({}, [line(1, 10, discount=11)]),
    ({"bill_discount": 11}, [line(1, 10)]),
    ({"bill_discount": -1}, [line(1, 10)]),
])
def test_invalid_input_is_rejected(kwargs, lines):
    with pytest.raises(ValueError):
        compute(lines, **kwargs)
