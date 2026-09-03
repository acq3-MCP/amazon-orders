.. rst-class:: hide-header

*************************************************************************************************
Amazon Orders - A Python library (and CLI) for Amazon order history, line items, and transactions
*************************************************************************************************

.. image:: _html/logo.png
   :alt: amazon-orders - A Python library (and CLI) for Amazon order history, line items, and transactions
   :align: center

|

.. image:: https://img.shields.io/pypi/v/amazon-orders
   :target: https://pypi.org/project/amazon-orders
.. image:: https://img.shields.io/pypi/pyversions/amazon-orders.svg
   :target: https://pypi.org/project/amazon-orders
.. image:: https://img.shields.io/codecov/c/github/alexdlaird/amazon-orders
   :target: https://codecov.io/gh/alexdlaird/amazon-orders
.. image:: https://img.shields.io/github/actions/workflow/status/alexdlaird/amazon-orders/build.yml
   :target: https://github.com/alexdlaird/amazon-orders/actions/workflows/build.yml
.. image:: https://img.shields.io/readthedocs/amazon-orders
   :target: https://amazon-orders.readthedocs.io
.. image:: https://img.shields.io/github/license/alexdlaird/amazon-orders
   :target: https://github.com/alexdlaird/amazon-orders

``amazon-orders`` is an unofficial library that provides a Python API (and CLI) for Amazon order history, line items, and transactions.

Only the English, ``.com`` version of Amazon is officially supported. Other Amazon domains can be targeted by passing
``domain`` to :class:`~amazonorders.session.AmazonSession` (or ``--domain`` on the CLI), and other English-based sites
may work by chance -- see :ref:`Known Limitations <known-limitations>` for details.

.. note::

    This package works by parsing data from Amazon's consumer-facing website. A periodic build validates
    functionality to ensure its stability, but as Amazon provides no official API to use, older versions of
    this package may break at any time, so it's recommended that you use the latest version.

Installation
============

``amazon-orders`` is available on
`PyPI <https://pypi.org/project/amazon-orders/>`__ and can be installed and/or upgraded
using ``pip``:

.. code:: sh

    pip install amazon-orders --upgrade

That's it! ``amazon-orders`` is now available as a package to your Python projects and from the command line.

If pinning, be sure to use a wildcard for the `minor version <https://semver.org/>`_ (e.g. ``==4.5.*``, not ``==4.5.0``)
to ensure you always get the latest stable release.

Basic Usage
===========

You'll use :class:`~amazonorders.session.AmazonSession` to authenticate your Amazon account, then
:class:`~amazonorders.orders.AmazonOrders` and :class:`~amazonorders.transactions.AmazonTransactions` to interact with
account data. :func:`~amazonorders.orders.AmazonOrders.get_order_history` and
:func:`~amazonorders.orders.AmazonOrders.get_order` are good places to start.

.. code:: python

    from amazonorders.session import AmazonSession
    from amazonorders.orders import AmazonOrders

    amazon_session = AmazonSession("<AMAZON_EMAIL>",
                                   "<AMAZON_PASSWORD>")
    amazon_session.login()

    amazon_orders = AmazonOrders(amazon_session)

    # Get orders from a specific year
    orders = amazon_orders.get_order_history(year=2023)

    # Or use time filters for recent orders
    orders = amazon_orders.get_order_history(time_filter="last30")  # Last 30 days
    orders = amazon_orders.get_order_history(time_filter="months-3")  # Past 3 months

    for order in orders:
        print(f"{order.order_number} - {order.grand_total}")

If the fields you're looking for aren't populated with the above, set ``full_details=True`` (or pass ``--full-details``
to the ``history`` CLI command), since by default it is ``False`` (enabling it slows down querying, since an additional
request for each order is necessary). Have a look at the :class:`~amazonorders.entity.order.Order` entity's docs to see
what fields are only populated with full details.

Gift Cards
----------

:class:`~amazonorders.gift_cards.AmazonGiftCards` reads the Gift Card balance and the activity ledger behind
it (claim code redemptions, amounts applied to Orders, refunds credited back, and reloads). It is read-only;
redeeming claim codes and reloading a balance are not supported.

.. code:: python

    from amazonorders.gift_cards import AmazonGiftCards

    gift_cards = AmazonGiftCards(amazon_session)

    balance = gift_cards.get_balance()

    for entry in gift_cards.get_gift_card_activity(days=90):
        print(f"{entry.activity_date} - {entry.description} - {entry.amount}")

Each :class:`~amazonorders.entity.gift_card_activity.GiftCardActivity` carries a signed
:attr:`~amazonorders.entity.gift_card_activity.GiftCardActivity.amount` (debits are negative) and the
:attr:`~amazonorders.entity.gift_card_activity.GiftCardActivity.closing_balance` after it, so the ledger's
running balance can be verified. Rows applied to an Order also carry
:attr:`~amazonorders.entity.gift_card_activity.GiftCardActivity.order_number`, which is ``None`` on the rows
Amazon renders without an Order link.

Digital Orders
--------------

