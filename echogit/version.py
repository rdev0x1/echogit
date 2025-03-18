class Version:
    # Semantic versioning: Major.Minor.Release
    MAJOR = 0  # incremented if protocol is broken
    MINOR = 0  # incremented on feature modification/addition
    RELEASE = 1  # incremented on bug fix and minor update

    @staticmethod
    def __str__():
        return f"{Version.MAJOR}.{Version.MINOR}.{Version.RELEASE}"

    @staticmethod
    def is_compatible(other_version_string):
        """
        Check compatibility between the current version and a peer version string.
        Versions are compatible if they have the same major version.
        """
        try:
            major, _minor, _release = map(int, other_version_string.split('.'))
        except ValueError:
            # If the other version string is invalid, treat it as incompatible
            return False

        # Versions are compatible if the major version is the same
        return Version.MAJOR == major

    @staticmethod
    def full_version():
        """
        Returns the full version as a string.
        """
        return f"{Version.MAJOR}.{Version.MINOR}.{Version.RELEASE}"
