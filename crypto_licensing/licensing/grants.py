# -*- coding: utf-8 -*-

#
# Crypto-licensing -- Cryptographically signed licensing, w/ Cryptocurrency payments
#
# Copyright (c) 2022, Dominion Research & Development Corp.
#
# Crypto-licensing is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.  It is also available under alternative (eg. Commercial)
# licenses, at your option.  See the LICENSE file at the top of the source tree.
#
# It is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
import logging
import datetime
import json

from enum		import Enum

from .errors		import (
    LicenseIncompatibility, LicenseDisjoint
)
from .serializable	import Serializable

from ..misc		import (
    type_num_base, type_str_base, is_mapping, is_listlike,
    parse_datetime, parse_seconds, Timestamp, Duration,
    into_str,
)

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( "grants" )


def into_str_UTC( ts, tzinfo=Timestamp.UTC ):
    if ts is not None:
        return ts.render( tzinfo=tzinfo, ms=False, tzdetail=True )


def into_str_LOC( ts ):
    return into_str_UTC( ts, tzinfo=Timestamp.LOC )


def overlap_intersect( start, length, other ):
    """Accepts a start/length, and a Timespan (something w/ start and length), and compute the
    intersecting start/length, and its begin and (if known) ended timestamps.

        start,length,begun,ended = overlap_intersect( start, length, other )

    A start/Timespan w/ None for length is assumed to endure from its start with no time limit.

    """
    other			= into_Timespan( other )
    # Detect the situation where there is no computable overlap, and start, length is defined by one
    # pair or the other.
    if start is None:
        # This license has no defined start time (it is perpetual); other license determines
        assert length is None, "Cannot specify a length without a start timestamp"
        if other.start is None:
            # Neither specifies start at a defined time
            assert other.length is None, "Cannot specify a length without a start timestamp"
            return None,None,None,None
        if other.length is None:
            return other.start,other.length,other.start,None
        return other.start,other.length,other.start,other.start + other.length
    elif other.start is None:
        assert other.length is None, "Cannot specify a length without a start timestamp"
        if length is None:
            return start,length,start,None
        return start,length,start,start + length

    # Both have defined start times; begun defines beginning of potential overlap If the computed
    # ended time is <= begun, then there is no (zero) overlap!
    begun 		= max( start, other.start )
    ended		= None
    if length is None and other.length is None:
        # But neither have duration
        return start,length,begun,None

    # At least one length; ended is computable, as well as the overlap start/length
    if other.length is None:
        ended		= start + length
    elif length is None:
        ended		= other.start + other.length
    else:
        ended		= min( start + length, other.start + other.length )
    start		= begun
    length		= Duration( 0 if ended <= begun else ended - begun )
    return start,length,begun,ended


