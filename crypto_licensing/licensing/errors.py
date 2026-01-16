class LicensingError( Exception ):
    pass


class LicenseNotFound( LicensingError ):
    pass


class LicenseIncompatibility( LicensingError ):
    """Something is wrong with the License, or supporting infrastructure."""
    pass


class LicenseDuplicated( LicenseIncompatibility ):
    """A duplicate but incompatible License was found."""
    pass


class LicenseDisjoint( LicenseIncompatibility ):
    """When combining Licenses, we may want to take special action when it is detected that the
    Grants containing Timespans that are disjoint, eg. use the most recent Grant.

    """
    pass


class NotLicensed( LicensingError ):
    pass


class RegistrationError( LicensingError ):
    pass


class NotRegistered( RegistrationError ):
    pass


class DKIMError( LicensingError ):
    pass
