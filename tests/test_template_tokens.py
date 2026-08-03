import unittest

from template_tokens import TemplateTokenStore


class FakeClock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class TemplateTokenStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.tokens = iter(["token-1", "token-2", "token-3"])
        self.store = TemplateTokenStore(
            clock=self.clock,
            token_factory=lambda: next(self.tokens),
        )

    def issue(self, *, max_uses: int = 2, ttl_seconds: float = 60) -> str:
        result = self.store.issue(
            "demo.app",
            "schema-1",
            max_uses=max_uses,
            ttl_seconds=ttl_seconds,
        )
        return result["template_token"]

    def reserve(self, token: str, *, max_uses: int = 2, ttl_seconds: float = 60):
        return self.store.reserve(
            token,
            "demo.app",
            "schema-1",
            max_uses=max_uses,
            ttl_seconds=ttl_seconds,
        )

    def test_issue_returns_limits(self) -> None:
        result = self.store.issue(
            "demo.app",
            "schema-1",
            max_uses=50,
            ttl_seconds=12 * 3600,
        )
        self.assertEqual(result["template_token"], "token-1")
        self.assertEqual(result["template_token_max_uses"], 50)
        self.assertTrue(result["template_token_expires_at"].endswith("Z"))

    def test_usage_limit_expires_token(self) -> None:
        token = self.issue()
        for expected_remaining in (1, 0):
            reservation, error = self.reserve(token)
            self.assertIsNone(error)
            result = self.store.commit(token, reservation)
            self.assertEqual(result["template_token_remaining_uses"], expected_remaining)

        reservation, error = self.reserve(token)
        self.assertIsNone(reservation)
        self.assertEqual(error["error_code"], "TEMPLATE_TOKEN_EXHAUSTED")

    def test_time_limit_expires_token_at_boundary(self) -> None:
        token = self.issue(ttl_seconds=10)
        self.clock.value += 10
        reservation, error = self.reserve(token, ttl_seconds=10)
        self.assertIsNone(reservation)
        self.assertEqual(error["error_code"], "TEMPLATE_TOKEN_EXPIRED")

    def test_release_does_not_consume_use(self) -> None:
        token = self.issue(max_uses=1)
        reservation, error = self.reserve(token, max_uses=1)
        self.assertIsNone(error)
        self.store.release(token, reservation)

        second_reservation, second_error = self.reserve(token, max_uses=1)
        self.assertIsNone(second_error)
        self.assertIsNotNone(second_reservation)

    def test_reservations_prevent_concurrent_overuse(self) -> None:
        token = self.issue(max_uses=1)
        reservation, error = self.reserve(token, max_uses=1)
        self.assertIsNone(error)
        self.assertIsNotNone(reservation)

        second_reservation, second_error = self.reserve(token, max_uses=1)
        self.assertIsNone(second_reservation)
        self.assertEqual(second_error["error_code"], "TEMPLATE_TOKEN_EXHAUSTED")

    def test_wrong_template_is_rejected(self) -> None:
        token = self.issue()
        error = self.store.validate(
            token,
            "other.app",
            "schema-1",
            max_uses=2,
            ttl_seconds=60,
        )
        self.assertEqual(error["error_code"], "TEMPLATE_TOKEN_WRONG_TEMPLATE")

    def test_schema_or_policy_change_makes_token_stale(self) -> None:
        token = self.issue()
        schema_error = self.store.validate(
            token,
            "demo.app",
            "schema-2",
            max_uses=2,
            ttl_seconds=60,
        )
        policy_error = self.store.validate(
            token,
            "demo.app",
            "schema-1",
            max_uses=3,
            ttl_seconds=60,
        )
        self.assertEqual(schema_error["error_code"], "TEMPLATE_TOKEN_STALE")
        self.assertEqual(policy_error["error_code"], "TEMPLATE_TOKEN_STALE")

    def test_missing_and_cleared_tokens_are_rejected(self) -> None:
        missing = self.store.validate(
            None,
            "demo.app",
            "schema-1",
            max_uses=2,
            ttl_seconds=60,
        )
        self.assertEqual(missing["error_code"], "TEMPLATE_TOKEN_REQUIRED")

        token = self.issue()
        self.store.clear()
        invalid = self.store.validate(
            token,
            "demo.app",
            "schema-1",
            max_uses=2,
            ttl_seconds=60,
        )
        self.assertEqual(invalid["error_code"], "TEMPLATE_TOKEN_INVALID")


if __name__ == "__main__":
    unittest.main()
