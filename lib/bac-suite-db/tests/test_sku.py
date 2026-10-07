# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from bac_suite_db.sku import Sku, SkuError, is_sku, parse_sku, validate_sku

VALID = {
    "bac-dev-kit-2u-v1r1": ("dev", "kit", "2u", "v1r1", None),
    "bac-dev-eps-main-board-v2r2": ("dev", "eps", "main-board", "v2r2", None),
    "bac-edu-kit-1u-v1r1": ("edu", "kit", "1u", "v1r1", None),
    "bac-edu-kit-1.5u-v2r4": ("edu", "kit", "1.5u", "v2r4", None),
    "bac-dev-adc-magnetorquer-xy-2u-v2r1.1": ("dev", "adc", "magnetorquer-xy-2u", "v2r1.1", None),
    "bac-flight-kit-2u-v1r0-exolaunch": ("flight", "kit", "2u", "v1r0", "exolaunch"),
    "bac-merch-shirt-galaxy-v1r0-eu": ("merch", "shirt", "galaxy", "v1r0", "eu"),
    "bac-dev-eps-main-board-v2r2-b": ("dev", "eps", "main-board", "v2r2", "b"),
    "bac-dev-eps-main-board-v2r2-hdr": ("dev", "eps", "main-board", "v2r2", "hdr"),
    "bac-dev-eps-buck-v1r1-no-hdr": ("dev", "eps", "buck", "v1r1", "no-hdr"),
}

INVALID = [
    "BAC-HW-KIT-0001-R1",  # the pre-1.4.0 scheme
    "bac-dev-kit-2U-v1r1",  # uppercase
    "bac-dev-kit-2u",  # no version string
    "bac-dev-kit-2u-v1",  # revision missing
    "bac-dev-kit-v1r1",  # name missing: only three fields before the version
    "bac-dev-kit-2u-v1r1-",  # trailing hyphen
    "bac-dev-kit_2u-v1r1",  # underscore
    "bac-dev-kit-1..5u-v1r1",  # double dot
    "bac-dev-kit-.5u-v1r1",  # leading dot
    "bac-dev-kit-2u-v1r1-B",  # uppercase variant
    "dev-kit-2u-v1r1",  # prefix missing
    "",
]


@pytest.mark.parametrize(("sku", "fields"), list(VALID.items()))
def test_valid_skus_parse_into_fields(sku, fields):
    parsed = parse_sku(sku)
    assert (parsed.cat, parsed.sub, parsed.name, parsed.version, parsed.variant) == fields
    assert str(parsed) == sku
    assert validate_sku(sku) == sku
    assert is_sku(sku)


@pytest.mark.parametrize("sku", INVALID)
def test_invalid_skus_raise(sku):
    assert not is_sku(sku)
    with pytest.raises(SkuError) as info:
        parse_sku(sku)
    assert info.value.exit_code == 1
    assert info.value.detail


@pytest.mark.parametrize(
    ("sku", "reason"),
    [("bac-dev-kit-2U-v1r1", "lowercase"), ("dev-kit-2u-v1r1", "prefix"), ("bac-dev-kit-2u", "version string")],
)
def test_reasons_name_the_rule(sku, reason):
    with pytest.raises(SkuError) as info:
        parse_sku(sku)
    assert reason in info.value.detail


def test_last_version_token_anchors_the_parse():
    parsed = parse_sku("bac-dev-kit-a-v1r1-x-v2r2")
    assert parsed.name == "a-v1r1-x"
    assert parsed.version == "v2r2"
    assert parsed.variant is None


def test_whitespace_is_tolerated_around_the_sku():
    assert parse_sku("  bac-dev-kit-2u-v1r1\n") == Sku("dev", "kit", "2u", "v1r1")
