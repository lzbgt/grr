#!/usr/bin/env python
"""Test for client comms."""

import time

import requests

from grr_response_client import comms
from grr.lib import flags
from grr.lib import utils
from grr.test_lib import test_lib


def _make_http_response(code=200):
  """A helper for creating HTTP responses."""
  response = requests.Response()
  response.status_code = code
  return response


def _make_404():
  return _make_http_response(404)


def _make_200(content):
  response = _make_http_response(200)
  response._content = content
  return response


class RequestsInstrumentor(object):
  """Instrument the urllib2 library."""

  def __init__(self):
    self.time = 0
    self.current_opener = None
    # Record the actions in order.
    self.actions = []

    # These are the responses we will do.
    self.responses = []

  def request(self, **request_options):
    self.actions.append([self.time, request_options])
    if self.responses:
      response = self.responses.pop(0)
      if isinstance(response, IOError):
        raise response
      return response
    else:
      return _make_404()

  def sleep(self, timeout):
    self.time += timeout

  def instrument(self):
    """Install the mocks required.

    Returns:
       A context manager that when exits restores the mocks.
    """
    self.actions = []
    return utils.MultiStubber((requests, "request", self.request),
                              (time, "sleep", self.sleep))


class URLFilter(RequestsInstrumentor):
  """Emulate only a single server url that works."""

  def request(self, url=None, **kwargs):
    # If request is from server2 - return a valid response. Assume, server2 is
    # reachable from all proxies.
    response = super(URLFilter, self).request(url=url, **kwargs)
    if "server2" in url:
      return _make_200("Good")
    return response


class MockHTTPManager(comms.HTTPManager):

  def _GetBaseURLs(self):
    return ["http://server1/", "http://server2/", "http://server3/"]

  def _GetProxies(self):
    """Do not test the proxy gathering logic itself."""
    return ["proxy1", "proxy2", "proxy3"]


class HTTPManagerTest(test_lib.GRRBaseTest):
  """Tests the HTTP Manager."""

  def MakeRequest(self, instrumentor, manager, path, verify_cb=lambda x: True):
    with utils.MultiStubber((requests, "request", instrumentor.request),
                            (time, "sleep", instrumentor.sleep)):
      return manager.OpenServerEndpoint(path, verify_cb=verify_cb)

  def testBaseURLConcatenation(self):
    instrumentor = RequestsInstrumentor()
    with instrumentor.instrument():
      manager = MockHTTPManager()
      manager.OpenServerEndpoint("/control")

    # Make sure that the URL is concatenated properly (no //).
    self.assertEqual(instrumentor.actions[0][1]["url"],
                     "http://server1/control")

  def testProxySearch(self):
    """Check that all proxies will be searched in order."""
    # Do not specify a response - all requests will return a 404 message.
    instrumentor = RequestsInstrumentor()
    with instrumentor.instrument():
      manager = MockHTTPManager()
      result = manager.OpenURL("http://www.google.com/")

    # Three requests are made.
    proxies = [x[1]["proxies"]["https"] for x in instrumentor.actions]
    self.assertEqual(proxies, manager.proxies)

    # Result is an error since no requests succeeded.
    self.assertEqual(result.code, 404)

  def testVerifyCB(self):
    """Check that we can handle captive portals via the verify CB.

    Captive portals do not cause an exception but return bad data.
    """

    def verify_cb(http_object):
      return http_object.data == "Good"

    instrumentor = RequestsInstrumentor()

    # First request is an exception, next is bad and the last is good.
    instrumentor.responses = [_make_404(), _make_200("Bad"), _make_200("Good")]
    with instrumentor.instrument():
      manager = MockHTTPManager()
      result = manager.OpenURL("http://www.google.com/", verify_cb=verify_cb)

    self.assertEqual(result.data, "Good")

  def testURLSwitching(self):
    """Ensure that the manager switches URLs to one that works."""
    # Only server2 works and returns Good response.
    instrumentor = URLFilter()
    with instrumentor.instrument():
      manager = MockHTTPManager()
      result = manager.OpenServerEndpoint("control")

    # The result is correct.
    self.assertEqual(result.data, "Good")

    queries = [(x[1]["url"], x[1]["proxies"]["http"])
               for x in instrumentor.actions]

    self.assertEqual(
        queries,
        # First search for server1 through all proxies.
        [
            ("http://server1/control", "proxy1"),
            ("http://server1/control", "proxy2"),
            ("http://server1/control", "proxy3"),

            # Now search for server2 through all proxies.
            ("http://server2/control", "proxy1")
        ])

  def testTemporaryFailure(self):
    """If the front end gives an intermittent 500, we must back off."""
    instrumentor = RequestsInstrumentor()
    # First response good, then a 500 error, then another good response.
    instrumentor.responses = [
        _make_200("Good"),
        _make_http_response(code=500),
        _make_200("Also Good")
    ]

    manager = MockHTTPManager()
    with instrumentor.instrument():
      # First request - should be fine.
      result = manager.OpenServerEndpoint("control")

    self.assertEqual(result.data, "Good")

    with instrumentor.instrument():
      # Second request - should appear fine.
      result = manager.OpenServerEndpoint("control")

    self.assertEqual(result.data, "Also Good")

    # But we actually made two requests.
    self.assertEqual(len(instrumentor.actions), 2)

    # And we waited 60 seconds to make the second one.
    self.assertEqual(instrumentor.actions[0][0], 0)
    self.assertEqual(instrumentor.actions[1][0], manager.error_poll_min)

    # Make sure that the manager cleared its consecutive_connection_errors.
    self.assertEqual(manager.consecutive_connection_errors, 0)

  def test406Errors(self):
    """Ensure that 406 enrollment requests are propagated immediately.

    Enrollment responses (406) are sent by the server when the client is not
    suitable enrolled. The http manager should treat those as correct responses
    and stop searching for proxy/url combinations in order to allow the client
    to commence enrollment workflow.
    """
    instrumentor = RequestsInstrumentor()
    instrumentor.responses = [_make_http_response(code=406)]

    manager = MockHTTPManager()
    with instrumentor.instrument():
      # First request - should raise a 406 error.
      result = manager.OpenServerEndpoint("control")

    self.assertEqual(result.code, 406)

    # We should not search for proxy/url combinations.
    self.assertEqual(len(instrumentor.actions), 1)

    # A 406 message is not considered an error.
    self.assertEqual(manager.consecutive_connection_errors, 0)

  def testConnectionErrorRecovery(self):
    instrumentor = RequestsInstrumentor()

    # When we can't connect at all (server not listening), we get a
    # requests.exceptions.ConnectionError but the response object is None.
    err_response = requests.ConnectionError("Error", response=None)
    instrumentor.responses = [err_response, _make_200("Good")]
    with instrumentor.instrument():
      manager = MockHTTPManager()
      result = manager.OpenServerEndpoint("control")

    self.assertEqual(result.data, "Good")


def main(argv):
  test_lib.main(argv)


if __name__ == "__main__":
  flags.StartMain(main)
