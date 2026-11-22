"""GST calculation shared by billing, purchases and notes.

Rules implemented:
* discount is applied before tax (reduces taxable value);
* bill-level discount is distributed across lines in proportion to their value;
* prices may be GST-inclusive (tax is extracted) or exclusive (tax is added);
* INTRA supply -> CGST + SGST (half each); INTER supply -> IGST;
* EXEMPT / NIL / ZERO-rated lines carry no tax.
Rates are always taken from the product master / user input — nothing is hard-coded."""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

NON_TAXABLE = {"EXEMPT", "NIL", "ZERO"}


def r2(x: float) -> float:
    """Round half-up to paise (Python's round() is banker's rounding)."""
    return float(Decimal(repr(float(x or 0))).quantize(Decimal("0.01"), ROUND_HALF_UP))


def r0(x: float) -> float:
    return float(Decimal(repr(float(x or 0))).quantize(Decimal("1"), ROUND_HALF_UP))


@dataclass
class Line:
    qty: float
    rate: float
    discount: float = 0
    gst_rate: float = 0
    tax_category: str = "TAXABLE"
    # outputs
    gross: float = 0
    bill_discount_share: float = 0
    taxable: float = 0
    cgst: float = 0
    sgst: float = 0
    igst: float = 0
    total: float = 0
    extra: dict = field(default_factory=dict)


@dataclass
class Totals:
    gross: float = 0
    item_discount: float = 0
    bill_discount: float = 0
    taxable: float = 0
    exempt: float = 0
    cgst: float = 0
    sgst: float = 0
    igst: float = 0
    total_tax: float = 0
    round_off: float = 0
    grand_total: float = 0


def compute(lines: list[Line], bill_discount: float = 0, inclusive: bool = False,
            inter_state: bool = False, round_to_rupee: bool = True, other_charges: float = 0) -> Totals:
    for ln in lines:
        if ln.qty <= 0:
            raise ValueError("Quantity must be greater than zero")
        if ln.rate < 0 or ln.discount < 0:
            raise ValueError("Rate and discount cannot be negative")
        ln.gross = r2(ln.qty * ln.rate)
        if ln.discount > ln.gross:
            raise ValueError("Item discount cannot exceed the item amount")

    net_values = [ln.gross - ln.discount for ln in lines]
    base = sum(net_values)
    bill_discount = r2(bill_discount or 0)
    if bill_discount < 0 or bill_discount > base + 0.001:
        raise ValueError("Bill discount must be between 0 and the bill amount")

    # distribute the bill discount; last line absorbs rounding difference
    remaining = bill_discount
    for i, ln in enumerate(lines):
        if i == len(lines) - 1:
            share = remaining
        else:
            share = r2(bill_discount * net_values[i] / base) if base else 0
            remaining = r2(remaining - share)
        ln.bill_discount_share = share

    t = Totals(bill_discount=bill_discount)
    for ln in lines:
        value = r2(ln.gross - ln.discount - ln.bill_discount_share)
        rate = 0 if ln.tax_category in NON_TAXABLE else (ln.gst_rate or 0)
        taxable = r2(value / (1 + rate / 100)) if inclusive and rate else value
        if inter_state:
            ln.igst = r2(taxable * rate / 100)
            ln.cgst = ln.sgst = 0
        else:
            ln.cgst = ln.sgst = r2(taxable * rate / 200)
            ln.igst = 0
        if inclusive and rate:
            # keep the customer-facing value exact: put any paisa difference into taxable value
            taxable = r2(value - ln.cgst - ln.sgst - ln.igst)
        ln.taxable = taxable
        ln.total = r2(taxable + ln.cgst + ln.sgst + ln.igst)

        t.gross += ln.gross
        t.item_discount += ln.discount
        if ln.tax_category in NON_TAXABLE:
            t.exempt += taxable
        else:
            t.taxable += taxable
        t.cgst += ln.cgst
        t.sgst += ln.sgst
        t.igst += ln.igst

    for k in ("gross", "item_discount", "taxable", "exempt", "cgst", "sgst", "igst"):
        setattr(t, k, r2(getattr(t, k)))
    t.total_tax = r2(t.cgst + t.sgst + t.igst)
    exact = r2(t.taxable + t.exempt + t.total_tax + (other_charges or 0))
    t.grand_total = r0(exact) if round_to_rupee else exact
    t.round_off = r2(t.grand_total - exact)
    return t
