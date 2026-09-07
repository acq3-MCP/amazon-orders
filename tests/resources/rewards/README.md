# Rewards Fixtures

Sanitized captures of the `https://www.amazon.com/credit/rewardscard/member` page (a plain `GET`).
The page is a Next.js app: `div#__next` holds only a skeleton loading animation and every visible
widget is rendered client-side, so the DOM carries none of the values on screen. The server embeds
the page data in the standard `<script id="__NEXT_DATA__" type="application/json">` blob, and the
card list at `props.pageProps.initialPageData.usCbccCardInfos` is all the Rewards parser reads. Only
that script (plus the nav shell and the skeleton `div#__next`) is retained. The Chase-hosted card
balance and payment-due fields are not in the page data at all.

| File | Variant | Provenance |
| --- | --- | --- |
| `rewards-card-member.html` | One card (Prime Visa) with a rewards balance in USD and points | Captured 2026-09-07 (browser "Save Page As"), sanitized |
| `rewards-card-member-no-card.html` | Empty `usCbccCardInfos` list | Fabricated from the capture — the source account holds a card, so the real no-card rendering is unverified (it may be a redirect to the apply page rather than an empty list) |
| `rewards-card-member-two-cards.html` | Two cards: the captured Prime Visa plus a fabricated non-Prime Amazon Visa with a `lastUpdateTime` set | Fabricated from the capture by duplicating the card entry |

Sanitization applied (the JSON structure and every key are byte-accurate to the capture; only values
changed):

- `customerId`, `cardId`, `token`, `ownership.amazonReferenceId`, and `ownership.cpid` replaced with
  fakes of the same shape
- `tail` (last four digits) remapped to `1234`
- Balance scaled by a constant factor, points recomputed so `amount.value == points.value *
  conversionRate` holds exactly
- Every inline `<script>` body other than `__NEXT_DATA__` emptied (they carried session identifiers),
  and the nav bar's customer name and delivery address replaced with placeholders
- The document trimmed to the head, nav shell, `div#__next` skeleton, and the data script
