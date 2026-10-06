"""Who can access what: token SIDs for a user, evaluated against folder ACLs."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..acl.evaluate import BASELINE_SIDS
from ..config import settings
from ..models import GroupMember


def baseline_sids_for(user_sid: str) -> set[str]:
    sids = set(BASELINE_SIDS) | set(settings.extra_baseline_sids)
    # Domain Users (RID 513) is the primary group, which LDAP group expansion
    # doesn't return; every user of a domain belongs to it.
    domain, _, rid = user_sid.rpartition("-")
    if domain.startswith("S-1-5-21-") and rid.isdigit():
        sids.add(f"{domain}-513")
    return sids


def token_sids(db: Session, user_sid: str) -> set[str]:
    """The SIDs Windows would put in this user's token, limited to groups seen in ACLs."""
    groups = set(db.scalars(select(GroupMember.group_sid).where(GroupMember.member_sid == user_sid)))
    return {user_sid} | baseline_sids_for(user_sid) | groups
