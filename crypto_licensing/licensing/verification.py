# -*- coding: utf-8 -*-

#
# Crypto-licensing -- Cryptographically signed licensing, w/ Cryptocurrency payments
#
# Copyright (c) 2022, Dominion Research & Development Corp.
#
# Crypto-licensing is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.  See the LICENSE file at the top of the source tree.
#
# It is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#

from __future__ import absolute_import, print_function, division

import ast
import codecs
import copy
import datetime
import dns.resolver
import hashlib
import json
import logging
import os
import sys
import traceback
import uuid

from enum import Enum

from .defaults		import (
    MODULENAME, LICPATTERN, KEYPATTERN, KEYEXTENSION,
)
from ..misc		import (
    type_str_base, urlencode,
    parse_datetime, parse_seconds, Timestamp, Duration,
    deduce_name, config_open, config_open_deduced,
)

# Get Ed25519 support. Try a globally installed ed25519ll possibly with a CTypes binding, Otherwise,
# try our local Python-only ed25519ll derivation, or fall back to the very slow D.J.Bernstein Python
# reference implementation
from .. import ed25519

# Optionally, we can provide ChaCha20Poly1305 to support KeypairEncrypted
try:
    from chacha20poly1305 import ChaCha20Poly1305
except ImportError:
    pass

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( "licensing" )


class LicenseIncompatibility( Exception ):
    """Something is wrong with the License, or supporting infrastructure."""
    pass


def domainkey_service( product ):
    """Convert a UTF-8 product name into a ASCII DNS Domainkey service name, with
    replacement for some symbols invalid in DNS names (TODO: incomplete).

        >>> domainkey_service( "Something Awesome v1.0" )
        'something-awesome-v1-0'

    Retains None, if supplied.
    """
    author_service		= product
    if author_service:
        author_service		= domainkey_service.idna_encoder( author_service )[0]
        if sys.version_info[0] >= 3:
            author_service	= author_service.decode( 'ASCII' )
        author_service		= author_service.translate( domainkey_service.dns_trans )
        author_service		= author_service.lower()
    return author_service
try:      # noqa: E305
    domainkey_service.dns_trans	= str.maketrans( ' ._/', '----' )
except AttributeError:   # Python2
    import string
    domainkey_service.dns_trans	= string.maketrans( ' ._/', '----' )
domainkey_service.idna_encoder	= codecs.getencoder( 'idna' )
assert "a/b.c_d e".translate( domainkey_service.dns_trans ) == 'a-b-c-d-e'


def into_hex( binary, encoding='ASCII' ):
    return into_text( binary, 'hex', encoding )


def into_b64( binary, encoding='ASCII' ):
    return into_text( binary, 'base64', encoding )


def into_text( binary, decoding='hex', encoding='ASCII' ):
    """Convert binary bytes data to the specified decoding, (by default encoded to ASCII text), across
    most versions of Python 2/3.  If no encoding, resultant decoding symbols remains as un-encoded
    bytes.

    A supplied None remains None.

    """
    if binary is not None:
        if isinstance( binary, bytearray ):
            binary		= bytes( binary )
        assert isinstance( binary, bytes ), \
            "Cannot convert to {}: {!r}".format( decoding, binary )
        binary			= codecs.getencoder( decoding )( binary )[0]
        binary			= binary.replace( b'\n', b'' )  # some decodings contain line-breaks
        if encoding is not None:
            return binary.decode( encoding )
        return binary


def into_bytes( text, decodings=('hex', 'base64'), ignore_invalid=None ):
    """Try to decode base-64 or hex bytes from the provided ASCII text, pass thru binary data as bytes.
    Must work in Python 2, which is non-deterministic; a str may contain bytes or text.

    So, assume ASCII encoding, start with the most strict (least valid symbols) decoding codec
    first.  Then, try as simple bytes.

    """
    if not text:
        return None
    if isinstance( text, bytearray ):
        return bytes( text )
    # First, see if the text looks like hex- or base64-decoded UTF-8-encoded ASCII
    encoding,is_ascii		= 'UTF-8',lambda c: 32 <= c <= 127
    try:
        # Python3 'bytes' doesn't have .encode (so will skip this code), and Python2 non-ASCII
        # binary data will raise an AssertionError.
        text_enc		= text.encode( encoding )
        assert all( is_ascii( c ) for c in bytearray( text_enc )), \
            "Non-ASCII symbols found: {!r}".format( text_enc )
        for c in decodings:
            try:
                binary		= codecs.getdecoder( c )( text_enc )[0]
                #log.debug( "Decoding {} {} bytes from: {!r}".format( len( binary ), c, text_enc ))
                return binary
            except Exception:
                pass
    except Exception:
        pass
    # Finally, check if the text is already bytes (*possibly* bytes in Python2, as str ===
    # bytes; so this cannot be done before the decoding attempts, above)
    if isinstance( text, bytes ):
        #log.debug( "Passthru {} {} bytes from: {!r}".format( len( text ), 'native', text ))
        return text
    if not ignore_invalid:
        raise RuntimeError( "Could not encode as {}, decode as {} or native bytes: {!r}".format(
            encoding, ', '.join( decodings ), text ))


def into_keys( keypair ):
    """Return whatever Ed25519 (public, signing) keys are available in the provided Keypair or
    32/64-byte key material.  This destructuring ordering is consistent with the
    namedtuple('Keypair', ('vk', 'sk')).

    Supports deserialization of keys from hex or base-64 encode public (32-byte) or secret/signing
    (64-byte) data.  To avoid nondeterminism, we will assume that all Ed25519 key material is encoded in
    base64 (never hex).

    """
    try:
        # May be a Keypair namedtuple
        return keypair.vk, keypair.sk
    except AttributeError:
        pass
    # Not a Keypair.  First, see if it's a serialized public/private key.
    deserialized	= into_bytes( keypair, ('base64',), ignore_invalid=True )
    if deserialized:
        keypair		= deserialized
    # Finally, see if we've recovered a signing or public key
    if isinstance( keypair, bytes ):
        if len( keypair ) == 64:
            # Must be a 64-byte signing key, which also contains the public key
            return keypair[32:64], keypair[0:64]
        elif len( keypair ) == 32:
            # Can only contain a 32-byte public key
            return keypair[:32], None
    # Unknown key material.
    return None, None


def into_str( maybe ):
    if maybe is not None:
        return str( maybe )


def into_str_UTC( ts, tzinfo=Timestamp.UTC ):
    if ts is not None:
        return ts.render( tzinfo=tzinfo, ms=False, tzdetail=True )


def into_str_LOC( ts ):
    return into_str_UTC( ts, tzinfo=Timestamp.LOC )


def into_JSON( thing, indent=None, default=None ):
    def endict( x ):
        try:
            return dict( x )
        except Exception as exc:
            if default:
                return default( x )
            log.warning("Failed to JSON serialize {!r}: {}".format( x, exc ))
            raise exc
    # Unfortunately, Python2 json.dumps w/ indent emits trailing whitespace after "," making
    # tests fail.  Make the JSON separators whitespace-free, so the only difference between the
    # signed serialization and an pretty-printed indented serialization is the presence of
    # whitespace.
    separators			= (',', ':')
    text			= json.dumps(
        thing, sort_keys=True, indent=indent, separators=separators, default=endict )
    return text


def into_boolean( val, truthy=(), falsey=() ):
    """Check if the provided numeric or str val content is truthy or falsey; additional tuples of
    truthy/falsey lowercase values may be provided."""
    if isinstance( val, (int,float,bool)):
        return bool( val )
    assert isinstance( val, type_str_base )
    if val.lower() in ( 't', 'true', 'y', 'yes' ) + truthy:
        return True
    elif val.lower() in ( 'f', 'false', 'n', 'no' ) + falsey:
        return False
    raise ValueError( val )


def into_timestamp( ts ):
    """Convert to a timestamp, retaining None.

    """
    if ts is not None:
        if isinstance( ts, type_str_base ):
            ts			= parse_datetime( ts )
        if isinstance( ts, datetime.datetime ):
            ts			= Timestamp( ts )
        assert isinstance( ts, Timestamp )
    return ts


def into_duration( dur ):
    """Convert to a duration, retaining None"""
    if dur is not None:
        if not isinstance( dur, Duration ):
            dur			= parse_seconds( dur )
            assert isinstance( dur, (int, float) )
            dur			= Duration( dur )
    return dur


def into_Timespan( tspan ):
    """Convert to a Timespan, retaining None"""
    if tspan is not None:
        if not isinstance( tspan, Timespan ):
            if isinstance( tspan, type_str_base ):
                tspan		= json.dumps( tspan )
            tspan		= Timespan( **dict( tspan ))
    return tspan


def into_Grant( grant ):
    """Convert to a Grant, retaining None.  An empty Grant won't be included in serialize."""
    if grant is not None:
        if not isinstance( grant, Grant ):
            if isinstance( grant, type_str_base ):
                grant		= json.loads( grant )
            grant		= Grant( **dict( grant ))
    return grant


def into_UUIDv4( machine ):
    if machine is not None:
        if not isinstance( machine, uuid.UUID ):
            machine		= uuid.UUID( machine )
        assert machine.version == 4
    return machine


