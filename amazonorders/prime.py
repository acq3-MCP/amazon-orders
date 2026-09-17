__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import logging
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.prime_payment import PrimePayment
from amazonorders.exception import AmazonOrdersError
from amazonorders.session import AmazonSession

logger = logging.getLogger(__name__)


class PrimePaymentsPageResult:
    """
    The parsed contents of the Prime payments page, as returned by
    :func:`~amazonorders.prime.AmazonPrime.parse_prime_payments_page`.
    """

    def __init__(self,
                 payments: List[PrimePayment],
                 page_type: str) -> None:
        #: The payments on the page, newest first as the page lists them.
        self.payments: List[PrimePayment] = payments
        #: What the page is: ``payments`` (payment cards were parsed), ``empty`` (the payment history
        #: widget rendered with no cards), or ``not_prime_payments`` (a sign-in, Captcha, or challenge
        #: page; the supplied HTML is not the Prime payments page at all).
        self.page_type: str = page_type

    def __repr__(self) -> str:
        return f"<PrimePaymentsPageResult: \"{self.page_type}\", {len(self.payments)} payments>"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.page_type}: {len(self.payments)} payments"


def _parse_prime_payments_page(parsed: Tag,
                               config: AmazonOrdersConfig) -> PrimePaymentsPageResult:
    """
    Classify a parsed Prime payments page and parse its payment cards.

    A page with no payment history widget that is not a recognizable sign-in or challenge page
    raises, since that is a page that failed to render rather than a member with no payments. If
    a card fails to parse, the raised exception's :attr:`~amazonorders.exception.AmazonOrdersError.meta`
    carries ``partial_payments`` (the payments parsed before the failure).

    :param parsed: The parsed page.
    :param config: The config to use.
    :return: The parsed page.
    """
    widget_tag = util.select_one(parsed, config.selectors.PRIME_PAYMENTS_WIDGET_SELECTOR)

    if widget_tag is None:
        if util.select_one(parsed, config.selectors.AUTH_CHALLENGE_PAGE_SELECTORS):
            return PrimePaymentsPageResult(payments=[], page_type="not_prime_payments")

        raise AmazonOrdersError("Could not parse Prime payments. Check if Amazon changed the HTML.")

    payments: List[PrimePayment] = []
    for payment_tag in util.select(widget_tag, config.selectors.PRIME_PAYMENT_SELECTOR):
        try:
            payments.append(PrimePayment(payment_tag, config))
        except AmazonOrdersError as e:
            e.meta = {**{"partial_payments": payments}, **(e.meta or {})}
            raise

    return PrimePaymentsPageResult(payments=payments,
                                   page_type="payments" if payments else "empty")


class AmazonPrime:
    """
    Using an authenticated :class:`~amazonorders.session.AmazonSession`, can be used to query Amazon
    for the Prime membership payment history.

    Membership fee charges are digital Orders (``D01-`` IDs) that neither the Order history nor the
    Digital Orders tab lists; the Prime payments page is the only listing of them. Each
    :class:`~amazonorders.entity.prime_payment.PrimePayment` carries the charge date, total, and
    Order number; the Order itself is fetched with :func:`~amazonorders.orders.AmazonOrders.get_order`.
    """

    def __init__(self,
                 amazon_session: AmazonSession,
                 debug: Optional[bool] = None,
                 config: Optional[AmazonOrdersConfig] = None) -> None:
        if not debug:
            debug = amazon_session.debug
        if not config:
            config = amazon_session.config

        #: The session to use for requests.
        self.amazon_session: AmazonSession = amazon_session
        #: The config to use.
        self.config: AmazonOrdersConfig = config

        #: Setting logger to ``DEBUG`` will send output to ``stderr``.
        self.debug: bool = debug
        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_prime_payments(self) -> List[PrimePayment]:
        """
        Get every charge in the Prime membership payment history, newest first as the page lists them.

        :return: The Prime payments (empty when the page lists none).
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        page_response = self.amazon_session.get(self.config.constants.PRIME_PAYMENTS_URL)
        self.amazon_session.check_response(page_response)

        result = _parse_prime_payments_page(page_response.parsed, self.config)

        if result.page_type == "not_prime_payments":
            raise AmazonOrdersError("Amazon rendered a sign-in or challenge page instead of the Prime payments page.")

        return result.payments

    @staticmethod
    def parse_prime_payments_page(html: str,
                                  config: AmazonOrdersConfig) -> PrimePaymentsPageResult:
        """
        Parse an already-fetched Prime payments page into its payments and page type, without a
        session driving the fetch.

        The result's :attr:`~amazonorders.prime.PrimePaymentsPageResult.page_type` distinguishes a
        member with no payments (``empty``, the payment history widget rendered with no cards) from
        a page that is not the Prime payments page at all (``not_prime_payments``: sign-in, Captcha,
        or challenge pages). A page with neither the widget nor a recognizable challenge raises,
        since that is a page that failed to render rather than an empty history.

        If a card fails to parse, the raised exception's
        :attr:`~amazonorders.exception.AmazonOrdersError.meta` carries ``partial_payments`` (the
        payments parsed before the failure).

        :param html: The Prime payments page HTML to parse.
        :param config: The config providing the selectors used for parsing.
        :return: The parsed page.
        """
        parsed = BeautifulSoup(html, config.bs4_parser)

        return _parse_prime_payments_page(parsed, config)
