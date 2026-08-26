"""Arabic counting, because "3 نافذة" reads wrong.

Arabic numbers agree with the noun in four buckets: singular, dual,
3-10 (plural) and 11+ (back to singular).
"""
from __future__ import annotations

WINDOW = ("نافذة", "نافذتين", "نوافذ", "نافذة")
MONITOR = ("شاشة", "شاشتين", "شاشات", "شاشة")


def count(number: int, forms: tuple[str, str, str, str]) -> str:
    one, two, few, many = forms
    if number == 0:
        return f"مافيش {few}"
    if number == 1:
        return f"{one} واحدة"
    if number == 2:
        return two
    if 3 <= number <= 10:
        return f"{number} {few}"
    return f"{number} {many}"


def windows(number: int) -> str:
    return count(number, WINDOW)


def monitors(number: int) -> str:
    return count(number, MONITOR)