def machine_UUIDv4( machine_id_path=None):
    """Identify the machine-id as an RFC 4122 UUID v4. On Linux systems w/ systemd, get from
    /etc/machine-id, as a UUID v4: https://www.man7.org/linux/man-pages/man5/machine-id.5.html.
    On MacOS and Windows, use uuid.getnode(), which derives from host-specific data (eg. MAC
    addresses, serial number, ...).

    This UUID should be reasonably unique across hosts, but is not guaranteed to be.

    TODO: Include root disk UUID?
    """
    if machine_id_path is None:
        machine_id_path		= "/etc/machine-id"
    try:
        with open( machine_id_path, 'r' ) as m_id:
            machine_id		= m_id.read().strip()
    except Exception:
        # Node number is typically a much shorter integer; fill to required UUID length.
        machine_id		= "{:0>32}".format( hex( uuid.getnode())[2:] )
    try:
        machine_id		= into_bytes( machine_id, ('hex', ) )
        assert len( machine_id ) == 16
    except Exception as exc:
        raise RuntimeError( "Invalid Machine ID found: {!r}: {}".format( machine_id, exc ))
    machine_id			= bytearray( machine_id )
    machine_id[6]	       &= 0x0F
    machine_id[6]	       |= 0x40
    machine_id[8]	       &= 0x3F
    machine_id[8]	       |= 0x80
    machine_id			= bytes( machine_id )
    return uuid.UUID( into_hex( machine_id ))


def domainkey( product, domain, service=None, pubkey=None ):
    """Compute and return the DNS path for the given product and domain.  Optionally, returns the
    appropriate DKIM TXT RR record containing the agent's public key (base-64 encoded), as per the
    RFC: https://www.rfc-editor.org/rfc/rfc6376.html

        >>> from .verification import author, domainkey
        >>> path, dkim_rr = domainkey( "Some Product", "example.com" )
        >>> path
        'some-product.crypto-licensing._domainkey.example.com.'
        >>> dkim_rr

        # An Awesome, Inc. product
        >>> keypair = author( seed=b'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA' )
        >>> path, dkim_rr = domainkey( "Something Awesome v1.0", "awesome-inc.com", pubkey=keypair )
        >>> path
        'something-awesome-v1-0.crypto-licensing._domainkey.awesome-inc.com.'
        >>> dkim_rr
        'v=DKIM1; k=ed25519; p=25lf4lFp0UHKubu6krqgH58uHs599MsqwFGQ83/MH50='

    """
    if service is None:
        service			= domainkey_service( product )
    assert service, \
        "A service is required to deduce the DKIM DNS path"
    domain_name			= dns.name.from_text( domain )
    service_name		= dns.name.Name( [service, MODULENAME, '_domainkey'] )
    path_name			= service_name + domain_name
    path			= path_name.to_text()

    dkim			= None
    if pubkey:
        pubkey,_		= into_keys( pubkey )
        dkim			= '; '.join( "{k}={v}".format(k=k, v=v) for k,v in (
            ('v', 'DKIM1'),
            ('k', 'ed25519'),
            ('p', into_b64( pubkey )),
        ))

    return (path, dkim)


class Serializable( object ):
    """A base-class that provides a deterministic Unicode JSON serialization of every __slots__
    and/or __dict__ attribute, and a consistent dict representation of the same serialized data.
    Access attributes directly to obtain underlying types.

    Uses __slots__ in derived classes to identify serialized attributes; traverses the class
    hierarchy's MRO to identify all attributes to serialize.  Output serialization is always in
    attribute-name sorted order.

    If an attribute requires special serialization handling (other than simple conversion to 'str'),
    then include it in the class' serializers dict, eg:

        serializers		= dict( special = into_hex )

    It is expected that derived class' constructors will deserialize when presented with keywords
    representing all keys.

    """

    __slots__			= ()
    serializers			= {}

    def vars( self ):
        """Returns all key/value pairs defined for the object, either from __slots__ and/or __dict__."""
        for cls in type( self ).__mro__:
            try:
                vars_seq	= tuple( cls.__slots__ )  # Having a key defined but not instantiated isn't valid.
                if '__dict__' in vars_seq:
                    vars_seq   += tuple( self.__dict__ )
            except AttributeError:
                try:
                    vars_seq	= self.__dict__
                except AttributeError as exc:
                    vars_seq	= ()
                    if cls is not object:  # Only the base object() is allowed to have neither __slots__ nor __dict__
                        log.error( "vars for base {cls!r} instance {self!r} has neither __slots__ nor __dict__: {exc}".format(
                            cls=cls, self=self,
                            exc=''.join( traceback.format_exception( *sys.exc_info() )) if log.isEnabledFor( logging.TRACE ) else exc ))
                        raise
            for key in vars_seq:
                yield key, getattr( self, key )

    def __copy__( self ):
        """Create a new object by copying an existing object, taking __slots__ into account.

        """
        result			= self.__class__.__new__( self.__class__ )

        for key,val in self.vars():
            setattr( result, key, copy.copy( val ))

        return result

    def keys( self, every=False ):
        """Yields the Serializable object's relevant (not absent/None/.empty()) keys.

        For many uses (eg. conversion to dict), the default behaviour of ignoring keys with values
        of None (or a Truthy .empty() method) is appropriate.  However, if you want all keys
        regardless of content, specify every=True.

        """
        def isnt_empty( val ):
            if val is None:
                return False
            empty		= getattr( val, 'empty', None )
            if empty is not None and hasattr( empty, '__call__' ) and empty():
                return False
            return True

        for key,val in self.vars():
            if every or isnt_empty( val ):
                yield key

    def serializer( self, key ):
        """Finds any custom serialization formatter specified for the given attribute, defaults to None.

        """
        for cls in type( self ).__mro__:
            try:
                return cls.serializers[key]
            except (AttributeError, KeyError):
                pass

    def __getitem__( self, key ):
        """Returns the serialization of the requested key, passing thru values without a serializer."""
        if key in self.keys( every=True ):
            try:
                serialize	= self.serializer( key )  # (no Exceptions)
                value		= getattr( self, key )    # IndexError
                if serialize:
                    return serialize( value )             # conversion failure Exceptions
                return value
            except Exception as exc:
                log.debug( "Failed to convert {class_name}.{key} with {serialize!r}: {exc}".format(
                    class_name = self.__class__.__name__, key=key, serialize=serialize, exc=exc ))
                raise
        raise IndexError( "{} not found in keys {}".format( key, ', '.join( self.keys( every=True ))))

    def __str__( self ):
        return self.serialize( indent=4, encoding=None )  # remains as UTF-8 text

    def JSON( self, indent=None, default=None ):
        """Return the default JSON representation of the present (default: entire self) object."""
        return into_JSON( self, indent=indent, default=default )

    def serialize( self, indent=None, encoding='UTF-8', default=None ):
        """Return a binary 'bytes' serialization of the present object.  Serialize to JSON, assuming any
        complex sub-objects (eg. License, LicenseSigned) have a sensible dict representation.

        The default serialization (ie. with indent=None) will be the one used to create the digest.

        If there are objects to be serialized that require special handling, they must not have a
        'dict' interface (be convertible to a dict), and then a default may be supplied to serialize
        them (eg. str).

        """
        stream			= self.JSON( indent=indent, default=default )
        if encoding:
            stream		= stream.encode( encoding )
        return stream

    def sign( self, sigkey, pubkey=None ):
        """Sign our default serialization, and (optionally) confirm that the supplied public key
        (which will be used to check the signature) is correct, by re-deriving the public key.

        """
        vk, sk			= into_keys( sigkey )
        assert sk, \
            "Invalid ed25519 signing key provided"
        if pubkey:
            # Re-derive and confirm supplied public key matches supplied signing key
            keypair		= ed25519.crypto_sign_keypair( sk[:32] )
            assert keypair.vk == pubkey, \
                "Mismatched ed25519 signing vs. public keys {!r} vs. {!r}".format(
                    into_b64( keypair.vk ), into_b64( pubkey ))
        signed			= ed25519.crypto_sign( self.serialize(), sk )
        signature		= signed[:64]
        return signature

    def verify( self, pubkey, signature ):
        """Check that the supplied signature matches this serialized payload, and return the verified
        payload bytes.

        """
        pubkey, _		= into_keys( pubkey )
        signature		= into_bytes( signature, ('base64',) )
        assert pubkey and signature, \
            "Missing required {}".format(
                ', '.join( () if pubkey else ('public key',)
                           + () if signature else ('signature',) ))
        return ed25519.crypto_sign_open( signature + self.serialize(), pubkey )

    def digest( self, encoding=None, decoding=None ):
        """The SHA-256 hash of the serialization, as 32 bytes.  Optionally, encode w/ a named codec,
        eg.  "hex" or "base64".  Often, these will require a subsequent .decode( 'ASCII' ) to become
        a non-binary str.

        """
        binary			= hashlib.sha256( self.serialize() ).digest()
        if encoding is not None:
            binary		= codecs.getencoder( encoding )( binary )[0].replace(b'\n', b'')
            if decoding is not None:
                return binary.decode( decoding )
        return binary

    def hexdigest( self ):
        """The SHA-256 hash of the serialization, as a 256-bit (32 byte, 64 character) hex string."""
        return self.digest( 'hex', 'ASCII' )

    def b64digest( self ):
        return self.digest( 'base64', 'ASCII' )


