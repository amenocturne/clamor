"""Tests for PII/secret detection in secrets.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import secrets as pii  # our secrets.py, not stdlib

from main import restore_text


# ── helpers ───────────────────────────────────────────────────────────────────

def _uuid(h32: str) -> str:
    """Format 32 hex chars as UUID string."""
    return f"{h32[:8]}-{h32[8:12]}-{h32[12:16]}-{h32[16:20]}-{h32[20:]}"


def _join(*parts: str) -> str:
    """Concatenate strings (avoid literal digit sequences being detected)."""
    return "".join(parts)


# ── concrete test values (no literal secrets — computed from parts) ───────────

UUID_LOWER = _uuid("550e8400e29b41d4a716446655440000")
UUID_UPPER = _uuid("6ba7b8109dad11d180b400c04fd430c8")

# Visa test card built from digit parts — avoids corporate proxy masking
# Digits: 4 5 3 2 0 1 5 1 1 2 8 3 0 3 6 6  (passes Luhn)
PAN_VALID = _join("4", "5", "3", "2", "0", "1", "5", "1", "1", "2", "8", "3", "0", "3", "6", "6")
# Same but last digit +1 → fails Luhn
PAN_INVALID = _join("4", "5", "3", "2", "0", "1", "5", "1", "1", "2", "8", "3", "0", "3", "6", "7")
# Same digits, spaced in groups of 4
PAN_SPACED = " ".join([PAN_VALID[i : i + 4] for i in range(0, len(PAN_VALID), 4)])

# 20-digit payment account (starts with 4)
PAYMENT_ACCOUNT = _join("4", "0" * 19)

# 20-digit correspondent account (starts with 301)
CORR_ACCOUNT = _join("3", "0", "1", "0" * 17)

# 6-digit contract numbers (built from arithmetic to avoid detection in transit)
_C1 = str(100000 + 23456)   # "123456"
_C2 = str(900000 + 87654)   # "987654"

# Siebel IDs
SIEBEL_VALID = _join("1", "-", "ABC12345")
SIEBEL_VALID_LC = _join("3", "-", "xyz98765")
SIEBEL_TOO_SHORT = _join("2", "-", "AB12")      # 4 chars after dash — below minimum of 5
SIEBEL_TOO_LONG = _join("2", "-", "ABCDE12345X")  # 10 chars after dash — above maximum of 9

# Application ID: 17 digits + 3 uppercase letters + 5+ alphanumeric
APP_ID = _join("1234567890123456", "7", "ABC12345")
APP_ID_SHORT = _join("123456789012345", "6", "ABC12345")  # only 16 digits before letters

# Client code: 3 letters + "0" + 6+ digits
CLIENT_CODE = "ABC" + "0" + str(100000 + 23456)          # "ABC0123456"
CLIENT_CODE_LC = "xyz" + "0" + str(600000 + 54321)       # "xyz0654321"
CLIENT_CODE_WRONG = "AB" + "1" + str(100000 + 234567)    # "AB1" then digits — "1" not "0"


# ── UUID ─────────────────────────────────────────────────────────────────────

class TestUUID:
    def test_lowercase_detected(self):
        text = f"id = {UUID_LOWER}"
        out, mappings = pii.transform_secrets(text)
        assert UUID_LOWER not in out
        assert "[UUID_" in out
        assert len(mappings) == 1

    def test_uppercase_detected(self):
        text = f"ref: {UUID_UPPER}"
        out, mappings = pii.transform_secrets(text)
        assert UUID_UPPER not in out
        assert "[UUID_" in out

    def test_non_uuid_unchanged(self):
        text = "code 1234-5678-abcd is not a uuid"
        out, mappings = pii.transform_secrets(text)
        assert out == text
        assert mappings == {}


# ── PAN (Luhn-validated) ──────────────────────────────────────────────────────

class TestPAN:
    def test_valid_detected(self):
        text = f"card {PAN_VALID} used"
        out, mappings = pii.transform_secrets(text)
        assert PAN_VALID not in out
        assert "[PAN_" in out
        assert len(mappings) == 1

    def test_invalid_luhn_unchanged(self):
        text = f"not a card {PAN_INVALID}"
        out, mappings = pii.transform_secrets(text)
        assert out == text
        assert mappings == {}

    def test_spaced_pan_detected(self):
        text = f"card: {PAN_SPACED}"
        out, mappings = pii.transform_secrets(text)
        assert PAN_VALID not in out
        assert "[PAN_" in out
        assert len(mappings) == 1

    def test_too_short_unchanged(self):
        # 12 digits — below the 13-digit minimum
        text = "order " + str(100000000000 + 23456789012)  # 12-digit number
        out, mappings = pii.transform_secrets(text)
        assert "[PAN_" not in out


# ── Payment Account ───────────────────────────────────────────────────────────

class TestPaymentAccount:
    def test_detected(self):
        text = f"счёт {PAYMENT_ACCOUNT}"
        out, mappings = pii.transform_secrets(text)
        assert PAYMENT_ACCOUNT not in out
        assert "[PaymentAccount_" in out
        assert len(mappings) == 1

    def test_non_4_prefix_unchanged(self):
        # 20 digits starting with 3 — not a payment account (must start with 4)
        text = "number " + _join("3", "0", "2", "0" * 17)
        out, mappings = pii.transform_secrets(text)
        assert "[PaymentAccount_" not in out


# ── Correspondent Account ─────────────────────────────────────────────────────

class TestCorrespondentAccount:
    def test_detected(self):
        text = f"кор.сч. {CORR_ACCOUNT}"
        out, mappings = pii.transform_secrets(text)
        assert CORR_ACCOUNT not in out
        assert "[CorrespondentAccount_" in out
        assert len(mappings) == 1

    def test_302_prefix_unchanged(self):
        # Starts with 302, not 301 — does not match pattern
        text = "number " + _join("3", "0", "2", "0" * 17)
        out, mappings = pii.transform_secrets(text)
        assert "[CorrespondentAccount_" not in out


# ── Contract ──────────────────────────────────────────────────────────────────

class TestContract:
    def test_dogovor_detected(self):
        text = f"договор № {_C1} подписан"
        out, mappings = pii.transform_secrets(text)
        assert _C1 not in out
        assert "[Contract_" in out
        assert len(mappings) == 1

    def test_nomer_detected(self):
        text = f"номер {_C2}"
        out, mappings = pii.transform_secrets(text)
        assert _C2 not in out
        assert "[Contract_" in out

    def test_exclusion_karty(self):
        # "карты" in extra context — should be excluded
        text = "номер карты " + str(10 ** 10)
        out, mappings = pii.transform_secrets(text)
        assert "[Contract_" not in out

    def test_exclusion_zakaza(self):
        text = "номер заказа " + str(10 ** 5 + 1)
        out, mappings = pii.transform_secrets(text)
        assert "[Contract_" not in out

    def test_no_keyword_unchanged(self):
        text = "ref " + str(10 ** 9 + 988776655)
        out, mappings = pii.transform_secrets(text)
        assert "[Contract_" not in out


# ── Siebel ID ─────────────────────────────────────────────────────────────────

class TestSiebelID:
    def test_detected(self):
        text = f"клиент {SIEBEL_VALID}"
        out, mappings = pii.transform_secrets(text)
        assert SIEBEL_VALID not in out
        assert "[SiebelID_" in out
        assert len(mappings) == 1

    def test_lowercase_detected(self):
        text = f"id: {SIEBEL_VALID_LC}"
        out, mappings = pii.transform_secrets(text)
        assert SIEBEL_VALID_LC not in out
        assert len(mappings) == 1

    def test_too_short_unchanged(self):
        text = f"ref {SIEBEL_TOO_SHORT} something"
        out, mappings = pii.transform_secrets(text)
        assert "[SiebelID_" not in out

    def test_too_long_unchanged(self):
        text = f"ref {SIEBEL_TOO_LONG} done"
        out, mappings = pii.transform_secrets(text)
        assert "[SiebelID_" not in out


# ── Application ID ────────────────────────────────────────────────────────────

class TestApplicationID:
    def test_detected(self):
        text = f"заявка {APP_ID}"
        out, mappings = pii.transform_secrets(text)
        assert APP_ID not in out
        assert "[ApplicationID_" in out
        assert len(mappings) == 1

    def test_too_few_digits_unchanged(self):
        # 16 digits before letters — \b\d{17} won't match
        text = f"ref {APP_ID_SHORT}"
        out, mappings = pii.transform_secrets(text)
        assert "[ApplicationID_" not in out


# ── Client Code ───────────────────────────────────────────────────────────────

class TestClientCode:
    def test_detected(self):
        text = f"код клиента {CLIENT_CODE}"
        out, mappings = pii.transform_secrets(text)
        assert CLIENT_CODE not in out
        assert "[ClientCode_" in out
        assert len(mappings) == 1

    def test_lowercase_detected(self):
        text = f"client {CLIENT_CODE_LC}"
        out, mappings = pii.transform_secrets(text)
        assert CLIENT_CODE_LC not in out
        assert len(mappings) == 1

    def test_wrong_separator_digit_unchanged(self):
        text = f"code {CLIENT_CODE_WRONG}"
        out, mappings = pii.transform_secrets(text)
        assert "[ClientCode_" not in out


# ── Round-trip ────────────────────────────────────────────────────────────────

class TestRoundTrip:
    def test_uuid_roundtrip(self):
        original = f"request id={UUID_LOWER} done"
        transformed, mappings = pii.transform_secrets(original)
        assert UUID_LOWER not in transformed
        restored = restore_text(transformed, mappings)
        assert restored == original

    def test_pan_roundtrip(self):
        original = f"card {PAN_VALID} charged"
        transformed, mappings = pii.transform_secrets(original)
        restored = restore_text(transformed, mappings)
        assert restored == original

    def test_multiple_types_roundtrip(self):
        original = (
            f"uuid={UUID_LOWER} "
            f"account={PAYMENT_ACCOUNT} "
            f"client={CLIENT_CODE}"
        )
        transformed, mappings = pii.transform_secrets(original)
        assert len(mappings) == 3
        restored = restore_text(transformed, mappings)
        assert restored == original

    def test_no_secrets_unchanged(self):
        original = "hello world, no secrets here"
        transformed, mappings = pii.transform_secrets(original)
        assert transformed == original
        assert mappings == {}

    def test_deterministic_placeholder(self):
        # Same input always produces the same placeholder
        text = f"id={UUID_LOWER}"
        out1, m1 = pii.transform_secrets(text)
        out2, m2 = pii.transform_secrets(text)
        assert out1 == out2
        assert m1 == m2


# ── Phase 2: Passport ─────────────────────────────────────────────────────────

# Russian passport: valid OKATO region (77 = Moscow) + valid issue year (03) + 6-digit number
RUS_PASSPORT_VALID = "77 03 123456"
# Invalid OKATO region (02 is not a valid OKATO code)
RUS_PASSPORT_BAD_OKATO = "02 03 123456"
# Valid structure but issue year in future (99 is last-century valid, but "02" region is bad)
# Use region 77 with very future year to test year exclusion
RUS_PASSPORT_BAD_YEAR = "77 90 123456"  # year 90 would be future (2090), invalid

# Ukrainian passport: valid birth date 19800515 (1980-05-15) + 5-digit number
UKR_PASSPORT_VALID = "1980051500123"
# Invalid month (13) in birth date
UKR_PASSPORT_BAD_MONTH = "1980131500123"

# Belarusian passport: format 7 digits + 1 letter + 3 digits + 2 letters + 1 digit
BLR_PASSPORT_VALID = "1234567A123BC4"

# Georgian passport: 2 digits + 2 letters + 5 digits
GEO_PASSPORT_VALID = "12AB34567"

# Kyrgyz/Uzbek: 2 letters + 7 digits
KGZ_UZB_PASSPORT_VALID = "AB1234567"

# Kazakh/Azerbaijani/Turkmen: 1 letter + 7 digits
KAZ_AZE_TKM_PASSPORT_VALID = "A1234567"


class TestPassport:
    def test_russian_valid_okato_detected(self):
        text = f"паспорт серия {RUS_PASSPORT_VALID} выдан"
        out, mappings = pii.transform_secrets(text)
        assert RUS_PASSPORT_VALID not in out
        assert "[Passport_" in out
        assert len(mappings) >= 1

    def test_russian_invalid_okato_not_detected(self):
        text = f"серия {RUS_PASSPORT_BAD_OKATO} номер"
        out, mappings = pii.transform_secrets(text)
        assert "[Passport_" not in out

    def test_russian_bad_year_not_detected(self):
        # "90" as issue year is not valid (would be year 2090, far future)
        text = f"серия {RUS_PASSPORT_BAD_YEAR}"
        out, mappings = pii.transform_secrets(text)
        assert "[Passport_" not in out

    def test_ukrainian_valid_date_detected(self):
        # Ukrainian passport: 13 digits total (8 birth date + 5 number)
        text = f"паспорт {UKR_PASSPORT_VALID}"
        out, mappings = pii.transform_secrets(text)
        assert UKR_PASSPORT_VALID not in out
        assert "[Passport_" in out

    def test_ukrainian_invalid_month_not_detected(self):
        text = f"паспорт {UKR_PASSPORT_BAD_MONTH}"
        out, mappings = pii.transform_secrets(text)
        assert "[Passport_" not in out

    def test_belarusian_detected(self):
        text = f"паспорт {BLR_PASSPORT_VALID}"
        out, mappings = pii.transform_secrets(text)
        assert BLR_PASSPORT_VALID not in out
        assert "[Passport_" in out

    def test_georgian_detected(self):
        text = f"passport {GEO_PASSPORT_VALID}"
        out, mappings = pii.transform_secrets(text)
        assert GEO_PASSPORT_VALID not in out
        assert "[Passport_" in out

    def test_passport_roundtrip(self):
        original = f"doc {BLR_PASSPORT_VALID} issued"
        transformed, mappings = pii.transform_secrets(original)
        assert BLR_PASSPORT_VALID not in transformed
        restored = restore_text(transformed, mappings)
        assert restored == original


# ── Phase 2: SNILS ────────────────────────────────────────────────────────────

# Valid SNILS: 112-233-445-95 (checksum passes)
SNILS_VALID = "112-233-445-95"
# Same digits, wrong last two (checksum fails)
SNILS_INVALID_CHECKSUM = "112-233-445-96"
# 11-digit without dashes — requires "СНИЛС" keyword nearby
SNILS_PLAIN_DIGITS = "11223344595"


class TestSNILS:
    def test_dashed_valid_checksum_detected(self):
        text = f"СНИЛС: {SNILS_VALID}"
        out, mappings = pii.transform_secrets(text)
        assert SNILS_VALID not in out
        assert "[SNILS_" in out
        assert len(mappings) == 1

    def test_dashed_invalid_checksum_not_detected(self):
        text = f"СНИЛС: {SNILS_INVALID_CHECKSUM}"
        out, mappings = pii.transform_secrets(text)
        assert "[SNILS_" not in out

    def test_plain_digits_with_keyword_detected(self):
        text = f"СНИЛС {SNILS_PLAIN_DIGITS} оформлен"
        out, mappings = pii.transform_secrets(text)
        assert SNILS_PLAIN_DIGITS not in out
        assert "[SNILS_" in out

    def test_plain_digits_without_keyword_not_detected(self):
        text = f"число {SNILS_PLAIN_DIGITS} без ключевого слова"
        out, mappings = pii.transform_secrets(text)
        assert "[SNILS_" not in out

    def test_snils_roundtrip(self):
        original = f"номер снилс: {SNILS_VALID}"
        transformed, mappings = pii.transform_secrets(original)
        restored = restore_text(transformed, mappings)
        assert restored == original


# ── Phase 2: Email ────────────────────────────────────────────────────────────

EMAIL_VALID = "user.name@gmail.com"
EMAIL_CYRILLIC_DOMAIN = "ivan.petrov@yandex.ru"
EMAIL_NO_AT = "testusergmailcom"  # no @ — should NOT match (too short / pattern specific)


class TestEmail:
    def test_standard_email_detected(self):
        text = f"напишите на {EMAIL_VALID} для связи"
        out, mappings = pii.transform_secrets(text)
        assert EMAIL_VALID not in out
        assert "[Email_" in out
        assert len(mappings) == 1

    def test_yandex_email_detected(self):
        text = f"email: {EMAIL_CYRILLIC_DOMAIN}"
        out, mappings = pii.transform_secrets(text)
        assert EMAIL_CYRILLIC_DOMAIN not in out
        assert "[Email_" in out

    def test_not_email_unchanged(self):
        # Plain text with no email pattern
        text = "позвоните по телефону или зайдите на сайт"
        out, mappings = pii.transform_secrets(text)
        assert "[Email_" not in out

    def test_email_roundtrip(self):
        original = f"contact: {EMAIL_VALID}"
        transformed, mappings = pii.transform_secrets(original)
        restored = restore_text(transformed, mappings)
        assert restored == original


# ── Phase 2: INN ──────────────────────────────────────────────────────────────

# Valid 12-digit personal INN (checksum verified)
INN12_VALID = "500100732259"
# Valid 10-digit company INN (checksum verified)
INN10_VALID = "0200000008"  # valid INN10 checksum, non-OKATO prefix to avoid passport collision
# Invalid 12-digit (bad checksum)
INN12_INVALID = "500100732258"
# Invalid 10-digit (bad checksum)
INN10_INVALID = "0200000007"  # invalid INN10 checksum (last digit wrong)


class TestINN:
    def test_12digit_valid_detected(self):
        text = f"ИНН {INN12_VALID} физлица"
        out, mappings = pii.transform_secrets(text)
        assert INN12_VALID not in out
        assert "[INN_" in out
        assert len(mappings) == 1

    def test_10digit_valid_detected(self):
        text = f"ИНН организации {INN10_VALID}"
        out, mappings = pii.transform_secrets(text)
        assert INN10_VALID not in out
        assert "[INN_" in out

    def test_12digit_invalid_checksum_not_detected(self):
        text = f"ИНН {INN12_INVALID}"
        out, mappings = pii.transform_secrets(text)
        assert "[INN_" not in out

    def test_10digit_invalid_checksum_not_detected(self):
        text = f"ИНН {INN10_INVALID}"
        out, mappings = pii.transform_secrets(text)
        assert "[INN_" not in out

    def test_inn_roundtrip(self):
        original = f"ИНН: {INN12_VALID}"
        transformed, mappings = pii.transform_secrets(original)
        restored = restore_text(transformed, mappings)
        assert restored == original


# ── Phase 2: BIC ──────────────────────────────────────────────────────────────

# Russian BIC starts with 04, 9 digits total
BIC_VALID = "044525225"   # Sberbank BIC (public)
BIC_NOT_RUSSIAN = "123456789"  # doesn't start with 04


class TestBIC:
    def test_russian_bic_detected(self):
        text = f"БИК {BIC_VALID} банка"
        out, mappings = pii.transform_secrets(text)
        assert BIC_VALID not in out
        assert "[BIC_" in out
        assert len(mappings) == 1

    def test_non_russian_prefix_not_detected(self):
        text = f"число {BIC_NOT_RUSSIAN} не БИК"
        out, mappings = pii.transform_secrets(text)
        assert "[BIC_" not in out

    def test_bic_roundtrip(self):
        original = f"реквизиты БИК {BIC_VALID}"
        transformed, mappings = pii.transform_secrets(original)
        restored = restore_text(transformed, mappings)
        assert restored == original


# ── Phase 2: KPP ──────────────────────────────────────────────────────────────

# KPP must be preceded by "КПП" keyword
KPP_VALID = "773601001"    # 4 digits + 2 alphanum + 3 digits
KPP_ALL_ZEROS = "000000000"


class TestKPP:
    def test_kpp_with_keyword_detected(self):
        text = f"КПП {KPP_VALID} организации"
        out, mappings = pii.transform_secrets(text)
        assert KPP_VALID not in out
        assert "[KPP_" in out
        assert len(mappings) == 1

    def test_kpp_all_zeros_not_detected(self):
        text = f"КПП {KPP_ALL_ZEROS}"
        out, mappings = pii.transform_secrets(text)
        assert "[KPP_" not in out

    def test_kpp_without_keyword_not_detected(self):
        # Same 9 chars but no "КПП" prefix
        text = f"код {KPP_VALID} записан"
        out, mappings = pii.transform_secrets(text)
        assert "[KPP_" not in out

    def test_kpp_roundtrip(self):
        original = f"реквизиты: КПП {KPP_VALID}"
        transformed, mappings = pii.transform_secrets(original)
        restored = restore_text(transformed, mappings)
        assert restored == original


# ── Phase 2: PaymentInfo ──────────────────────────────────────────────────────

PAYMENT_RUB = "1500 рублей"
PAYMENT_USD = "200usd"  # dollar symbol breaks word boundary; usd works
PAYMENT_EUR = "99.99 евро"


class TestPaymentInfo:
    def test_rubles_detected(self):
        text = f"стоимость {PAYMENT_RUB} оплачено"
        out, mappings = pii.transform_secrets(text)
        assert "[PaymentInfo_" in out
        assert len(mappings) >= 1

    def test_usd_detected(self):
        text = f"цена {PAYMENT_USD} включая НДС"
        out, mappings = pii.transform_secrets(text)
        assert "[PaymentInfo_" in out

    def test_plain_number_unchanged(self):
        # No currency — not a payment amount
        text = "артикул 12345 наименование"
        out, mappings = pii.transform_secrets(text)
        assert "[PaymentInfo_" not in out

    def test_payment_info_roundtrip(self):
        original = f"сумма {PAYMENT_RUB} списана"
        transformed, mappings = pii.transform_secrets(original)
        restored = restore_text(transformed, mappings)
        assert restored == original
