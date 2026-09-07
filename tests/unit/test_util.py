__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

from bs4 import BeautifulSoup

from amazonorders.selectors import Selector
from amazonorders.util import to_type, cleanup_html_text, select
from tests.unittestcase import UnitTestCase


class TestUtil(UnitTestCase):
    def test_to_type(self):
        self.assertIsNone(to_type(None))

        self.assertEqual(to_type("0.0"), 0.0)
        self.assertEqual(to_type("0.1"), 0.1)
        self.assertEqual(to_type("0"), 0)
        self.assertEqual(to_type("1.0"), 1.0)
        self.assertEqual(to_type("1.1"), 1.1)
        self.assertEqual(to_type("1"), 1)

        self.assertEqual(to_type("True"), True)
        self.assertEqual(to_type("False"), False)

        self.assertIsNone(to_type(""))
        self.assertEqual(to_type(" "), " ")
        self.assertEqual(to_type("None"), "None")

    def test_cleanup_html_text(self):
        self.assertEqual(cleanup_html_text("""This is a paragraph.
        
        
        So much space. More space.
        This sentence will have period added
        So will this one with two spaces
        
        And then some more.
        
        And that's all"""  # noqa: W293
                                           ),
                         "This is a paragraph. So much space. More space. This sentence will have period "
                         "added. So will this one with two spaces. And then some more. And that's all.")
        self.assertEqual(cleanup_html_text(""" There was a problem
        
        The One Time Password (OTP) you entered is not valid.
        
        Please try again
        
        """  # noqa: W293
                                           ),
                         "There was a problem. The One Time Password (OTP) you entered is not valid. "
                         "Please try again.")
        self.assertEqual(cleanup_html_text("""
        
        This has leading newlines.
        
        They should be removed
        
        """  # noqa: W293
                                           ), "This has leading newlines. They should be removed.")

    def test_select_with_text_selector_returns_matched_tags(self):
        # GIVEN two tags match the text and one does not
        parsed = BeautifulSoup("<div><span>Rewards balance</span><span>Other</span>"
                               "<p><b>Rewards balance</b></p><i>Rewards balance</i></div>",
                               self.test_config.bs4_parser)

        # WHEN
        tags = select(parsed, Selector("span, b", text="Rewards balance"))

        # THEN the matched tags themselves come back (not their children), in document order
        self.assertEqual(["span", "b"], [t.name for t in tags])
        self.assertEqual(["Rewards balance", "Rewards balance"], [t.text for t in tags])