class IssueRequest( Serializable ):
    __slots__			= (
        'author', 'author_pubkey', 'product',
        'client', 'client_pubkey', 'machine'
    )
    serializers			= dict(
        author_pubkey	= into_b64,
        client_pubkey	= into_b64,
        machine		= into_str,
    )

    def __init__( self, author=None, author_pubkey=None, product=None,
                  client=None, client_pubkey=None, machine=None ):
        self.author		= into_str( author )
        self.author_pubkey, _	= into_keys( author_pubkey )
        self.product		= into_str( product )
        self.client		= into_str( client )
        self.client_pubkey, _	= into_keys( client_pubkey )
        self.machine		= into_UUIDv4( machine )

    def query( self, sigkey ):
        """Issue query is sorted-key order"""
        qd			= dict( self )
        qd['signature']		= into_b64( self.sign( sigkey=sigkey ))
        return urlencode( sorted( qd.items() ))


def overlap_intersect( start, length, other ):
    """Accepts a start/length, and a Timespan (something w/ start and length), and compute the
    intersecting start/length, and its begin and (if known) ended timestamps.

        start,length,begun,ended = overlap_intersect( start, length, other )

    A start/Timespan w/ None for length is assumed to endure from its start with no time limit.

    """
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


class Agent( Serializable ):
    __slots__			= (
        'name', 'pubkey', 'domain', 'product', 'service',
    )
    serializers			= dict(
        pubkey		= into_b64,
    )

    def __init__(
        self,
        name,
        pubkey		= None,			# Normally, obtained from domain's DKIM1 TXT RR
        domain		= None,			# Needed for DKIM if no pubkey provided
        product		= None,
        service		= None,			# Normally, derived from product name
    ):
        # Obtain the Agent's public key; either given through the API, or obtained from their
        # domain's DKIM entry.
        assert pubkey or ( domain and ( product or service )), \
            "Either a pubkey or a domain + service/product must be provided"
        self.name	= name
        self.domain	= domain
        self.product	= product
        self.service	= service
        self.pubkey,_	= into_keys( pubkey )
        # Now pubkey_query has all the details it requires to do a DKIM lookup, if necessary
        if not self.pubkey:
            self.pubkey	= self.pubkey_query()

    def pubkey_query( self ):
        """Obtain the agent's public key.  This was either provided at License construction time, or
        can be obtained from a DNS TXT "DKIM" record.

        TODO: Cache

        Query the DKIM record for an author public key.  May be split into multiple strings:

            r = dns.resolver.query('default._domainkey.justicewall.com', 'TXT')
            for i in r:
            ...  i.to_text()
            ...
            '"v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9...Btx" "aPXTN/aI+cvS8...4KHoQqhS7IwIDAQAB;"'

        Fortunately, the Python AST for string literals handles this quite nicely:

            >>> ast.literal_eval('"abc" "123"')
            'abc123'

        """
        dkim_path, _dkim_rr	= domainkey( self.product, self.domain, service=self.service )
        log.debug("Querying {domain} for DKIM service {service}: {dkim_path}".format(
            domain=self.domain, service=self.service, dkim_path=dkim_path ))
        # Python2/3 compatibility; use query vs. resolve
        records			= list( rr.to_text() for rr in dns.resolver.query( dkim_path, 'TXT' ))
        assert len( records ) == 1, \
            "Failed to obtain a single TXT record from {dkim_path}".format( dkim_path=dkim_path )
        # Parse the "..." "..." strings.  There should be no escaped quotes.
        dkim			= ast.literal_eval( records[0] )
        log.debug("Parsing DKIM record: {dkim!r}".format( dkim=dkim ))
        p			= None
        for pair in dkim.split( ';' ):
            key,val 		= pair.strip().split( '=', 1 )
            if key.strip().lower() == "v":
                assert val.upper() == "DKIM1", \
                    "Failed to find DKIM record; instead found record of type/version {val}".format( val=val )
            if key.strip().lower() == "k":
                assert val.lower() == "ed25519", \
                    "Failed to find Ed25519 public key; instead was of type {val!r}".format( val=val )
            if key.strip().lower() == "p":
                p		= val.strip()
        assert p, \
            "Failed to locate public key in TXT DKIM record: {dkim}".format( dkim=dkim )
        p_binary		= into_bytes( p, ('base64',) )
        return p_binary


class Timespan( Serializable ):
    """A time period, optionally w/ a start and/or a length."""
    __slots__			= (
        'start', 'length',
    )
    serializers			= dict(
        start		= into_str_UTC,
        length		= into_str,
    )

    def __init__(
        self,
        start		= None,
        length		= None,
    ):
        """A License usually has a timespan of start timestamp and duration length.  These cannot
        exceed the timespan of any License dependencies.  First, get any supplied start time as a
        timestamp, and any duration length as a number of seconds.

        """
        self.start		= into_timestamp( start )
        self.length		= into_duration( length )


class Grant( Serializable ):
    """The option key/value capabilities granted by a License.  The first level names (typically
    something related to the product name) must only specify a dict of key/value pairs, and all
    must be serializable to JSON.

    The Granted option names cannot be trusted; any License may carry a Grant of any option name
    whatsoever.  So, the License itself must be validated as being issued by an expected author,
    before its Grant of options can be trusted.

    Also, some License options granted in sub-Licenses may "accumulate", while others only accrue
    to the direct client of the License.  Each License author must decide this; only their code
    that validates their License knows the semantics of their Grant options.

    We'll use a dynamic __dict__ instead of __slots__ to hold the unknown option key/dict pairs.

    """
    def __init__( self, *args, **kwds ):
        if args:
            assert len( args ) == 1 and isinstance( args[0], type_str_base ) and not kwds, \
                "Grant option cannot be defined w/ multiple or non-str args both args: {args!r} and/or kwds: {kwds!r}".format(
                    args=args, kwds=kwds )
            kwds		= json.loads( args[0] )
        option			= dict( kwds )
        # Ensure that options only has first-level keys w/ /dicts
        assert all(
            hasattr( v, 'keys' ) and hasattr( v, '__getitem__' )
            for v in option.values()
        ), "Found non-dict Grant option(s): {keys}".format(
            keys		= ', '.join(
                k for k,v in option.items()
                if not ( hasattr( v, 'keys' ) and hasattr( v, '__getitem__' ))
            )
        )
        self.__dict__.update( option )

    def empty( self ):
        """Detects if empty, and avoid serialization if so.  This allows someone to accidentally define an
        empty Grant, without changing the signature vs. the same License w/ no Grant.

        """
        return not bool( self.__dict__ )