class Timespan( Serializable ):
    """A time period, w/ a start and optionally a length.  An "empty" (0 length) Timespan may result
    from a failed intersection.

    """
    __slots__			= (
        'start', 'length'
    )
    serializers			= dict(
        start		= into_str_UTC,
        length		= into_str,
    )

    @property
    def end( self ):
        return None if self.start is None or self.length is None else self.start + self.length

    def empty( self ):
        return self.length == 0  # Note: None != 0, in both Python 2 and 3

    def __nonzero__( self ):
        return not self.empty()
    __bool__			= __nonzero__  # Python3

    def __repr__( self ):
        return (
            '<'
            + (
                (
                    repr( self.start )
                    + ' - '
                    + repr( self.end )
                    + ' = '
                ) if log.isEnabledFor( logging.DEBUG ) else ''
            )
            + self.__class__.__name__
            + '(' + repr(str( self.start ))
            + ',' + repr(str( self.length ))
            + ')>'
        )

    def __init__(
        self,
        start		= None,
        length		= None,
        **kwds
    ):
        """A License usually has a timespan of a start timestamp and (optional) duration length.
        These cannot exceed the timespan of any License dependencies.  First, get any supplied start
        time as a timestamp, and any duration length as a number of seconds.

        A Timespan with a None start is assumed to be perpetual, and with a None length is assumed
        to be perpetual from that start time.

        """
        self.start		= into_Timestamp( start )
        self.length		= into_Duration( length )
        super( Timespan, self ).__init__( **kwds )

        assert self.length is None or self.start is not None, \
            "Invalid Timespan; must have a start time if length specified"

    def __contains__( self, other ):
        """True iff we fully encompasses the other Timespan.

        If 'other in self' is False, we know (at least) that self.start is not None, because the
        full perpetual (no start or length) Timespan contains any other Timespan.

        If 'other in self' and 'self in other' are both False, we know that both .start are
        non-None, and at least one .length is non-None -- so at least self.end or other.end is
        finite.

        """
        return self.start is None or (
            other.start is not None and other.start >= self.start and (
                self.end is None or (
                    other.end is not None and other.end <= self.end
                )
            )
        )

    def intersection( self, *others ):
        start			= self.start
        length			= self.length
        for other in others:
            start,length,begun,ended = overlap_intersect( start, length, other )
            if length is not None and length.total_seconds() == 0:
                # We've reached a point where there is no overlap with some other Timespan, and our
                # intersection is empty.  Return an empty Timespan (start time irrelevant, but
                # cannot be None)
                return Timespan( start, 0 )
        return Timespan( start, length )

    def adjacent( self, other ):
        if other in self:
            return True
        if self in other:
            return True
        assert self.end is not None or other.end is not None, \
            "Either {} or {} should have been non-perpetual".format( repr( self ), repr( other ))
        if self.length is not None and other.start <= self.end <= other.end:
            return True
        if other.length is not None and self.start <= other.end <= self.end:
            return True
        return False

    def union( self, *others ):
        """Successively check for intersection or adjacency, expanding if possible, until there is
        no intersection or adjacency with any remaining Timespan.  Each time we integrate another
        Timespan, we have to recompute its union with all other Timespans, because they now may be
        adjacent.

        """
        for i,other in enumerate( others ):
            if self.adjacent( other ):
                break
        else:
            # We completed without incorporating at detecting one intersecting/adjacent Timespan.  Done.
            log.debug( "union: {} doesn't adjoin {}".format( repr( self ), ', '.join( map( repr, others ))))
            return self
        # We broke out of the loop, after detecting an overlap/intersection with the i'th Timespan;
        # compute the (now larger) union with the remaining others.
        if len( others ) > 1:
            return ( self + other ).union( *( others[:i] + others[i+1:] ))
        return ( self + other )

    def __add__( self, other ):
        """Add a Timespan, or something with a .start/.length or ['start'],['length'].  May result in
        no change if there is no intersection/adjacency -- you can't "add" a disjoint Timespan!"""
        other			= into_Timespan( other )
        if other in self:
            return self
        if self in other:
            return other
        if self.length is not None and self.start <= other.start <= self.end:
            if other.length is None:
                return Timespan( self.start, None )
            else:
                return Timespan( self.start, other.end - self.start )
        elif other.length is not None and other.start <= self.start <= other.end:
            if self.length is None:
                return Timespan( other.start, None )
            else:
                return Timespan( other.start, self.end - other.start )
        else:
            log.debug( "{} + {} doesn't overlap".format( repr( self ), repr( other )))
        # Not overlapping/adjacent; no change
        return self


def into_Timestamp( ts ):
    """Convert to a Timestamp, retaining None.

    """
    if ts is not None:
        if isinstance( ts, type_str_base ):
            ts			= parse_datetime( ts )
        if isinstance( ts, datetime.datetime ):
            ts			= Timestamp( ts )
        assert isinstance( ts, Timestamp )
    return ts


def into_Duration( dur ):
    """Convert to a duration, retaining None"""
    if dur is not None:
        if not isinstance( dur, Duration ):
            dur			= parse_seconds( dur )
            assert isinstance( dur, (int, float) )
            dur			= Duration( dur )
    return dur


