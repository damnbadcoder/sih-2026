from enum import StrEnum


class UserType(StrEnum):
    """Canonical user persona vocabulary.

    Values mirror the frontend ``UserType`` union in
    ``frontend/src/lib/types.ts`` exactly so there is a single shared
    vocabulary; do not introduce a second, incompatible list.
    """

    ORGANISATION = "Organisation"
    GOVERNMENT_AGENCY = "Government Agency"
    INFLUENCER = "Influencer"
    RESEARCHER = "Researcher"
    JOURNALIST = "Journalist"
    INDIVIDUAL = "Individual"