class License( Serializable ):
    """Represents the details of a Licence from an author to a client (could be any client, if no
    client or client.pubkey provided).  Cannot be constructed unless the supplied License details
    are valid with respect to the License dependencies it 'has', and grants capabilities 'for'
    certain machine, period or other "keys".


    {
        "author": {
           "domain":"dominionrnd.com",
           "name":"Dominion Research & Development Corp.",
           "product":"Cpppo Test",
           "pubkey":"qZERnjDZZTmnDNNJg90AcUJZ+LYKIWO9t0jz/AzwNsk="
        }
        "client":{
            "name":"Awesome, Inc.",
            "pubkey":"cyHOei+4c5X+D/niQWvDG5olR1qi4jddcPTDJv/UfrQ="
        },
        "has":[
            {
                "license":{...},
                "signature":"9Dba....kLCg=="
            },
            ...
        ],
        "grant":{
            "timespan":{
                "start": "2021-01-01 00:00:00+00:00"
                "length": "1y"
            },
            "machine":"00010203-0405-4607-8809-0a0b0c0d0e0f"
            "option":{
                "Hz":1000,
            }
        }
    }

    Verifying a License
    -------------------

    A signed license is a claim by an Author that the License is valid; it is up to a recipient to
    check that the License also actually satisfies the constraints of any License dependencies.  A
    nefarious Author could create a License and properly sign it -- but not satisfy the License
    constraints.  License.verify(confirm=True) will do this, as well as (optionally) retrieve and
    verify from DNS the public keys of the (claimed) signed License dependencies.

    Checking your License
    ---------------------

    Each module that uses crypto_licensing.licensing checks that the final product's License or its
    parents contains valid license(s) for itself, somewhere within the License dependencies tree.

    All start times are expressed in the UTC timezone; if we used the local timezone (as computed
    using get_localzone, wrapped to respect any TZ environment variable, and made available as
    timestamp.LOC), then serializations (and hence signatures and signature tests) would be
    inconsistent.

    Licenses for products are signed by the author using their signing key.  The corresponding
    public key is expected to be found in a DKIM entry; eg. for Dominion's Cpppo product:

        cpppo.crypto-licensing._domainkey.dominionrnd.com 300 IN TXT "v=DKIM1; k=ed25519; p=ICkF+6tTRKc8voK15Th4eTXMX3inp5jZwZSu4CH2FIc="


    Licenses may carry optional constraints, with functions to validate their values.  These may be
    expressed in terms of all Licenses issued by the Author.  During normal License.verify of an
    installed License, nothing about the pool of issued Licenses is known, so no additional
    verification can be done.  However, when an Author is issuing a License and has access to the
    full pool of issued Licenses, all presently issued values of the constraint are known.

    If a lambda is provided it will be passed a proposed value as its second default parameter, with
    the first parameter defaulting to None, or a list containing all present instances of the
    constraint across all currently valid Licenses.  For example, if only 10 machine licenses are
    available, return the provided machine if the number is not exhausted:

        machine = "00010203-0405-4607-8809-0a0b0c0d0e0f"
        machine__verifier = lambda m, ms=None: \
            ( str( m ) if len( str( m ).split( '-' )) == 5 else ValueError( f"{m} doesn't look like a UUID" )\
                if ms is None or len( ms ) < 10 \
                else ValueError( "No more machine licenses presently available" )

    Alternatively, a None or numeric limit could be distributed across all issued licenses:

        targets = 3
        targets__verifier = lambda n, ns=None: \
            None if n is None else int( n ) \
              if n is None or ns is None or int( n ) + sum( map( int, filter( None, ns ))) <= 100 \
              else ValueError( f"{n} exceeds {100-sum(map(int,filter(None,ns)))} targets available" )

    If an Exception is returned, it will be raised.  Otherwise, the result of the lambda will be
    used as the License' value for the constraint.

    """

    __slots__			= (
        'author',
        'client',
        'dependencies',
        'machine',
        'timespan',
        'grant',
    )
    serializers			= dict(
        start		= into_str_UTC,
        length		= into_str,
        machine		= into_str,
    )

    @property
    def start( self ):
        return self.timespan and self.timespan.start

    @property
    def length( self ):
        return self.timespan and self.timespan.length

    def __init__(
        self,
        author,
        client		= None,
        dependencies	= None,				# Any Licenses this License depends on
        machine		= None,
        timespan	= None,
        grant		= None,				# The timespan, machine and options granted
        machine_id_path	= None,
        confirm		= None,				# Validate License' author_pubkey from DNS
    ):
        # Who is authoring this License, and who (if anyone in particular) is this License intended
        # for?  If no client is specified, any agent Keypair may issue a sub-license this license.
        assert author, \
            "Issuing a Licence without an author is incorrect"
        if isinstance( author, type_str_base ):
            author		= json.loads( author )  # Deserialize Agent, if necessary
        self.author		= Agent( **author )

        if isinstance( client, type_str_base ):
            client		= json.loads( client )  # Deserialize Agent, if necessary
        self.client		= Agent( **client ) if client else None

        self.machine		= into_UUIDv4( machine )  # None or machine UUIDv4 (raw or serialized)

        try:
            self.timespan	= into_Timespan( timespan )
        except Exception as exc:
            raise LicenseIncompatibility( "License timespan invalid: {exc}".format( exc=exc ))

        try:
            self.grant		= into_Grant( grant )
        except Exception as exc:
            raise LicenseIncompatibility( "License grant invalid: {exc}".format( exc=exc ))

        # Reconstitute LicenseSigned provenance from any dicts provided
        self.dependencies	= None
        if dependencies is not None:
            self.dependencies	= list(
                prov
                if isinstance( prov, LicenseSigned )
                else LicenseSigned( confirm=confirm, machine_id_path=machine_id_path, **dict( prov ))
                for prov in dependencies
            )

        # Only allow the construction of valid Licenses
        self.verify( confirm=confirm, machine_id_path=machine_id_path )

    def overlap( self, *others ):
        """Compute the overlapping start/length that is within the bounds of this and other license(s).
        If they do not overlap, raises a LicenseIncompatibility Exception.

        Any other thing that doesn't have a .product, .author defaults to *this* License's
        attributes (eg. we're applying further Timespan constraints to this License).

        """
        start			= self.start
        length			= self.length
        for other in others:
            # If we determine a 0-length overlap, we have failed.
            start,length,begun,ended = overlap_intersect( start, length, other )
            if length is not None and length.total_seconds() == 0:
                # Overlap was computable, and was zero
                raise LicenseIncompatibility(
                    "License for {author}'s {product!r} from {start} for {length} incompatible with others".format(
                        author	= getattr( getattr( other, 'author', None ), 'name', None )  or self.author.name,
                        product	= getattr( getattr( other, 'author', None ), 'product', None ) or self.author.product,
                        start	= into_str_LOC( other.start ),
                        length	= other.length,
                    ))
        return start, length

    def verify(
        self,
        author_pubkey	= None,
        signature	= None,
        confirm		= None,
        machine_id_path	= None,
        dependencies	= False,  # Default to not include this LicenseSigned in returned constraints['dependencies']
        **constraints
    ):
        """Verify that the License is valid:

            - Has properly signed License dependencies
              - Each public key can be confirmed, if desired
            - Complies with the bounds of any License dependencies
              - A sub-License must be issued while all License dependencies are active
            - Allows any constraints supplied.

        If it does, the constraints are returned, including this LicenseSigned added to the
        constraints['dependencies'].  If no additional constraints are supplied, this will simply
        return the empty constraints dict on success.  The returned constraints would be usable in
        constructing a new License (assuming at least the necessary author, author_domain and
        product were defined).

        """
        if author_pubkey:
            author_pubkey, _	= into_keys( author_pubkey )
            assert author_pubkey, "Unrecognized author_pubkey provided"

        if author_pubkey and author_pubkey != self.author.pubkey:
            raise LicenseIncompatibility(
                "License for {auth}'s {prod!r} public key mismatch".format(
                    auth	= self.author.name,
                    prod	= self.author.product,
                ))
        # Verify that the License's stated public key matches the one in the domain's DKIM.  Default
        # to True when confirm is None.
        if confirm or confirm is None:
            avkey	 	= self.author.pubkey_query()
            if avkey != self.author.pubkey:
                raise LicenseIncompatibility(
                    "License for {auth}'s {prod!r}: author key from DKIM {found} != {claim}".format(
                        auth	= self.author.name,
                        prod	= self.author.product,
                        found	= into_b64( avkey ),
                        claim	= into_b64( self.author.pubkey ),
                    ))
        # Verify that the License signature was indeed produced by the signing key corresponding to
        # the provided public key
        if signature:
            try:
                super( License, self ).verify( pubkey=self.author.pubkey, signature=signature )
            except Exception as exc:
                raise LicenseIncompatibility(
                    "License for {auth}'s {prod!r}: signature mismatch: {sig!r}; {exc}".format(
                        auth	= self.author.name,
                        prod	= self.author.product,
                        sig	= into_b64( signature ),
                        exc	= exc,
                    ))

        # Verify any License dependencies are valid; signed w/ DKIM specified key, License OK.  When
        # verifying License dependencies, we don't supply the constraints and decline inclusion of
        # dependencies, because we're not interested in sub-Licensing these Licenses, only verifying
        # them.  If a License dependency specifies a client, make certain it matches the issued
        # License's author; otherwise, any author is allowed.

        # TODO: Issuing a License that allows "anonymous" clients is somewhat dangerous, as the
        # entire package of License capabilities can be acquired by anyone.  When we validate
        # capabilities requested against those granted by a License, we must "stop", when we
        # encounter any anonymous License dependencies -- any capabilities they grant cannot be
        # assumed to be "for" the licensee; the Agent authoring the present license.
        for prov_dct in self.dependencies or []:
            prov		= LicenseSigned( confirm=confirm, machine_id_path=machine_id_path, **prov_dct )
            try:
                prov.verify( confirm=confirm, machine_id_path=machine_id_path )
                assert prov.license.client is None or prov.license.client.pubkey is None or prov.license.client.pubkey == self.author.pubkey, \
                    "sub-License client public key {client_pubkey} doesn't match Licence author's public key {author_pubkey}".format(
                        client_pubkey	= into_b64( prov.license.client.pubkey ),
                        author_pubkey	= into_b64( self.author.pubkey ),
                    )
            except Exception as exc:
                raise LicenseIncompatibility(
                    "License for {auth}'s {prod!r}; sub-License for {dep_auth}'s {dep_prod!r} invalid: {exc}".format(
                        auth		= self.author.name,
                        prod		= self.author.product,
                        dep_auth	= prov.license.author.name,
                        dep_prod	= prov.license.author.product,
                        exc		= exc,
                    ))

        # Enforce all constraints, returning a dict suitable for creating a specialized License, if
        # a signature was provided; if not, we cannot produce a specialized sub-License, and must
        # fail.

        # First, scan the constraints to see if any are callable

        # Verify all sub-license start/length durations comply with this License' duration.
        # Remember, these start/length specify the validity period of the License to be
        # sub-licensed, not the execution time of the installation!
        try:
            # Collect any things with .start/.length; all sub-Licenses dependencies, and a Timespan
            # representing any supplied start/length constraints in order to validate their
            # consistency with the sub-License start/lengths.
            others		= list( ls.license for ls in ( self.dependencies or [] ))
            # Find any non-empty timespan w/ non-empty start/length in constraints
            timespan_cons	= constraints.get( 'timespan' )
            if timespan_cons:
                if isinstance( timespan_cons, type_str_base ):
                    timespan_cons = json.loads( timespan_cons )
            # At this point, only iff timespan_cons is Truthy, has there been a timespan constraint specified
            if timespan_cons:
                others.append( Timespan( **timespan_cons ))
            start, length	= self.overlap( *others )
        except LicenseIncompatibility as exc:
            raise LicenseIncompatibility(
                "License for {auth}'s {prod!r}; sub-{exc}".format(
                    auth	= self.author.name,
                    prod	= self.author.product,
                    exc		= exc,
                ))
        else:
            # Finally, if a timespan constraint w/ either start or length was supplied, update it
            # with the computed timespan of start/length constraints overlapped with all
            # dependencies.  For example, we might get only a timespan.length constraint; this
            # would use produce the earliest overlapping timespan.start of all dependency Licenses,
            # with a duration of the supplied length.
            if timespan_cons:  # Iff a timespan constraint was specified...
                constraints['timespan'] = Timespan( start, length )

        # TODO: Implement License expiration date, to allow a software deployment to time out and
        # refuse to run after a License as expired, forcing the software owner to obtain a new
        # License with a future expiration.  Typically, Cpppo installations are perpetual; if
        # installed with a valid License, they will continue to work without expiration.  However,
        # other software authors may want to sell software that requires issuance of new Licenses.

        # Default 'machine' constraints to the local machine UUID.  If no constraints and
        # self.machine is None, we don't need to do anything, because the License is good for any
        # machine.  Use machine=True to force constraints to include the current machine UUID.
        machine			= None
        if machine_id_path is not False and ( self.machine or constraints.get( 'machine' )):
            # Either License or constraints specify a machine (so we have to verify), and the
            # machine_id_path directive doesn't indicate to *not* check the machine ID (eg. when
            # issuing the license from a different machine)
            machine_uuid	= machine_UUIDv4( machine_id_path=machine_id_path )
            if self.machine not in (None, True) and self.machine != machine_uuid:
                raise LicenseIncompatibility(
                    "License for {auth}'s {prod!r} specifies Machine ID {required}; found {detected}{via}".format(
                        auth	= self.author.name,
                        prod	= self.author.product,
                        required= self.machine,
                        detected= machine_uuid,
                        via	= " (via {})".format( machine_id_path ) if machine_id_path else "",
                    ))
            machine_cons	= constraints.get( 'machine' )
            if machine_cons not in (None, True) and machine_cons != machine_uuid:
                raise LicenseIncompatibility(
                    "Constraints on {auth}'s {prod!r} specifies Machine ID {required}; found {detected}{via}".format(
                        auth	= self.author.name,
                        prod	= self.author.product,
                        required= machine_cons,
                        detected= machine_uuid,
                        via	= " (via {})".format( machine_id_path ) if machine_id_path else "",
                    ))
            # Finally, unless the supplied 'machine' constraint was explicitly None (indicating that
            # the caller desires a machine-agnostic sub-License), default to constrain the License to
            # this machine.
            if machine_cons is not None:
                constraints['machine'] = machine_uuid

        log.info( "License for {auth}'s {prod!r} is valid from {start} for {length} on machine {machine}".format(
            auth	= self.author.name,
            prod	= self.author.product,
            start	= into_str_LOC( start ),
            length	= length,
            machine	= into_str( machine ) or into_str( constraints.get( 'machine' )) or '(any)',
        ))

        # Finally, now that the License, all License.dependencies and any supplied constraints have
        # been verified, augment the constraints with this LicenseSigned as one of the dependencies.
        if dependencies:
            assert signature is not None, \
                "Attempt to issue a sub-License of an un-signed License"
            assert isinstance( dependencies, (list,bool) ), \
                "Provided dependencies must be False/True, or a list of LicenseSigned"
            constraints['dependencies'] = [] if dependencies is True else dependencies
            constraints['dependencies'].append( dict(
                LicenseSigned( license=self, signature=signature, confirm=confirm, machine_id_path=machine_id_path )
            ))

        return constraints


