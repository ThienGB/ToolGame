import unittest
from unittest.mock import patch

from ld_device_utils import parse_adb_devices_output, parse_ldconsole_list2, refresh_adb_devices, resolve_adb_path


class LdDeviceScanTests(unittest.TestCase):
    def test_parse_ldconsole_list2_with_running_state(self):
        sample = """0,1,2,3,1,4,127.0.0.1:5554
1,1,2,3,1,4,127.0.0.1:5556
"""
        devices = parse_ldconsole_list2(sample)
        self.assertEqual(devices[0]["index"], 0)
        self.assertEqual(devices[0]["serial"], "127.0.0.1:5554")
        self.assertEqual(devices[1]["index"], 1)
        self.assertEqual(devices[1]["serial"], "127.0.0.1:5556")

    def test_parse_ldconsole_list2_with_legacy_format(self):
        sample = """0,0,1,1,0,0,0
1,0,1,1,1,1,1
"""
        devices = parse_ldconsole_list2(sample)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["index"], 1)
        self.assertEqual(devices[0]["serial"], "127.0.0.1:5556")

    def test_resolve_adb_path_from_ldconsole_path(self):
        self.assertEqual(resolve_adb_path(r"C:\LDPlayer\LDPlayer9\ldconsole.exe", "adb.exe"), r"C:\LDPlayer\LDPlayer9\adb.exe")
        self.assertEqual(resolve_adb_path(r"C:\LDPlayer\LDPlayer9\\", "adb.exe"), r"C:\LDPlayer\LDPlayer9\adb.exe")

    def test_parse_adb_devices_output(self):
        output = "List of devices attached\n127.0.0.1:5554\tdevice\n127.0.0.1:5556\toffline\n"
        self.assertEqual(parse_adb_devices_output(output), [("127.0.0.1:5554", "device"), ("127.0.0.1:5556", "offline")])

    @patch("ld_device_utils.time.sleep")
    @patch("ld_device_utils.subprocess.run")
    def test_refresh_adb_devices_retries_and_returns_online_serials(self, mock_run, mock_sleep):
        mock_run.side_effect = [
            unittest.mock.Mock(returncode=0),
            unittest.mock.Mock(returncode=0),
            unittest.mock.Mock(returncode=0),
            unittest.mock.Mock(returncode=0, stdout="List of devices attached\n127.0.0.1:5554\tdevice\n"),
        ]

        devices = refresh_adb_devices("adb.exe", ["127.0.0.1:5554"], attempts=2, delay=0.1)

        self.assertEqual(devices, [("127.0.0.1:5554", "device")])
        self.assertEqual(mock_run.call_count, 4)


if __name__ == "__main__":
    unittest.main()