Digital Orders (``D01-`` IDs: video rentals and purchases, apps, eGift cards) do not appear in the default
Order history at all. :class:`~amazonorders.digital_orders.AmazonDigitalOrders` walks the Digital Orders tab
instead.

.. code:: python

    from amazonorders.digital_orders import AmazonDigitalOrders

    digital_orders = AmazonDigitalOrders(amazon_session)

    # A single year window
    orders = digital_orders.get_digital_orders(year=2024)

    # Or every year window the account's Digital Orders tab offers, newest first
    orders = digital_orders.get_all_digital_orders()

Rows parse in to the same :class:`~amazonorders.entity.order.Order` entity as the rest of the history, with
Shipments and Recipients left empty, since digital Orders have neither. The tab's default window is the past
three months, so :func:`~amazonorders.digital_orders.AmazonDigitalOrders.get_digital_orders` always sends an
explicit time filter, and :func:`~amazonorders.digital_orders.AmazonDigitalOrders.get_all_digital_orders`
enumerates the year windows the page itself offers rather than assuming a range.

Command Line Usage
------------------

You can also run any command available to the main Python interface from the command line:

.. code:: sh

    amazon-orders login
    amazon-orders history --year 2023
    amazon-orders history --last-30-days
    amazon-orders history --last-3-months
    amazon-orders digital-orders --year 2024
    amazon-orders gift-card-balance
    amazon-orders gift-card-activity --days 90

Automating Authentication
-------------------------

Authentication can be automated by (in order of precedence) storing credentials in environment variables, passing them
to :class:`~amazonorders.session.AmazonSession`, or storing them in :class:`~amazonorders.conf.AmazonOrdersConfig`. The
environment variables ``amazon-orders`` looks for are:

- ``AMAZON_USERNAME``
- ``AMAZON_PASSWORD``
- ``AMAZON_OTP_SECRET_KEY`` (see :attr:`~amazonorders.session.AmazonSession.otp_secret_key`)

To enable **WAF auto-solve** via a third-party integration, install with the relevant extra:

.. code:: sh

    pip install amazon-orders[capsolver]
    pip install amazon-orders[anticaptcha]
    pip install amazon-orders[2captcha]

See :doc:`waf` for details.

To enable **browser-based challenge handling** (ACIC and JavaScript bot-detection pages) via
a headless browser, install with the ``browser`` extra:

.. code:: sh

    pip install amazon-orders[browser]
    playwright install chromium

See :doc:`browser` for details.

For **legacy Captcha auto-solve** on Python <=3.12, install with ``captcha`` extra:

.. code:: sh

    pip install amazon-orders[captcha]

See :ref:`Login Challenges <login-challenges>` for details.

.. _known-limitations:

Known Limitations
-----------------

- Non-English, non-``.com`` versions of Amazon are unsupported
    - Pass ``domain`` to :class:`~amazonorders.session.AmazonSession` (or set ``domain`` in
      :class:`~amazonorders.conf.AmazonOrdersConfig`, or pass ``--domain`` on the CLI) to point at another
      Amazon site. URLs and the URL-shaped headers (``Origin``, ``Host``, ``Referer``) are rewritten from
      the domain, and ``Accept-Language`` is adjusted for a small set of English-locale TLDs, so other
      English-based versions of Amazon (e.g. ``amazon.ca``) may work by chance. Other values such as the
      OpenID ``assoc_handle`` are not adjusted — subclass :class:`~amazonorders.constants.Constants` and
      set ``constants_class`` to override them if a particular site requires it. The ``AMAZON_BASE_URL``
      environment variable continues to work as a fallback.
    - We do not run nightly regressions against non-``.com`` versions of the site, and as such do not say
      they are officially supported. If you fork the repo, point the ``integration.yml`` workflow at a
      different domain with your own credentials, please `contact us <mailto:contact@alexlaird.com>`_ and
      we will start mentioning support for that version of the site.
    - See `issue #15 <https://github.com/alexdlaird/amazon-orders/issues/15>`_ for more details.
- Order history fetched outside an authenticated session may be encrypted
    - Amazon sometimes serves an Order history page with its card content replaced by an encrypted
      client-side-decryption payload. This has been observed on pages fetched by a browser rather than by
      :class:`~amazonorders.session.AmazonSession`. The cards are present as empty shells, so no fields can
      be read from them.
    - :func:`~amazonorders.orders.AmazonOrders.parse_order_history_page` reports such a page as
      ``page_type="csd_encrypted"`` rather than parsing it as empty Orders. Fetching the same window through
      an authenticated session returns readable markup.
- Device not remembered for OTP
    - Amazon will sometimes re-prompt for OTP even when a device has been remembered.
    - The recommended workaround for this is persisting the :attr:`~amazonorders.session.AmazonSession.otp_secret_key`
      in the config or the environment so that re-prompts are auto-solved.
    - See `issue #55 <https://github.com/alexdlaird/amazon-orders/issues/55>`_ for more details.

Dive Deeper
===========

For more advanced usage, dive deeper in to the rest of the documentation.

.. toctree::
   :maxdepth: 2

   api
   waf
   browser
   troubleshooting

.. include:: ../CONTRIBUTING.rst