class LicenseSigned( Serializable ):
    """A License and its Ed25519 Signature provenance.  Only a LicenseSigned (and confirmation of
    the author's public key) proves that a License was actually issued by the purported author.  It
    is expected that authors will only sign a valid License.

    The public key of the author must be confirmed through independent means.  One typical means is
    by checking publication on the author's domain (the default behaviour w/ confirm=None), eg.:

        awesome-tool.crypto-licensing._domainkey.awesome-inc.com 86400 IN TXT \
            "v=DKIM1; k=ed25519; p=PW847sz.../M+/GZc="


    Authoring a License
    -------------------

    A software issuer (or end-user, in the case of machine-specific or numerically limited Licenses)
    must create new Licenses.

        >>> from crypto_licensing import author, issue, verify

    First, create a Keypair, including both signing (private, .sk) and verifying (public, .vk) keys:

        >>> signing_keypair = author( seed=b'our secret 32-byte seed material' )

    Then, create a License, identifying the author by their public key, and the product.  This
    example is a perpetual license (no start/length), for any machine.

        >>> license = License( author = "Awesome, Inc.", product = "Awesome Tool", \
                author_domain = "awesome-inc.com", author_pubkey = signing_keypair.vk, \
                confirm=False ) # since awesome-inc.com doesn't actually exist...

    Finally, issue the LicenseSigned containing the License and its Ed25519 Signature provenance:

        >>> provenance = issue( license, signing_keypair, confirm=False )
        >>> provenance_ser = provenance.serialize( indent=4 )
        >>> print( provenance_ser.decode( 'UTF-8' ) )
        {
            "license":{
                "author":"Awesome, Inc.",
                "author_domain":"awesome-inc.com",
                "author_pubkey":"PW847szICqnQBzbdr5TAoGO26RwGxG95e3Vd/M+/GZc=",
                "author_service":"awesome-tool",
                "client":null,
                "client_pubkey":null,
                "dependencies":null,
                "length":null,
                "machine":null,
                "product":"Awesome Tool",
                "start":null
            },
            "signature":"MiOGUpkv6/RWzI/C/VP1Ncn7N4WZa0lpiVzETZ4CJsLSo7qGLxIx+X+4tal16CcT+BUW1cDwJtcTftI5z+RHAQ=="
        }


    De/Serializing Licenses
    -----------------------

    Licenses are typically stored in files, in the configuration directory path of the application.

        import json
        # Locate, open, read
        #with config_open( "application.crypto-licencing", 'r' ) as provenance_file:
        #    provenance_ser	= provenance_file.read()
        >>> provenance_dict = json.loads( provenance_ser )

    Or use the crypto_licensing.load() API to get them all into a dict, with
    the license file basename deduced from your __package__ or __file__ name:

        import crypto_licensing as cl
        licenses		= dict( cl.load(
            filename	= __file__,
            confirm	= False, # don't check signing key validity via DKIM
        ))

    Validating Licenses
    -------------------

    Somewhere in the product's code, the License is loaded and validated.

        >>> provenance_load = LicenseSigned( confirm=False, **provenance_dict )
        >>> print( provenance_load )
        {
            "license":{
                "author":"Awesome, Inc.",
                "author_domain":"awesome-inc.com",
                "author_pubkey":"PW847szICqnQBzbdr5TAoGO26RwGxG95e3Vd/M+/GZc=",
                "author_service":"awesome-tool",
                "client":null,
                "client_pubkey":null,
                "dependencies":null,
                "length":null,
                "machine":null,
                "product":"Awesome Tool",
                "start":null
            },
            "signature":"MiOGUpkv6/RWzI/C/VP1Ncn7N4WZa0lpiVzETZ4CJsLSo7qGLxIx+X+4tal16CcT+BUW1cDwJtcTftI5z+RHAQ=="
        }
        >>> verify( provenance_load, confirm=False )
        {}

    """

    __slots__			= ('license', 'signature')
    serializers			= dict(
        signature	= into_b64,
    )

    def __init__( self, license, author_sigkey=None, signature=None, confirm=None,
                  machine_id_path=None ):
        """Given an ed25519 signing key (32-byte private + 32-byte public), produce the provenance
        for the supplied License.

        Normal constructor calling convention to take a License and a signing key and create
        a signed provenance:

            LicenseSigned( <License>, <Keypair> )

        To reconstruct from a dict (eg. recovered from a .crypto-licensing file):

            LicenseSigned( **provenance_dict )

        """
        if isinstance( license, type_str_base ):
            license		= json.loads( license )  # Deserialize License, if necessary
        assert isinstance( license, (License, dict) ), \
            "Require a License or its serialization dict, not a {!r}".format( license )
        if isinstance( license, dict ):
            license		= License( confirm=confirm, machine_id_path=machine_id_path, **license )
        self.license		= license

        assert signature or author_sigkey, \
            "Require either signature, or the means to produce one via the author's signing key"
        if author_sigkey and not signature:
            # Sign our default serialization, also confirming that the public key matches
            self.signature	= self.license.sign(
                sigkey=author_sigkey, pubkey=self.license.author.pubkey )
        elif signature:
            # Could be a hex-encoded signature on deserialization, or a 64-byte signature.  If both
            # signature and author_sigkey, we'll just be confirming the supplied signature, below.
            self.signature	= into_bytes( signature, ('base64',) )

        self.verify(
            author_pubkey	= author_sigkey,
            confirm		= confirm,
            machine_id_path	= machine_id_path,
        )

    def verify(
        self,
        author_pubkey	= None,
        signature	= None,
        confirm		= None,
        machine_id_path	= None,
        **constraints
    ):
        return self.license.verify(
            author_pubkey	= author_pubkey or self.license.author.pubkey,
            signature		= signature or self.signature,
            confirm		= confirm,
            machine_id_path	= machine_id_path,
            **constraints )


