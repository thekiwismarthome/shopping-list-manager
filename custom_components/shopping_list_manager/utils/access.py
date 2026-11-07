"""Who may see a list or loyalty card. No Home Assistant imports, so it is easy to test.

An item (list or card) has:
  owner_id        the creating user; None means it is visible to everyone (legacy "shared" items)
  group_id        a household the item belongs to (only meaningful when owner_id is set)
  allowed_users   extra individual users it is shared with
  allowed_groups  extra groups it is shared with

A user can see an item when any of these is true:
  - they are an admin
  - the item is visible to everyone (no owner)
  - they own it
  - they are in allowed_users
  - they belong to its group_id
  - they belong to any group in allowed_groups
"""
from __future__ import annotations

from typing import Iterable, Optional, Set


def can_access(
    owner_id: Optional[str],
    group_id: Optional[str],
    allowed_users: Optional[Iterable[str]],
    allowed_groups: Optional[Iterable[str]],
    user_id: Optional[str],
    is_admin: bool,
    user_group_ids: Set[str],
) -> bool:
    """Return True if the user may see (and work in) the item."""
    if owner_id is None:
        return True
    if user_id is None:
        return False
    if is_admin or owner_id == user_id:
        return True
    if user_id in (allowed_users or []):
        return True
    if group_id and group_id in user_group_ids:
        return True
    return any(g in user_group_ids for g in (allowed_groups or []))


def can_manage(owner_id: Optional[str], user_id: Optional[str], is_admin: bool) -> bool:
    """Return True if the user may rename, delete or change sharing on the item.

    Only the owner or an admin may. Items with no owner (visible to everyone) can be
    managed by anyone, as before groups existed.
    """
    if owner_id is None:
        return True
    return bool(user_id) and (is_admin or owner_id == user_id)
