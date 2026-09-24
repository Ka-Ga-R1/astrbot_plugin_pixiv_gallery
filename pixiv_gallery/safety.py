"""One content policy shared by search, artist selection and direct IDs."""

from __future__ import annotations

import re

from .config import Settings
from .models import Illustration


def policy_allows(
    work: Illustration, settings: Settings, *, is_private: bool | None = None
) -> bool:
    tags = {re.sub(r"[-_\s]", "", tag).lower() for tag in work.tags if isinstance(tag, str)}
    restriction = (
        work.x_restrict if type(work.x_restrict) is int and work.x_restrict in (0, 1, 2) else None
    )
    # Tags can increase, but never downgrade, a declared restriction.
    if "r18g" in tags:
        restriction = 2
    elif "r18" in tags and restriction != 2:
        restriction = 1
    if restriction is None:
        return not settings.reject_when_safety_check_failed
    if restriction == 0:
        return True
    if restriction == 1 and settings.filter_r18:
        return False
    if restriction == 2 and settings.filter_r18g:
        return False
    if is_private is True:
        return settings.allow_private_r18
    if is_private is False:
        return settings.allow_group_r18
    return False