class KeypairPlaintext( Serializable ):
    """De/serialize the plaintext Ed25519 private and public key material.  Order of arguments is
    NOT the same as ed25519.Keypair, b/c the public vk is optional.

    """
    __slots__			= ('sk', 'vk')
    serializers			= dict(
        sk		= into_b64,
        vk		= into_b64,
    )

    def __init__( self, sk=None, vk=None ):
        """Support sk and optionally vk to derive and verify the Keypair.  At minimum, the first 256
        bits of private key material must be supplied; the remainder of the 512-bit signing key is a
        copy of the public key.

        """
        if not sk and not vk:
            sk			= author( why="No Keypair supplied to KeypairPlaintext" )
        if hasattr( sk, 'sk' ):
            # Provided with a raw ed25519.Keypair or KeypairPlaintext; use its sk; retain any supplied vk for confirmation
            _,self.sk		= into_keys( sk )
        else:
            self.sk		= into_bytes( sk, ('base64',) )
        assert len( self.sk ) in (32, 64), \
            "Expected 256-bit or 512-bit Ed25519 Private Key, not {}-bit {!r}".format(
                len( self.sk ) * 8, self.sk )
        if vk:
            self.vk		= into_bytes( vk, ('base64',) )
            assert len( self.vk ) == 32, \
                "Expected 256-bit Ed25519 Public Key, not {}-bit {!r}".format(
                    len( self.vk ) * 8, self.vk )
            assert len( self.sk ) != 64 or self.vk == self.sk[32:], \
                "Inconsistent Ed25519 signing / public keys in supplied data"
        elif len( self.sk ) == 64:
            self.vk		= self.sk[32:]
        else:
            self.vk		= None
        # We know into_keypair is *only* going to use the self.sk[:32] (and optionally self.vk to
        # verify), so we've recovered enough to call it.
        self.vk, self.sk	= self.into_keypair()

    def into_keypair( self, **kwds ):
        """No additional data required to obtain Keypair; just the leading 256-bit private key material
        of the private key.

        """
        keypair			= author( seed=self.sk[:32], why="provided plaintext signing key" )
        if self.vk:
            assert keypair.vk == self.vk, \
                "Failed to derive matching Ed25519 public key from supplied private key data"
        return keypair


class KeypairCredentialError( Exception ):
    """Something is wrong with the provided Keypair credentials."""
    pass


class KeypairEncrypted( Serializable ):
    """De/serialize the keypair encrypted derivation seed, and the salt used in combination with the
    supplied username and password to derive the symmetric encryption key for encrypting the seed.
    The supported derivation(s):

        sha256:		hash of salt + username + password

    The 256-bit Ed25519 Keypair seed is encrypted using ChaCha20Poly1305 w/ the salt and derived
    key.  The salt and ciphertext are always serialized in hex, to illustrate that it is not Ed25519
    Keypair data.

    Can be supplied w/ a raw signing key or an ed25519.Keypair as an unencrypted key, along with
    username/password.  If no signing key at all is provided, one will be generated.

    """
    __slots__			= ('salt', 'ciphertext')
    serializers			= dict(
        salt		= into_hex,
        ciphertext	= into_hex,
    )

    def __init__( self, sk=None, vk=None, salt=None, ciphertext=None, username=None, password=None ):
        assert bool( ciphertext and salt ) ^ bool( password and username ), \
            "Insufficient data to create an Encrypted Keypair"
        if not ( ciphertext and salt ) and not sk:
            sk			= author( why="No Keypair supplied to KeypairEncrypted" )
        if hasattr( sk, 'sk' ):
            # Provided with a raw ed25519.Keypair or KeypairPlaintext; extract its sk, and use any supplied vk for confirmation
            _,edsk		= into_keys( sk )
            sk			= into_b64( edsk )
        if salt:
            self.salt		= into_bytes( salt, ('hex',) )
        else:
            # If salt not supplied, supply one -- but we obviously can't be given an encrypted seed!
            assert sk and not ciphertext, \
                "Expected unencrypted keypair if no is salt provided"
            self.salt		= os.urandom( 12 )
        assert len( self.salt ) == 12, \
            "Expected 96-bit salt, not {!r}".format( self.salt )
        if ciphertext:
            # We are provided with the encrypted seed (tag + ciphertext).  Done!  But, we don't know
            # the original Keypair, here, so we can't verify below.
            self.ciphertext	= into_bytes( ciphertext, ('hex',) )
            assert len( self.ciphertext ) * 8 == 384, \
                "Expected 384-bit ChaCha20Poly1305-encrypted seed, not a {}-bit {!r}".format(
                    len( self.ciphertext ) * 8, self.ciphtertext )
            keypair		= None
        else:
            # We are provided with the unencrypted signing key.  We must encrypt the 256-bit private
            # key material to produce the seed ciphertext.  Remember, the Ed25519 private signing
            # key always includes the 256-bit public key appended to the raw 256-bit private key
            # material.
            sk			= into_bytes( sk, ('base64',) )
            seed		= sk[:32]
            keypair		= author( seed=seed, why="provided unencrypted signing key" )
            if vk:
                vk		= into_bytes( vk, ('base64',) )
                assert keypair.vk == vk, \
                    "Failed to derive Ed25519 signing key from supplied data"
            key			= self.key( username=username, password=password )
            cipher		= ChaCha20Poly1305( key )
            plaintext		= bytearray( seed )
            nonce		= self.salt
            self.ciphertext	= bytes( cipher.encrypt( nonce, plaintext ))
        if username and password:
            # Verify MAC by decrypting w/ username and password, if provided
            keypair_rec		= self.into_keypair( username=username, password=password )
            assert keypair is None or keypair_rec == keypair, \
                "Failed to recover original key after decryption"

    def key( self, username, password ):
        # The username, which is often an email address, should be case-insensitive.
        username		= username.lower()
        username		= username.encode( 'UTF-8' )
        password		= password.encode( 'UTF-8' )
        m			= hashlib.sha256()
        m.update( self.salt )
        m.update( username )
        m.update( password )
        return m.digest()

    def into_keypair( self, username=None, password=None ):
        """Recover the original signing Keypair by decrypting with the supplied data.  Raises a
        KeypairCredentialError on decryption failure.

        """
        assert username and password, \
            "Cannot recover Encrypted Keypair without username and password"
        key			= self.key( username=username, password=password )
        cipher			= ChaCha20Poly1305( key )
        nonce			= self.salt
        ciphertext		= bytearray( self.ciphertext )
        try:
            plaintext		= bytes( cipher.decrypt( nonce, ciphertext ))
        except Exception:
            raise KeypairCredentialError(
                "Failed to decrypt ChaCha20Poly1305-encrypted Keypair w/ {}'s credentials".format( username ))
        keypair			= author( seed=plaintext, why="decrypted w/ {}'s credentials".format( username ))
        return keypair


def author(
    seed		= None,
    why			= None,
):
    """Prepare to author Licenses, by creating an Ed25519 keypair."""
    keypair			= ed25519.crypto_sign_keypair( seed )
    log.info( "Created Ed25519 signing keypair  w/ Public key: {vk_b64}{why}".format(
        vk_b64=into_b64( keypair.vk ), why=" ({})".format( why ) if why else "" ))
    return keypair


def issue(
    license,
    author_sigkey,
    signature		= None,
    confirm		= None,
    machine_id_path	= None,
):
    """If possible, issue the license signed with the supplied signing key. Ensures that the license
    is allowed to be issued, by verifying the signatures of the tree of dependent license(s) if any.

    The holder of an author secret key can issue any license they wish (so long as it is compatible
    with any License dependencies).

    Generally, a license may be issued if it is more "specific" (less general) than any License
    dependencies.  For example, a License could specify that it can be used on *any* 1
    installation.  The holder of the license may then issue a License specifying a the machine ID
    of a certain computer.  The software then confirms successfully that the License is allocated
    to *this* computer.

    Of course, this is all administrative; any sufficiently dedicated programmer can simply remove
    the License checks from the software.  However, such people are *not* Clients: they are simply
    thieves.  The issuance and checking of Licenses is to help support ethical Clients in confirming
    that they are following the rules of the software author.

    """
    return LicenseSigned(
        license,
        author_sigkey,
        signature	= signature,
        confirm		= confirm,
        machine_id_path	= machine_id_path )