def into_Timespan( timespan ):
    """Convert to a Timespan, retaining None.  Expects a Timespan, or a JSON string, object or
    mapping or sequence containing start, length."""
    if timespan is not None:
        if not isinstance( timespan, Timespan ):
            if isinstance( timespan, type_str_base ):
                timespan	= json.loads( timespan )
            if hasattr( timespan, 'start' ) and hasattr( timespan, 'length' ):
                timespan	= dict( start = timespan.start, length = timespan.length )
            if is_mapping( timespan ) and set( ('start', 'length') ) <= set( timespan.keys() ):
                timespan	= dict( start = timespan['start'], length = timespan['length'] )
            # Finally, must be dict or sequence for constructing dict w/ start, length
            timespan		= Timespan( **dict( timespan ))
    return timespan


def maybe_Timespan( timespan ):
    """See if something may be a Timespan; return passed-thru None, or Exception on failure.

    """
    try:
        timespan		= into_Timespan( timespan )
    except Exception as exc:
        timespan		= exc
    return timespan


def into_Grant( grant, _from=None ):
    """Convert to a Grant, retaining None.  An empty Grant won't be included in serialize."""
    if grant is not None:
        if not isinstance( grant, Grant ):
            if isinstance( grant, type_str_base ):
                grant		= json.loads( grant )
            grant		= Grant( _from=_from, **dict( grant ))
    return grant


