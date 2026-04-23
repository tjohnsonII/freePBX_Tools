import unittest

from webscraper.cli.attach_parsing import normalize_attach_args


class AttachParsingTests(unittest.TestCase):
    def test_attach_port_string(self) -> None:
        attach, host = normalize_attach_args("9222", "127.0.0.1", None)
        self.assertEqual(attach, 9222)
        self.assertEqual(host, "127.0.0.1")

    def test_attach_host_port_string_updates_host(self) -> None:
        attach, host = normalize_attach_args("localhost:9333", "127.0.0.1", None)
        self.assertEqual(attach, 9333)
        self.assertEqual(host, "localhost")

    def test_attach_debugger_wins(self) -> None:
        attach, host = normalize_attach_args("9222", "127.0.0.1", "10.0.0.15:9444")
        self.assertEqual(attach, 9444)
        self.assertEqual(host, "10.0.0.15")

    def test_invalid_attach_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "--attach expected an integer port"):
            normalize_attach_args("not-a-port", "127.0.0.1", None)

    def test_invalid_attach_debugger_requires_host_port(self) -> None:
        with self.assertRaisesRegex(ValueError, "--attach-debugger must be host:port"):
            normalize_attach_args(None, "127.0.0.1", "9222")


if __name__ == "__main__":
    unittest.main()