def verify(
    provenance,
    author_pubkey	= None,
    signature		= None,
    confirm		= None,
    machine_id_path	= None,
    dependencies	= True,
    **constraints
):
    """Verify that the supplied License or LicenseSigned contains a valid signature, and that the
    License follows the rules in all of its License dependencies.  Optionally, 'confirm' the
    validity of any public keys.

    Apply any additional constraints, returning a License serialization dict satisfying them.  If
    you plan to issue a new LicenseSigned, it is recommended to include your author, author_domain
    and product names, and perhaps also the client and client_pubkey of the intended License
    recipient.

    Works with either a License and signature= keyword parameter, or a LicenseSigned provenance.

    Defaults to demands that any LicenseSigned dependencies are included in the resultant remaining
    constraints, so that a sub-License can be produced.

    """
    return provenance.verify(
        author_pubkey	= author_pubkey,
        signature	= signature or provenance.signature,
        confirm		= confirm,
        machine_id_path	= machine_id_path,
        dependencies	= dependencies,
        **constraints )


def load(
    basename		= None,
    mode		= None,
    extension		= None,
    confirm		= None,
    machine_id_path	= None,
    filename		= None,
    package		= None,
    skip		= "*~",
    **kwds  # eg. extra=["..."], reverse=False, other open() args; see config_open
):
    """Open and load all crypto-lic[ens{e,ing}] file(s) found on the config path(s) (and any
    extra=[...,...]  paths) containing a LicenseSigned provenance record.  By default, use the
    provided package's (your __package__) name, or the executable filename's (your __file__)
    basename.  Assumes '<basename>.crypto-lic*', if no extension provided.

    Applies glob pattern matching via config_open....

    Yields the resultant (filename, LicenseSigned) provenance(s), or an Exception if any
    glob-matching file is found that doesn't contain a serialized LicenseSigned.

    """
    name		= deduce_name(
        basename=basename, extension=extension or LICPATTERN,
        filename=filename, package=package )
    for f in config_open( name=name, mode=mode, skip=skip, **kwds ):
        with f:
            prov_ser		= f.read()
            prov_name		= f.name
        prov_dict		= json.loads( prov_ser )
        prov			= LicenseSigned(
            confirm=confirm, machine_id_path=machine_id_path, **prov_dict )
        yield prov_name, prov


def load_keys(
    basename	= None,
    mode	= None,
    extension	= None,
    filename	= None,
    package	= None,		# For deduction of basename
    username	= None,
    password	= None,		# Decryption credentials to use
    every	= False,
    detail	= True,		# Yield every file w/ origin + credentials info or exception?
    skip	= "*~",
    **kwds                      # eg. extra=["..."], reverse=False, other open() args; see config_open
):
    """Load Ed25519 signing Keypair(s) from glob-matching file(s) with any supplied credentials.
    Yields all Encrypted/Plaintext Keypairs successfully opened (may be none at all), as a sequence
    of:

        <filename>, <Keypair{Encrypted,Plaintext}>, <credentials dict>, <Keypair/Exception>

    If every=True, then every file found will be returned with every credential, and an either
    Exception explaining why it couldn't be opened, or the resultant decrypted Ed25519 Keypair.
    Otherwise, only successfully decrypted Keypairs will be returned.

    - Read the plaintext Keypair's public/private keys.

      WARNING: Only perform this on action on a secured computer: this file contains your private
      signing key material in plain text form!

    - Load the encrypted seed (w/ a random salt), and:
      - Derive the decryption symmetric cipher key from the salt + username + password

        The plaintext 256-bit Ed25519 private key seed is encrypted using ChaCha20Poly1305 with the
        symmetric cipher key using the (same) salt as a Nonce.  Since the random salt is only (ever)
        used to encrypt one thing, it satisfies the requirement that the same Nonce only ever be
        used once to encrypt something using a certain key.

    - TODO: use a second Keypair's private key to derive a shared secret key

      Optionally, this Signing Keypair's derivation seed can be protected by a symmetric cipher
      key derived from the *public* key of this signing key, and the *private* key of another
      Ed25519 key using diffie-hellman.  For example, one derived via Argon2 from an email +
      password + salt.

    Therefore, the following deserialized Keypair dicts are supported:

    Unencrypted Keypair:

        {
            "sk":"bw58LSvuadS76jFBCWxkK+KkmAqLrfuzEv7ly0Y3lCLSE2Y01EiPyZjxirwSjHoUf9kz9meeEEziwk358jthBw=="
            "vk":"qZERnjDZZTmnDNNJg90AcUJZ+LYKIWO9t0jz/AzwNsk="
        }

    Unencrypted Keypair from just 256-bit seed (which is basically the first half of a full .sk
    signing key with a few bits normalized), and optional public key .vk to verify:

        {
            "seed":"bw58LSvuadS76jFBCWxkK+KkmAqLrfuzEv7ly0Y3lC=",
            "vk":"qZERnjDZZTmnDNNJg90AcUJZ+LYKIWO9t0jz/AzwNsk="
        }

    384-bit ChaCha20Poly1503-Encrypted seed (ya, don't use a non-random salt...):
        {
            "salt":"000000000000000000000000",
            "ciphertext":"d211f72ba97e9cdb68d864e362935a5170383e70ea10e2307118c6d955b814918ad7e28415e2bfe66a5b34dddf12d275"
        }

    NOTE: For encrypted Keypairs, we do not need to save the "derivation" we use to arrive at
    the cryptographic key from the salt + username + password, since the encryption used includes a
    MAC; we try each supported derivation.

    """
    issues			= []
    found			= 0
    name		= deduce_name(
        basename=basename, extension=extension or KEYPATTERN, filename=filename, package=package )
    for f in config_open( name=name, mode=mode, skip=skip, **kwds ):
        try:
            with f:
                f_name		= f.name
                f_ser		= f.read()
            log.isEnabledFor( logging.DEBUG ) and log.debug( "Read Keypair... data from {}: {}".format( f_name, f_ser ))
            keypair_dict		= json.loads( f_ser )
        except Exception as exc:
            log.debug( "Failure to load KeypairEncrypted/Plaintext from {}: {}".format(
                f_name, exc ))
            issues.append( (f_name, exc ) )
            continue
        # Attempt to recover the different Keypair...() types, from most stringent requirements to least.
        encrypted		= None
        try:
            encrypted		= KeypairEncrypted( **keypair_dict )  # accepts ciphertext, salt
            keypair		= encrypted.into_keypair( username=username, password=password )
            log.info( "Recover Ed25519 KeypairEncrypted w/ Public key: {} (from {}) w/ credentials {} / {}".format(
                into_b64( keypair.vk ), f_name, username, '*' * len( password )))
            if detail:
                yield f_name, encrypted, dict( username=username, password=password ), keypair
            else:
                yield f_name, keypair
            found	       += 1
            continue
        except KeypairCredentialError as exc:
            # The KeypairEncrypted was OK -- just the credentials were wrong; don't bother trying as non-Encrypted
            log.debug( "Failed to decrypt KeypairEncrypted: {exc}".format(
                exc=''.join( traceback.format_exception( *sys.exc_info() )) if log.isEnabledFor( logging.TRACE ) else exc ))
            issues.append( (f_name, exc) )
            if every:
                if detail:
                    yield f_name, encrypted, dict( username=username, password=password ), exc
                else:
                    yield f_name, exc
            continue
        except Exception as exc:
            # Some other problem attempting to interpret this thing as a KeypairEncrypted; carry on and try again
            log.debug( "Failed to decode  KeypairEncrypted: {exc}".format(
                exc=''.join( traceback.format_exception( *sys.exc_info() )) if log.isEnabledFor( logging.TRACE ) else exc ))

        plaintext		= None
        try:
            plaintext		= KeypairPlaintext( **keypair_dict )
            keypair		= plaintext.into_keypair()
            log.isEnabledFor( logging.DEBUG ) and log.debug(
                "Recover Ed25519 KeypairPlaintext w/ Public key: {} (from {})".format(
                    into_b64( keypair.vk ), f_name ))
            if detail:
                yield f_name, plaintext, {}, keypair
            else:
                yield f_name, keypair
            found	       += 1
            continue
        except Exception as exc:
            # Some other problem attempting to interpret as a KeypairPlaintext
            issues.append( (f_name, exc) )
            if every:
                if detail:
                    yield f_name, plaintext, {}, exc
                else:
                    yield f_name, exc
            log.debug( "Failed to decode KeypairPlaintext: {exc}".format(
                exc=''.join( traceback.format_exception( *sys.exc_info() )) if log.isEnabledFor( logging.TRACE ) else exc ))
    if not found:
        log.info( "Cannot load Keypair(s) from {name}: {reasons}".format(
            name=name, reasons=', '.join( "{}: {}".format( fn, exc ) for fn, exc in issues )))


