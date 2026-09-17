# Prime Fixtures

Sanitized capture of the Prime membership payment history page, `https://www.amazon.com/mc/payments`
(Membership Central, breadcrumb "Your Account › Manage Your Prime Membership › Your Prime Payments"),
captured 2026-09-17 (browser "Save Page As"). The payment cards are server-rendered: one
`div.a-cardui` per membership charge inside the widget `div[cel_widget_id^="prime-payment-history_"]`
(painter `prime-payment-history-cards`), with the charge date in `div.a-cardui-header h3` and
label/value rows (`span.a-color-tertiary` label, `p` value) for "Total", "Order Number", and
"Receipts", the last holding the "View Receipt" link to
`/gp/digital/your-account/order-summary.html?…&orderID=D01-…&print=1`. The `_cHJpb_…` class suffixes
are build hashes and are kept verbatim so the tests prove the parser does not depend on them. No
pagination or "load more" control was present; the capture's eight cards were the account's whole
membership history (one per year), so single-page delivery is observed, not proven.

The membership fee Orders are `D01-` IDs that the Digital Orders tab does not list. Their Order
details and invoice print pages render the standard `div#orderDetails` layout (line item
"Prime Membership Fee", "Tax Collected", "Total for this Order") and parse with the existing
`Order` entity, which is why no receipt entity accompanies this one.

| File | Variant | Provenance |
| --- | --- | --- |
| `prime-payments.html` | Eight payment cards, November 17 of 2018 through 2025 | Captured, sanitized |
| `prime-payments-empty.html` | The widget with no cards | Fabricated from the capture by removing the cards — the source account has payments, so the real no-payments rendering is unverified |
| `prime-payments-error.html` | Membership Central's own error page ("Oops." heading, "there's a problem with this page") served with a 200 in place of the widget | Captured 2026-09-17 server-side, by the library's own client from an AWS Lambda with a fully authenticated session that had just read the Order history; a browser on the same account got the payments; the same client from a residential address got the same error page. Cut to the `div.a-container.mc-container` error block inside the same page shell, scripts and styles removed, tracking ids zeroed |

Sanitization applied (the widget markup is otherwise byte-accurate to the capture):

- Only the payment history widget slot (`div.widgetmc-paymenthistory-slot`, which holds the
  "Your Prime Payments" heading and the cards) is retained, inside a minimal page shell with a
  placeholder nav name and the breadcrumb; every `<script>` emptied
- The eight Order numbers remapped to `D01-1000001-2000001` … `D01-1000008-2000008` (the receipt
  links carry the same remapped IDs); dates and totals kept
- Request, placement, and card-instance identifiers (`pf_rd_*` / `pd_rd_*` classes, CSA request
  IDs, `CardInstance…`) replaced with zeros
