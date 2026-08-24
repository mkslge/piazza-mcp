import pytest

from tests.support import assert_sensitive_value_absent


def test_sensitive_value_check_inspects_string_and_repr():
    sentinel = "UNIQUE_PRIVATE_SENTINEL"

    class LeakyString:
        def __str__(self):
            return sentinel

        def __repr__(self):
            return "redacted"

    with pytest.raises(AssertionError):
        assert_sensitive_value_absent(LeakyString(), sentinel)
