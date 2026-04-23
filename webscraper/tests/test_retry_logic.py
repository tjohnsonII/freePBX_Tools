import unittest

from webscraper.scrape.retry_logic import run_with_retry


class RetryLogicTests(unittest.TestCase):
    def test_run_with_retry_eventually_succeeds(self) -> None:
        state = {"count": 0}

        def flaky() -> str:
            state["count"] += 1
            if state["count"] < 3:
                raise RuntimeError("try again")
            return "ok"

        result = run_with_retry(flaky, retries=3, delay_s=0)
        self.assertEqual(result, "ok")
        self.assertEqual(state["count"], 3)


if __name__ == "__main__":
    unittest.main()