class Grant( Serializable ):
    """The key/value capabilities granted by something like a License.  The first level names
    (typically something related to the product name) usually specify a dict of key/value pairs, and
    all must be serializable to JSON.  The values may themselves be Grants.  Specifically, the first
    layer Grant is usually comprised of a couple of "global" values (eg. { "timespan": <Timespan>,
    "machine": <UUID> }, and the remaining values will themselves be Grants, eg. w/ a ._from
    indicating which LicenseSigned dependency they were initially from.

    The Granted option names cannot be trusted; any License may carry a Grant of any option name
    whatsoever.  So, the License itself must be validated as being issued by an expected author,
    before its Grant of options can be trusted.  When a sub-License modifies a Grant (ie. issues a
    subset of the granted capability to a licensee), it modifies the Grant, but retains the original
    source License in _from.  So, when the grants() are finally delivered to the caller, they can
    confirm that the top-level key (eg. "cpppo-test" = Grant( "Hz" = 100 ),_from=<LicenseSigned>)
    actual came from the expected author (ie. has the correct pubkey).

    Also, some License options granted in sub-Licenses may "accumulate", while others only accrue
    to the direct client of the License.  Each License author must decide this; only their code
    that validates their License knows the semantics of their Grant options.

    We'll use a __dict__ instead of __slots__ to hold the unknown option key/dict pairs.

    Two Licenses containing grants from same Grant group (say, 'cpppo-test') "combine" if they are
    loaded in parallel, but "refine" if they are dependencies.  For example, if I load two Licenses
    with Grant.cpppo-test["Hz"] of 1,000 and 200 respectively, I end up with a total Grant of 1,200
    "Hz".  However, if a License contains a Grant of 200, and has a License in its dependencies that
    grants() 1,000, I receive only the 200 (and it must be <= the dependencies' value).

    The Grant &= Grant operator "refines", the Grant |= Grant "combines".

    Note that combining Timespans between two licenses along with other features may grant
    unexpected results -- extending the time duration of the features granted in one license, into
    to the time duration of another license carrying different features.

    """
    def __init__( self, *args, **kwds ):
        _from			= kwds.pop( '_from', None )  # Python 2 doesn't support mixing keyword args and **kwds
        if args:
            assert len( args ) == 1 and isinstance( args[0], (type_str_base, dict) ) and not kwds, \
                "Grant option cannot be defined w/ multiple or non-str args both args: {args!r} and/or kwds: {kwds!r}".format(
                    args=args, kwds=kwds )
            if isinstance( args[0], type_str_base ):
                kwds		= json.loads( args[0] )
            else:
                kwds		= args[0]
        option			= dict( kwds )
        # Ensure that options only has first-level keys w/ /dicts (actually, the Mapping API),
        # unless _from is provided (indicating this is a sub-Grant).  In other words, an "anonymous"
        # Grant can only contain Grants/dicts.  Anything that specifies a ._from may contain
        # arbitrary key/value pairs; otherwise, .
        if _from is None:
            assert all(
                is_mapping( v ) or isinstance( v, Grant )
                for v in option.values()
            ), "Found non-dict/Grant option(s): {keys}".format(
                keys		= ', '.join(
                    k for k,v in option.items()
                    if not ( is_mapping( v ) or isinstance( v, Grant ))
                )
            )
        self.__dict__.update( option )
        super( Grant, self ).__init__( _from=_from )
        log.debug( "Created {!r}: {}".format( self, self ))

    def empty( self ):
        """Detects if empty, and avoid serialization if so.  This allows someone to accidentally
        define an empty Grant, without changing the signature vs. the same License w/ no Grant.
        Must ignore "hidden" _...  and (in turn) empty keys, so use .keys() So, a Grant containing
        empty Grants and/or keys with value None will be empty.

        """
        for _ in self.keys():
            return False
        return True

    def grants( self, once=None ):
        return self

    def items( self ):
        return self.__dict__.items()

    class Merging( Enum ):
        REFINING	= 0
        COMBINED	= 1

    def merge( self, group, key, value, style=Merging.REFINING ):
        """When a Grant group's key (eg. grant['cpppo-test']['Hz']) is presented with a new value in
        some sub-License, this must be consistent with (a strict subset of) any existing Grant from
        any License dependencies: you can't provide a sub-Licensee with "more" than your License
        dependencies provide.

        For example, if ['cpppo-test']['Hz'] is granted a 10 Hz I/O (poll rate) by Dominion Research
        & Development Corp., the value assigned to the current Grant['cpppo-test']['Hz'] must be <=
        10.

        Typically, a Grant group key w/ no value (ie. None) indicates no constraint, so we don't
        allow replacing a Grant constraint w/ None, in either REFINING or COMBINED; it will simply pass
        the existing limit through -- we won't allow a restrictive Grant to be replaced by an
        undefined/unrestricted Grant.

        Grants completely disjoint in time cannot be COMBINEd; any Timespans presented must overlap,
        and the *intersection* is kept.  This is because we are combining the capabilities of both
        sub-Licenses: the combined capability is only valid for the intersection of the License
        dependencies' combination!

        In other words, if you have 100 "Hz" from Jan 1 to July 31, and 200 "Hz" from May 1 to Dec
        31, if you chose to combine those sub-Licenses, the combined Grant will be 100 "Hz" from May
        1 to July 31.

        Returns the {REFINING,COMBINED}d value, confirmed to be a subset (or accumulation) of any
        current value; None indicates there is no restriction, and should only be possible if both
        the current and value are None.

        """
        current			= self.get( group, {} ).get( key )
        result			= value
        # If a non-None current for this Grant group's value is already present, do some basic
        # validation.  Trying to replace a non-None (restrictive) current w/ a value of None
        # (unrestricted) is not allowed.
        if isinstance( current, type_num_base ):
            if style is Grant.Merging.REFINING:
                if value is None or value > current:
                    raise LicenseIncompatibility( "License Grant.{group}[{key!r}] of {value!r} exceeds limit: {current!r}".format(
                        group=group, key=key, value=value, current=current ))
            else:
                result		= current + ( value or 0 )
        elif isinstance( current, type_str_base ):
            current_set		= set( current if is_listlike( current ) else (current,) )
            if style is Grant.Merging.REFINING:
                if value is None or value not in current_set:
                    raise LicenseIncompatibility( "License Grant.{group}[{key!r}] of {value!r} doesn't match: {current!r}".format(
                        group=group, key=key, value=value, current=current_set ))
            else:
                if value is not None:
                    current_set.add( value )
                result		= sorted( current_set )
                if len( result ) == 1:
                    result,	= result
        elif isinstance( current, Timespan ) or isinstance( maybe_Timespan( value ), Timespan ):
            # Either the current or new value is a Timespan.  Let's see if the value is within the
            # provided current Timespan.  If two Grants are disjoint, raises exception
            current		= into_Timespan( current )      # May be None (no restriction)
            result = value	= into_Timespan( value )        # ''
            if style is Grant.Merging.REFINING:
                if ( Timespan() if value is None else value ) not in ( Timespan() if current is None else current ):
                    raise LicenseIncompatibility( "License Grant.{group}[{key!r}] of {value!r} is not within: {current!r}".format(
                        group=group, key=key, value=value, current=current ))
            else:
                intersect	= ( Timespan() if current is None else current ).intersection( Timespan() if value is None else value )
                if not intersect:
                    raise LicenseDisjoint( "License Grant.{group}[{key!r}] of {value!r} do not overlap: {current!r}".format(
                        group=group, key=key, value=value, current=current ))
                result		= intersect
        elif current is not None:
            raise LicenseIncompatibility( "License Grant.{group}[{key!r}] of {value!r} not comparable to: {current!r}".format(
                group=group, key=key, value=value, current=current ))

        # The provided value is a valid refinement (ie. subset) or combination of the current value
        log.info( "{style} Grant {group}'s {key} = {current!r} w/ {value!r} ==> {result!r}".format(
            style=style, group=group, key=key, current=current, value=value, result=result ))
        return result

    def _integrate( self, rhs_grant, style ):
        """Grant &/| Grant REFINING or COMBINED the current Grant, w/ the keys/Grants carried by the
        given grant -- which must typically specify a "subset" (&=) or "union" (|=) of the
        capabilities granted by the current Grant.  If each granted capability (key) is a valid
        refinement, then the current Grant assumes the refined value.

        An existing Grant with its heritage will be retained; the refinement applied

        If a completely new group is being added -- a previously unknown Grant -- then, we will also
        copy the source Grant._from heritage.  In the case of Grants from Licenses, this will be the
        authoring Agent from the License that originally authored the Grant.

        If the provided Grant is under an already known group key in the present Grant, and they are
        both Grants -- then we will ensure that the _from is identical.

        """
        assert isinstance( rhs_grant, Grant ), \
            "Expected to {style} against a Grant, not a {name}".format( style=style, name=rhs_grant.__class__.__name__ )
        for group,rhs_group_grant in rhs_grant.items():
            assert isinstance( rhs_group_grant, Grant ), \
                "Expected to {style} another Grant group {group}, not a {name}{extra}".format(
                    style=style, group=group, name=rhs_group_grant.__class__.__name__,
                    extra="; {} in {}".format( repr( rhs_group_grant ), repr( rhs_grant )) if log.isEnabledFor( logging.DEBUG ) else "" )
            if group in self.keys( every=True ):
                # An existing group key; only if no heritage is known do we assume the authorship of
                # the supplied refining Grant.
                lhs_group_grant	= self[group]
                if lhs_group_grant._from != rhs_group_grant._from:
                    if style is Grant.Merging.COMBINED:
                        # When License.grants() are COMBINED, the Grants must come from the same author
                        raise LicenseIncompatibility( "License Grant group {group}'s author {lhs_auth!r} incompatible with {rhs_auth!r}".format(
                            group=group, lhs_auth=lhs_group_grant._from, rhs_auth=rhs_group_grant._from ))
                    if lhs_group_grant._from is None:
                        log.info( "Inherits {} {!r}: {} author to that of {!r}: {}".format(
                            group, lhs_group_grant, lhs_group_grant, rhs_group_grant, rhs_group_grant ))
                        lhs_group_grant._from = rhs_group_grant._from
            else:
                # A completely new group key; assume the heritage of the supplied Grant
                lhs_group_grant = self[group] = Grant( _from=rhs_group_grant._from )
                log.info( "Creating {} {!r}: {} author w/ that of {!r}: {}".format(
                    group, lhs_group_grant, lhs_group_grant, rhs_group_grant, rhs_group_grant ))
            for key,value in rhs_group_grant.items():
                update		= self.merge( group=group, key=key, value=value, style=style )
                if update is not None:
                    lhs_group_grant[key] = update

    def __iand__( self, rhs_grant ):
        self._integrate( rhs_grant, style=Grant.Merging.REFINING )
        log.debug( "After Grant &= {}:\n{}".format(
            ', '.join( "{} = {} = {}".format( key, repr( rhs ), rhs_grant[key] ) for key,rhs in rhs_grant.items() ),
            '\n'.join( "{} = {} = {}".format( key, repr( lhs ), self[key] ) for key,lhs in self.items() )))
        return self

    def __ior__( self, rhs_grant ):
        self._integrate( rhs_grant, style=Grant.Merging.COMBINED )
        log.debug( "After Grant |= {}:\n{}".format(
            ', '.join( "{} = {} = {}".format( key, repr( rhs ), rhs_grant[key] ) for key,rhs in rhs_grant.items() ),
            '\n'.join( "{} = {} = {}".format( key, repr( lhs ), self[key] ) for key,lhs in self.items() )))
        return self

    def __le__( self, rhs_grant ):
        """Detect if this Grant is a subset of another.  If it has additional keys, or has a Grant
        that couldn't be satisfied by our Grant, then we are considered "not a subset".

        We can only compare Grants consisting of group:Grant pairs using this operator; A Grant may
        contain either group: Grant pairs, or key: value pairs.  Ensure Grant's _from are compatible
        and values are a subset, then compare each group:Grant's key:value pairs for compatibilityf

        For key/value pairs, use merge( ..., REFINING), which does not alter the Grant, but ensures
        that the target Grant's key/value are a superset of the given Grant's key/value; in effect,
        that this Grant is a subset of the target Grant.

        """
        try:
            if miss_groups     := set( self.keys( every=True )) - set( rhs_grant.keys( every=True )):
                raise LicenseDisjoint( "Grant group(s) {} do not overlap".format( ', '.join( miss_groups )))
            if self._from != rhs_grant._from:
                raise LicenseIncompatibility( "License Grant {lhs_auth!r} incompatible with {rhs_auth!r}".format(
                    lhs_auth=self._from, rhs_auth=rhs_grant._from ))
            for group,lhs_group_grant in self.items():
                rhs_group_grant	= rhs_grant[group]
                assert isinstance( lhs_group_grant, Grant ) and isinstance( rhs_group_grant, Grant ), \
                    "Only {group} Grants may be compared for subset, not {lhs_type} vs {rhs_type}".format(
                        group=group, lhs_type=type(lhs_group_grant), rhs_type=type(rhs_grant) )
                if miss_keys   := set( lhs_group_grant.keys( every=True )) - set( rhs_group_grant.keys( every=True )):
                    raise LicenseDisjoint( "Grant {} keys {} do not overlap".format(
                        group, ', '.join( miss_keys )))
                for key,value in lhs_group_grant.items():
                    # Verify RHS value is a subset of LHS value, or raise LicenseIncompatibility
                    subset	= rhs_grant.merge( group=group, key=key, value=value, style=Grant.Merging.REFINING )
                    log.info( "Grant group {}'s key {} subset {} <= {} ==> {}".format(
                              group, key, value, lhs_group_grant[key], subset ))
        except LicenseIncompatibility as exc:
            log.info( "Grant {} is not a subset of {}: {}".format( self, rhs_grant, exc ))
            return False
        log.debug( "Grant {} is a subset of {}".format( self, rhs_grant ))
        return True
