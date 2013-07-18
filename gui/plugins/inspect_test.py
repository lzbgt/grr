#!/usr/bin/env python
# -*- mode: python; encoding: utf-8 -*-

# Copyright 2011 Google Inc. All Rights Reserved.
"""Test the inspect interface."""


from grr.lib import rdfvalue
from grr.lib import test_lib


class TestInspectView(test_lib.GRRSeleniumTest):
  """Test the inspect interface."""

  def testInspect(self):
    """Test the inspect UI."""

    self.Open("/")

    self.WaitUntil(self.IsElementPresent, "client_query")

    self.Type("client_query", "0001")
    self.Click("client_query_submit")

    self.WaitUntilEqual(u"C.0000000000000001",
                        self.GetText, "css=span[type=subject]")

    # Choose client 1
    self.Click("css=td:contains('0001')")
    self.WaitUntil(self.IsElementPresent, "css=a[grrtarget=LaunchFlows]")

    self.Click("css=a[grrtarget=LaunchFlows]")
    self.WaitUntil(self.IsElementPresent, "id=_Administrative")
    self.Click("css=#_Administrative ins")

    self.WaitUntil(self.IsTextPresent, "Interrogate")
    self.Click("css=a:contains(Interrogate)")

    self.WaitUntil(self.IsElementPresent, "css=input[value=Launch]")
    self.Click("css=input[value=Launch]")

    # Open the "Advanced" dropdown.
    self.Click("css=a[href='#HostAdvanced']")
    # Click on the "Debug client requests".
    self.Click("css=a[grrtarget=InspectView]")

    self.WaitUntil(self.IsElementPresent, "css=td:contains(GetPlatformInfo)")

    # Check that the we can see the requests in the table.
    for request in "GetPlatformInfo GetConfig EnumerateInterfaces Find".split():
      self.assertTrue(self.IsElementPresent(
          "css=td:contains(%s)" % request))

    self.Click("css=td:contains(GetPlatformInfo)")

    # Check that the proto is rendered inside the tab.
    self.WaitUntil(self.IsElementPresent,
                   "css=.tab-content td.proto_value:contains(GetPlatformInfo)")

    # Check that the request tab is currently selected.
    self.assertTrue(
        self.IsElementPresent("css=li.active:contains(Request)"))

    # Here we emulate a mock client with no actions (None) this should produce
    # an error.
    mock = test_lib.MockClient(rdfvalue.ClientURN("C.0000000000000001"),
                               None, token=self.token)
    while mock.Next():
      pass

    # Now select the Responses tab:
    self.Click("css=li a:contains(Responses)")
    self.WaitUntil(self.IsElementPresent, "css=td:contains('flow:response:')")

    self.assertTrue(self.IsElementPresent(
        "css=.tab-content td.proto_value:contains(GENERIC_ERROR)"))

    self.assertTrue(self.IsElementPresent(
        "css=.tab-content td.proto_value:contains(STATUS)"))