def check(
    basename		= None,			# Keypair/License file basename and open mode
    mode		= None,
    extension_keypair	= None,
    extension_license	= None,
    filename		= None,			# ...or, deduce basename from supplied data
    package		= None,
    username		= None,			# Keypair protected w/ supplied credentials
    password		= None,
    confirm		= None,
    machine_id_path	= None,
    constraints		= None,
    skip		= "*~",
    **kwds					# eg. extra=["..."], reverse=False, other open() args; see config_open
):
    """Check that a License has been issued to our agent, for this machine and/or username,
    yielding a sequence of <Keypair>, None/<LicenseSigned> found.

    Thus, if a <Keypair> is found but no <LicenseSigned> can be found or assigned, the caller can
    use the <Keypair> in a subsequent licence request, and then save the received LicenseSigned
    provenance for future use.


    Can deduce a basename from provided filename/package, if desired

    - Load our Ed25519 Keypair
      - Create one, if not found
    - Load our Licenses
      - Obtain one, if not found

    If an Ed25519 Agent signing authority or License must be created, the default location where
    they will be stored is in the most general configuration path location that is writable.

    Agent signing authority is usually machine- or username-specific: a License to run a program on
    one machine and/or for one username usually doesn't transfer to another machine/username.

        <basename>-<machine-id>.crypto-key...
        <basename>-<machine-id>.crypto-lic...

    """
    # Load any Keypair{Plaintext,Encrypted} available, and convert to a ed25519.Keypair,
    # ready for signing/verification.
    keypairs			= {}
    for key_path, keypair_typed, cred, keypair_or_error in load_keys(
            basename=basename, mode=mode, extension=extension_keypair,
            filename=filename, package=package,
            every=True, detail=True,
            username=username, password=password,
            skip=skip, **kwds
    ):
        if isinstance( keypair_or_error, ed25519.Keypair ):
            keypairs.setdefault( key_path, keypair_or_error )
            continue
        log.info( "{key_path:32}: {exc}".format(
            key_path=os.path.basename( key_path ), exc=keypair_or_error ))

    log.log( logging.DETAIL, "{:48} {}".format( 'File', 'Keypair' ))
    for n,k in keypairs.items():
        log.log( logging.DETAIL, "{:48} {}".format( os.path.basename( n ), into_b64( k.vk )))

    licenses			= dict( load(
        basename=basename, mode=mode, extension=extension_license,
        filename=filename, package=package,
        confirm=confirm, machine_id_path=machine_id_path, skip=skip, **kwds
    ))

    # See if license(s) has been (or can be) issued to our Agent keypair(s) (ie. was issued to this
    # keypair as a specific client_pubkey or was non-client-specific, and then was signed by our
    # Keypair), for this Machine ID.
    log.log( logging.NORMAL, "{:48} {:20} {:20} {}".format( 'File', 'Client', 'Author', 'Product' ))
    key_seen			= set()
    for key_path,keypair in keypairs.items():
        if keypair in key_seen:
            continue
        key_seen.add( keypair )

        # For each unique Keypair, discover any LicenceSigned we've been issued, or can issue.
        lic_path,lic		= None,None	 # If no Licensese found, at all
        prov,reasons		= None,[]        # Why didn't any Licenses qualify?
        for lic_path, lic in licenses.items():
            # Was this license issued by our Keypair Agent as the author?  This means that one was
            # issued by some author, with our Keypair Agent as a client, and we (previously) issued
            # and saved it.
            try:
                lic.verify(
                    author_pubkey	= keypair.vk,
                    confirm		= confirm,
                    machine_id_path	= machine_id_path,
                    dependencies	= False,
                    **( constraints or {} )
                )
            except Exception as exc:
                log.info( "Checked {lic_path:32} / {key_path:32}: {exc}".format(
                    lic_path=os.path.basename( lic_path ), key_path=os.path.basename( key_path ),
                    exc=''.join( traceback.format_exception( *sys.exc_info() )) if log.isEnabledFor( logging.TRACE ) else exc ))
                reasons.append( str( exc ))
            else:
                # This license passed muster w/ the constraints supplied and it was already issued
                # to us; we're done.
                prov		= lic
                break

            # License not already issued to us; check whether it could be ours w/ some remaining
            # constraints requirements.  We're going to try to issue a sub-License, so include the
            # LicenseSigned itself in the resultant computed constraints requirements.
            try:
                requirements	= lic.verify(
                    confirm		= confirm,
                    machine_id_path	= machine_id_path,
                    dependencies	= True,
                    **( constraints or {} )
                )
            except Exception as exc:
                log.info( "Verify  {lic_path:32} / {key_path:32}: {exc}".format(
                    lic_path=os.path.basename( lic_path ), key_path=os.path.basename( key_path ),
                    exc=''.join( traceback.format_exception( *sys.exc_info() )) if log.isEnabledFor( logging.TRACE ) else exc ))
                reasons.append( str( exc ))
                continue

            # Validated this License is sub-Licensable by this Keypair Agent!  This License is
            # available to be issued to us and verified, now, as one of our License dependencies.
            # Craft a new License, w/ the requirements produced by the verify, above.  If the
            # LicenseSigned provenance can be issued, it has fully passed verification.  We are
            # assuming that the License is sub-licensable by this agent's Keypair as the client; if
            # the License allows anonymous clients (no lic.license.client specified), then make an
            # ad-hoc Agent record.
            log.log( logging.DETAIL, "Require {requirements!r}".format( requirements=requirements ))
            try:
                author		= lic.license.client
                if not author:
                    pubkey	= into_b64( keypair.vk )
                    author	= Agent( name=pubkey, pubkey=pubkey )
                prov		= issue(
                    License(
                        author		= author,
                        confirm		= confirm,
                        machine_id_path	= machine_id_path,
                        **requirements
                    ),
                    author_sigkey	= keypair.sk,
                    confirm		= confirm,
                    machine_id_path	= machine_id_path,
                )
            except Exception as exc:
                log.info( "Issuing {lic_path:32} / {key_path:32} failure: {exc}".format(
                    lic_path=os.path.basename( lic_path ), key_path=os.path.basename( key_path ),
                    exc=''.join( traceback.format_exception( *sys.exc_info() )) if log.isEnabledFor( logging.TRACE ) else exc ))
                reasons.append( str( exc ))
                continue
            else:
                # The License was available to be issued as one of our dependencies, and passed
                # remaining constraints requirements; Use prov; prov_path remains None.
                break

        log.log( logging.DETAIL if prov is None else logging.NORMAL, "{!r:48} {!r:20.20} {!r:20.20} {!r:16.16}: {}".format(
            'N/A' if not lic_path else os.path.basename( lic_path ),
            'N/A' if not lic or not lic.license.client else "{}/{}".format( lic.license.client.name, into_b64( lic.license.client.pubkey )),
            'N/A' if not lic else "{}/{}".format( lic.license.author.name, into_b64( lic.license.author.pubkey )),
            'N/A' if not lic or not lic.license.author.product else lic.license.author.product,
            'OK' if prov else ', '.join( reasons )))

        yield keypair, prov  # Reports <Keypair>,None/<LicenseSigned>


def authorize(
    domain, product,			# The product we're licensing
    service		= None,		# ..can be deduced from product, usually
    username		= None,		# The credentials for our agent's Keypair
    password		= None,
    basename		= None,
    filename		= None,
    package		= None,
    confirm		= None,
    machine_id_path	= None,
    constraints		= None,
    reverse		= True,		# Default to look from most specific, to most general location
    reverse_save	= None,		# Default to save in the opposite of look-up (most general, to most specific location)
    extra		= None,
    skip		= "*~",
):
    """If possible, load and verify the agent's KeyPair (creating one if necessary), and the
    available LicenseSigned for the product.  If it can be proven that:

    1) The KeyPair belongs to the agent (unencrypted, decrypted or signed by the agent)
    2) the License is signed by the agent's KeyPair signing key (proving that the agent asked
       for it, and it was issued to the agent)
    3) The License was issued for the machine-id on which we are running, and remains valid
    4) The License contains the required capabilities

    then the requested capability is authorized.

    Otherwise, use the agent's Keypair to obtain a License for the specified capability/constraints.

    """
    class State( Enum ):
        START	= 0
        TEST	= 1
        CREATE	= 2

    state		= State.START
    while state is not State.CREATE:
        state		= State( state.value + 1 )
        log.warning( "Authorizing in state {state!r}".format( state=state ))
        if state is State.CREATE:
            keypair		= author( why="End-user Keypair" )
            keypair		= KeypairEncrypted(
                sk		= keypair.sk,
                username	= username,
                password	= password,
            ) if username and password else KeypairPlaintext(
                sk		= keypair.sk,
            )
            keypair_path	= None
            # Defaults to save in the most general, to most specific location
            for f in config_open_deduced(
                basename	= basename,
                mode		= "wb",
                extension	= KEYEXTENSION,
                filename	= filename,
                package		= package,
                reverse		= not reverse if reverse_save is None else reverse_save,
                extra		= extra,
                skip		= None,  # For writing/creating, of course we don't want to "skip" anything...
            ):
                try:
                    keypair_path	= f.name
                    log.warning( "Trying {path}".format( path=keypair_path ))
                    with f:
                        f.write( keypair.serialize( indent=4, encoding='UTF-8' ))
                        f.flush()
                except Exception as exc:
                    log.detail( "Writing End-user Keypair to {path} failed: {exc}".format(
                        path	= keypair_path,
                        exc	= exc,
                    ))
                    keypair_path	= None
                else:
                    log.normal( "Writing End-user Keypair to {path}".format(
                        path	= keypair_path,
                    ))
                    break

        # Try to find all keypairs and licenses.  As soon as we've found *at least* one, indicate that
        # we are done by switching to the CREATE state.
        for key,lic in check(
            username	= username,
            password	= password,
            basename	= basename,
            filename	= filename,
            package	= package,
            confirm	= confirm,
            machine_id_path = machine_id_path,
            reverse	= reverse,
            extra	= extra,
        ):
            yield key,lic
            state	= State.CREATE
