"""The permission checks hooks.py names, gathered from the modules that hold them."""

from digest.sharing import delivery_note_has_permission, journal_entry_has_permission

__all__ = ["delivery_note_has_permission", "journal_entry_has_permission"]
