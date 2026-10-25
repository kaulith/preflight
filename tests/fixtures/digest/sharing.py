"""Passes the checks on, one of them back to the module it came from, which no code defines."""

from digest.access import journal_entry_has_permission

from .delivery_note import delivery_note_has_permission

__all__ = ["delivery_note_has_permission", "journal_entry_has_permission"]
