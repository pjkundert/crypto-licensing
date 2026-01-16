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

import codecs
import copy
import hashlib
import json
import logging
import struct
import sys
import traceback

from ..misc		import (
    into_bytes, into_b64,
)

from ..			import ed25519

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( "serializable" )


def into_JSON( thing, indent=None, default=None, prefix=None ):
    """Convert thing to JSON, optionally prefixing every line.

    Ensure lists are in some deterministic order, or the JSON serialization won't be identical
    between invocations.

    """
    def endict( x ):
        try:
            return dict( x )
        except Exception as exc:
            if default:
                return default( x )
            log.warning("Failed to JSON serialize {!r}: {}".format( x, exc ))
            raise
    # Unfortunately, Python2 json.dumps w/ indent emits trailing whitespace after "," making
    # tests fail.  Make the JSON separators whitespace-free, so the only difference between the
    # signed serialization and an pretty-printed indented serialization is the presence of
    # whitespace.
    separators			= (',', ':')
    text			= json.dumps(
        thing, sort_keys=True, indent=indent, separators=separators, default=endict )
    if prefix and text:
        text			= '\n'.join( prefix + line for line in text.splitlines() )
    return text


class Serializable( object ):
    """A base-class that provides a deterministic Unicode JSON serialization of every __slots__
    and/or __dict__ attribute, and a consistent dict representation of the same serialized data.
    Access attributes directly to obtain underlying types.

    Hidden attributes starting with _... are never included in serialization; the base Serializable
    has an _path, which identifies a filesystem path where the Serializable has been stored.

    Uses __slots__ in derived classes to identify serialized attributes; traverses the class
    hierarchy's MRO to identify all attributes to serialize.  Output serialization is always in
    attribute-name sorted order.

    If an attribute requires special serialization handling (other than simple conversion to 'str'),
    then include it in the class' serializers dict, eg:

        serializers		= dict( special = into_hex )

    It is expected that derived class' constructors will deserialize when presented with keywords
    representing all keys.

    Optionally indicate where the data was '_from', be it a file Path, or a License, for example.
    The ultimate user of the Serializable data may verify the provenance of the data.

    """

    __slots__			= ('_from', )
    serializers			= {}

    def __init__( self, _from=None ):
        self._from		= _from

    def save( self, f, **kwds ):
        """Writes the serialization to the specified open <file> f, remembering the <file>.path"""
        kwds.setdefault( 'indent', 4 )
        kwds.setdefault( 'encoding', 'UTF-8' )
        ser			= self.serialize( **kwds )
        log.debug( "Saving {} bytes to {}".format( len( ser ), f.name ))
        f.write( ser )
        f.flush()
        self._from		= f.name
        return self._from

    def vars( self ):
        """Returns all key/value pairs defined for the object, either from __slots__ and/or __dict__
        (except hidden _...)."""
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
                if key[0] == '_':  # ignore hidden _... vars, eg. _from.
                    continue
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
        def suppressed( key, val ):
            if self.serializer( key ) is False:		# Explicitly suppressed from serialization
                return True
            if val is None:				# Values of None are suppressed
                return True
            empty		= getattr( val, 'empty', None )
            if empty is not None and hasattr( empty, '__call__' ) and empty():
                return True
            return False

        for key,val in self.vars():
            if every or not suppressed( key, val ):
                yield key

    def __contains__( self, key ):
        """Checks if key is in the Serializable container (__slots__ or __dict__), without ignoring
        "suppressed" (.empty()/None/no-serializer) keys.  In other words -- may include keys that
        are suppressed in the standard serialization.

        """
        if key in self.keys( every=True ):
            return True
        return False

    def serializer( self, key ):
        """Finds any custom serialization formatter specified for the given attribute, defaults to None.

        """
        for cls in type( self ).__mro__:
            try:
                return cls.serializers[key]
            except (AttributeError, KeyError):
                pass

    def __getitem__( self, key ):
        """Returns the serialization of the requested key, passing thru values without a serializer.
        We don't use our own __contains__, because this may be overridden in derive Serialized
        classes to represent the semantics of that object type (eg. a Timespan, ...).

        """
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
        raise IndexError( "{} not found in keys: {}".format( key, ', '.join( self.keys( every=True ))))

    def get( self, key, default=None ):
        try:
            return self.__getitem__( key )
        except (KeyError, IndexError):
            return default

    def __setitem__( self, key, value ):
        if key in set( dir( self )) - set( self.keys( every=True )):
            raise IndexError( "{} is not a valid {} keys".format( key, self.__class__.__name__ ))  # Hidden _... or predefined
        setattr( self, key, value )

    set				= __setitem__

    def setdefault( self, key, default ):
        if key not in self:
            self[key]           = default
        return self[key]

    def __str__( self ):
        return self.JSON()

    def __repr__( self ):
        return '<' + self.__class__.__name__ + (
            " (from {})".format( repr( self._from ))
            if self._from or log.isEnabledFor( logging.DEBUG )
            else ""
        ) + '>'

    def JSON( self, indent=4, default=None, prefix=None ):
        """Return the default readable JSON representation of the present object."""
        return into_JSON( self, indent=indent, default=default, prefix=prefix )

    def serialize( self, indent=None, encoding='UTF-8', default=None, prefix=None ):
        """Return a binary 'bytes' serialization of the present object.  Serialize to JSON, assuming
        any complex sub-objects (eg. License, LicenseSigned) have a sensible dict representation.

        The default serialization (ie. with indent=None, encoding to UTF-8) will be the one used to
        create the digest.

        If there are objects to be serialized that require special handling, they must not have a
        'dict' interface (be convertible to a dict), and then a default may be supplied to serialize
        them (eg. str).

        An optional prefix string may be prepended to each line.

        """
        stream			= self.JSON( indent=indent, default=default, prefix=prefix )
        if encoding:
            stream		= stream.encode( encoding )
        return stream

    def sign( self, sigkey, pubkey=None ):
        """Sign our default serialization, and (optionally) confirm that the supplied public key
        (which will be used to check the signature) is correct, by re-deriving the public key.

        """
        vk, sk			= ed25519.into_keys( sigkey )
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
        pubkey, _		= ed25519.into_keys( pubkey )
        signature		= into_bytes( signature, ('base64',) )
        assert pubkey and signature, \
            "Missing required {}".format(
                ', '.join( () if pubkey else ('public key',)
                           + () if signature else ('signature',) ))
        serialization		= self.serialize()
        try:
            verified		= ed25519.crypto_sign_open( signature + serialization, pubkey )
            return verified
        except Exception:
            log.debug( f"License serialization w/ signature {into_b64( signature )} not signed by pubkey: {into_b64( pubkey )}: {serialization}" )
            raise

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

    def __eq__( self, other ):
        """Serializable things should produce the same digest if equal.  There may be simpler or
        better equality tests, but this is the semantic for Serializable things or their hashes.

        For reasoning, see:
            https://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes

        """
        local_hash		= self.digest()
        if isinstance( other, Serializable ):
            other_hash		= other.digest()
        elif isinstance( other, bytes ) and len( other ) == len( local_hash ):
            other_hash		= other
        else:
            return NotImplemented
        return local_hash == other_hash

    def __ne__( self, other ):
        """Unnecessary under Python3, but needed for Python 2"""
        eq			= self.__eq__( other )
        if eq is NotImplemented:
            return NotImplemented
        return not eq

    def __hash__( self ):
        """Returns a 64-bit signed integer representing the first 8 bytes of the digest"""
        return struct.Struct('<q').unpack( self.digest()[:8] )[0]

    def hexdigest( self ):
        """The SHA-256 hash of the serialization, as a 256-bit (32 byte, 64 character) hex string."""
        return self.digest( 'hex', 'ASCII' )

    def b64digest( self ):
        return self.digest( 'base64', 'ASCII' )
