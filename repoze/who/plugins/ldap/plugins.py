# -*- coding: utf-8 -*-
#
# repoze.who.plugins.ldap, LDAP authentication for WSGI applications.
# Copyright (C) 2008 by Gustavo Narea <http://gustavonarea.net/>
#
# This file is part of repoze.who.plugins.ldap
# <http://code.gustavonarea.net/repoze.who.plugins.ldap/>
#
# repoze.who.plugins.ldap is freedomware: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or any later
# version.
#
# repoze.who.plugins.ldap is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# repoze.who.plugins.ldap. If not, see <http://www.gnu.org/licenses/>.

"""LDAP plugins for repoze.who."""

__all__ = ['LDAPAuthenticatorPlugin', 'LDAPAttributesPlugin']

from zope.interface import implements
import ldap

from repoze.who.interfaces import IAuthenticator, IMetadataProvider


#{ Authenticators


class LDAPAuthenticatorPlugin(object):

    implements(IAuthenticator)

    def __init__(self, ldap_connection, base_dn):
        """Create an LDAP authentication plugin.
        
        By passing an existing LDAPObject, you're free to use the LDAP
        authentication method you want, the way you want.
    
        If the default way to find the DN is not suitable for you, you may want
        to override L{_get_dn}.
        
        This plugin is compatible with any identifier plugin that defines the
        C{login} and C{password} items in the I{identity} dictionary.
        
        @param ldap_connection: An initialized LDAP connection.
        @type ldap_connection: C{ldap.ldapobject.SimpleLDAPObject}
        @param base_dn: The base for the I{Distinguished Name}. Something like
            C{ou=employees,dc=example,dc=org}, to which will be prepended the
            user id: C{uid=jsmith,ou=employees,dc=example,dc=org}.
        @type base_dn: C{unicode}
        @raise ValueError: If at least one of the parameters is not defined.
        
        """
        if base_dn is None:
            raise ValueError('A base Distinguished Name must be specified')
        self.ldap_connection = make_ldap_connection(ldap_connection)
        self.base_dn = base_dn

    # IAuthenticatorPlugin
    def authenticate(self, environ, identity):
        """Return the Distinguished Name of the user to be authenticated.
        
        @attention: The uid is not returned because it may not be unique; the
            DN, on the contrary, is always unique.
        @return: The Distinguished Name (DN), if the credentials were valid.
        @rtype: C{unicode} or C{None}
        
        """
        
        try:
            dn = self._get_dn(environ, identity)
            password = identity['password']
        except (KeyError, TypeError, ValueError):
            return None

        if not hasattr(self.ldap_connection, 'simple_bind_s'):
            environ['repoze.who.logger'].warn('Cannot bind with the provided '
                                              'LDAP connection object')
            return None
        
        try:
            self.ldap_connection.simple_bind_s(dn, password)
            # The credentials are valid!
            return dn
        except ldap.LDAPError:
            return None
    
    def _get_dn(self, environ, identity):
        """
        Return the DN based on the environment and the identity.
        
        It prepends the user id to the base DN given in the constructor:
        
        If the C{login} item of the identity is C{rms} and the base DN is
        C{ou=developers,dc=gnu,dc=org}, the resulting DN will be:
        C{uid=rms,ou=developers,dc=gnu,dc=org}.
        
        @attention: You may want to override this method if the DN generated by
            default doesn't meet your requirements. If you do so, make sure to
            raise a C{ValueError} exception if the operation is not successful.
        @param environ: The WSGI environment.
        @param identity: The identity dictionary.
        @return: The Distinguished Name (DN)
        @rtype: C{unicode}
        @raise ValueError: If the C{login} key is not in the I{identity} dict.
        
        """
        try:
            return u'uid=%s,%s' % (identity['login'], self.base_dn)
        except (KeyError, TypeError):
            raise ValueError

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, id(self))


#{ Metadata providers


class LDAPAttributesPlugin(object):
    """Loads LDAP attributes of the authenticated user."""
    
    implements(IMetadataProvider)
    
    def __init__(self, ldap_connection, attributes=None,
                 filterstr='(objectClass=*)'):
        """
        Fetch LDAP attributes of the authenticated user.
        
        @param ldap_connection: The LDAP connection to use to fetch this data.
        @type ldap_connection: C{ldap.ldapobject.SimpleLDAPObject} or C{str}
        @param attributes: The authenticated user's LDAP attributes you want to
            use in your application; an interable or a comma-separate list of
            attributes in a string, or C{None} to fetch them all.
        @type attributes: C{iterable} or C{str}
        @param filterstr: A filter for the search, as documented in U{RFC4515
            <http://www.faqs.org/rfcs/rfc4515.html>}; the results won't be
            filtered unless you define this.
        @type filterstr: C{str}
        @raise ValueError: If L{make_ldap_connection} could not create a
            connection from C{ldap_connection}, or if C{attributes} is not an
            iterable.
        
        """
        if hasattr(attributes, 'split'):
            attributes = attributes.split(',')
        elif hasattr(attributes, '__iter__'):
            # Converted to list, just in case...
            attributes = list(attributes)
        elif attributes is not None:
            raise ValueError('The needed LDAP attributes are not valid')
        self.ldap_connection = make_ldap_connection(ldap_connection)
        self.attributes = attributes
        self.filterstr = filterstr
    
    # IMetadataProvider
    def add_metadata(self, environ, identity):
        """
        Add metadata about the authenticated user to the identity.
        
        It modifies the C{identity} dictionary to add the metadata.
        
        @param environ: The WSGI environment.
        @param identity: The repoze.who's identity dictionary.
        
        """
        # Search arguments:
        args = (
            identity.get('repoze.who.userid'),
            ldap.SCOPE_BASE,
            self.filterstr,
            self.attributes
        )
        try:
            for (attr_key, attr_value) in self.ldap_connection.search_s(*args):
                identity[attr_key] = attr_value
        except ldap.LDAPError, msg:
            environ['repoze.who.logger'].warn('Cannot add metadata: %s' % \
                                              msg)
            return


#{ Utilities


def make_ldap_connection(ldap_connection):
    """Return an LDAP connection object to the specified server.
    
    If the C{ldap_connection} is already an LDAP connection object, it will
    be returned as is. If it's an LDAP URL, it will return an LDAP connection
    to the LDAP server specified in the URL.
    
    @param ldap_connection: The LDAP connection object or the LDAP URL of the
        server to be connected to.
    @type ldap_connection: C{ldap.LDAPObject}, C{str} or C{unicode}
    @return: The LDAP connection object.
    @rtype: C{ldap.LDAPObject}
    @raise ValueError: If C{ldap_connection} is C{None}.
    
    """
    if isinstance(ldap_connection, str) or isinstance(ldap_connection, unicode):
        return ldap.initialize(ldap_connection)
    elif ldap_connection is None:
        raise ValueError('An LDAP connection must be specified')
    return ldap_connection


#}
