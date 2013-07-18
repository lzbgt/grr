#!/usr/bin/env python
"""Tests for export utils functions."""

import os


# pylint: disable=unused-import,g-bad-import-order
from grr.lib import server_plugins
# pylint: enable=unused-import,g-bad-import-order

from grr.client import conf
from grr.lib import aff4
from grr.lib import export_utils
from grr.lib import rdfvalue
from grr.lib import test_lib
from grr.lib import utils


class TestExports(test_lib.FlowTestsBaseclass):
  """Tests exporting of data."""

  def setUp(self):
    super(TestExports, self).setUp()

    self.out = self.client_id.Add("fs/os")
    self.CreateFile("testfile1")
    self.CreateFile("testfile2")
    self.CreateDir("testdir1")
    self.CreateFile("testdir1/testfile3")
    self.CreateDir("testdir1/testdir2")
    self.CreateFile("testdir1/testdir2/testfile4")

  def CreateDir(self, dirpath):
    path = self.out.Add(*dirpath.split("/"))
    fd = aff4.FACTORY.Create(path, "VFSDirectory", token=self.token)
    fd.Close()

  def CreateFile(self, filepath):
    path = self.out.Add(filepath)
    fd = aff4.FACTORY.Create(path, "VFSMemoryFile", token=self.token)
    fd.Write("some data")
    fd.Close()

  def testExportFile(self):
    """Check we can export a file without errors."""
    with utils.TempDirectory() as tmpdir:
      export_utils.CopyAFF4ToLocal(
          self.out.Add("testfile1"), tmpdir,
          overwrite=True, token=self.token)
      expected_outdir = os.path.join(tmpdir, self.out.Path()[1:])
      self.assertTrue("testfile1" in os.listdir(expected_outdir))

  def testDownloadCollection(self):
    """Check we can export a file without errors."""
    # Create a collection with URNs to some files.
    fd = aff4.FACTORY.Create("aff4:/testcoll", "RDFValueCollection",
                             token=self.token)
    fd.Add(rdfvalue.RDFURN(self.out.Add("testfile1")))
    fd.Add(rdfvalue.StatEntry(aff4path=self.out.Add("testfile2")))
    fd.Close()

    with utils.TempDirectory() as tmpdir:
      export_utils.DownloadCollection("aff4:/testcoll", tmpdir, overwrite=True,
                                      dump_client_info=True, token=self.token,
                                      max_threads=2)
      expected_outdir = os.path.join(tmpdir, self.out.Path()[1:])

      # Check we found both files.
      self.assertTrue("testfile1" in os.listdir(expected_outdir))
      self.assertTrue("testfile2" in os.listdir(expected_outdir))

      # Check we dumped a YAML file to the root of the client.
      expected_rootdir = os.path.join(tmpdir, self.client_id.Basename())
      self.assertTrue("client_info.yaml" in os.listdir(expected_rootdir))

  def testRecursiveDownload(self):
    """Check we can export a file without errors."""
    with utils.TempDirectory() as tmpdir:
      export_utils.RecursiveDownload(
          aff4.FACTORY.Open(self.out, token=self.token),
          tmpdir, overwrite=True)
      expected_outdir = os.path.join(tmpdir, self.out.Path()[1:])
      self.assertTrue("testfile1" in os.listdir(expected_outdir))
      full_outdir = os.path.join(expected_outdir, "testdir1", "testdir2")
      self.assertTrue("testfile4" in os.listdir(full_outdir))


def main(argv):
  test_lib.main(argv)

if __name__ == "__main__":
  conf.StartMain(main)
