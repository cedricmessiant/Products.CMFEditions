#########################################################################
# Copyright (c) 2004, 2005 Alberto Berti, Gregoire Weber. 
# All Rights Reserved.
# 
# This file is part of CMFEditions.
# 
# CMFEditions is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# CMFEditions is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with CMFEditions; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
#########################################################################
"""Archivist implementation

$Id: ArchivistTool.py,v 1.15 2005/06/24 11:34:08 gregweb Exp $
"""

import os, sys
import time
from StringIO import StringIO
from cPickle import Pickler, Unpickler
import traceback
import re

import zLOG

from Globals import InitializeClass
from Persistence import Persistent
from Acquisition import aq_base
from AccessControl import ClassSecurityInfo, getSecurityManager
from ZODB.PersistentList import PersistentList
from OFS.SimpleItem import SimpleItem
from OFS.ObjectManager import ObjectManager

from Products.CMFCore.utils import UniqueObject, getToolByName
from Products.CMFCore.ActionProviderBase import ActionProviderBase
from Products.CMFCore.interfaces import IOpaqueItems

from Products.CMFEditions.utilities import KwAsAttributes
from Products.CMFEditions.utilities import dereference
from Products.CMFEditions.interfaces.IStorage import StorageError
from Products.CMFEditions.interfaces.IStorage import StorageRetrieveError
from Products.CMFEditions.interfaces.IStorage import StorageUnregisteredError

from Products.CMFEditions.interfaces.IArchivist import IArchivist
from Products.CMFEditions.interfaces.IArchivist import IHistory
from Products.CMFEditions.interfaces.IArchivist import IVersionData
from Products.CMFEditions.interfaces.IArchivist import IPreparedObject
from Products.CMFEditions.interfaces.IArchivist import IAttributeAdapter
from Products.CMFEditions.interfaces.IArchivist import IVersionAwareReference
from Products.CMFEditions.interfaces.IArchivist import IObjectData

from Products.CMFEditions.interfaces.IArchivist import ArchivistError
from Products.CMFEditions.interfaces.IArchivist import ArchivistRegisterError
from Products.CMFEditions.interfaces.IArchivist import ArchivistSaveError
from Products.CMFEditions.interfaces.IArchivist import ArchivistRetrieveError
from Products.CMFEditions.interfaces.IArchivist import ArchivistUnregisteredError


RETRIEVING_UNREGISTERED_FAILED = \
    "Retrieving a version of an unregistered object is not possible. " \
    "Register the object '%s' first. "

def deepcopy(obj):
    """Makes a deep copy of the object using the pickle mechanism.
    """
    stream = StringIO()
    p = Pickler(stream, 1)
    p.dump(aq_base(obj))
    stream.seek(0)
    u = Unpickler(stream)
    return u.load()

class VersionData:
    """
    """
    __implements__ = (IVersionData, )
    
    def __init__(self, data, refs_to_be_deleted, attr_handling_references, 
                 preserved_data, metadata):
        self.data = data
        self.refs_to_be_deleted = refs_to_be_deleted
        self.attr_handling_references = attr_handling_references
        self.preserved_data = preserved_data
        self.sys_metadata = metadata['sys_metadata']
        self.app_metadata = metadata['app_metadata']


class AttributeAdapter(Persistent):
    __implements__ = (IAttributeAdapter, )

    def __init__(self, parent, attr_name, type=None):
        self._parent = aq_base(parent)
        self._name = attr_name
        self._type = type

    def setAttribute(self, obj):
        setattr(self._parent, self._name, obj)

    def getAttribute(self):
        # The attribute may have been removed by a modifier
        return getattr(self._parent, self._name, None)

    def getAttributeName(self):
        return self._name

    def getType(self):
        return self._type


class VersionAwareReference(Persistent):
    """A Reference that is version aware (and in future also location aware).
    """
    __implements__ = (IVersionAwareReference, )

    def __init__(self, **info):
        self.history_id = None
        self.version_id = None
        self.location_id = None
        self.info = info
        
    def setReference(self, target_obj, remove_info=True):
        """See IVersionAwareReference
        """
        storage = getToolByName(target_obj, 'portal_historiesstorage')
        
        # save as much information as possible
        # it may be that the target object is not yet registered with the 
        # storage (aka not under version control)
        target_obj, self.history_id = dereference(target_obj)
        if storage.isRegistered(self.history_id):
            self.version_id = target_obj.version_id
            # XXX the location id has to be gotten from the object directly
            self.location_id = 0 # XXX only one location possible currently
            # XXX store the information if the referenced working copy
            # was unchanged since the last checkin. In this case the 
            # the exact state of the referenced object may be retrieved also.
            # XXX we really need a isUpToDate/isChanged methods!
            
        if remove_info and hasattr(self, 'info'):
            self.info = None


class ArchivistTool(UniqueObject, SimpleItem, ActionProviderBase):
    """
    """

    __implements__ = (
        SimpleItem.__implements__,
        IArchivist,
    )
        
    id = 'portal_archivist'
    alternative_id = 'portal_standard_archivist'
    
    meta_type = 'CMFEditions Portal Archivist Tool'
    
    # make interfaces, exceptions and classes available through the tool
    interfaces = KwAsAttributes(
        IVersionData=IVersionData,
        IVersionAwareReference=IVersionAwareReference,
        IAttributeAdapter=IAttributeAdapter,
    )
    exceptions = KwAsAttributes(
        ArchivistError=ArchivistError,
    )
    classes = KwAsAttributes(
        VersionData=VersionData,
        VersionAwareReference=VersionAwareReference,
        AttributeAdapter=AttributeAdapter,
    )
    
    security = ClassSecurityInfo()
    
    
    # -------------------------------------------------------------------
    # private helper methods
    # -------------------------------------------------------------------
    def _cloneByPickle(self, obj):
        """Returns a deep copy of a ZODB object, loading ghosts as needed.
        """
        modifier = getToolByName(self, 'portal_modifier')
        callbacks = modifier.getOnCloneModifiers(obj)
        if callbacks is not None:
            pers_id, pers_load, inside_orefs, outside_orefs = callbacks[0:4]
        else:
            inside_orefs, outside_orefs = (), ()
    
        stream = StringIO()
        p = Pickler(stream, 1)
        if callbacks is not None:
            p.persistent_id = pers_id
        p.dump(aq_base(obj))
        stream.seek(0)
        u = Unpickler(stream)
        if callbacks is not None:
            u.persistent_load = pers_load
        return u.load(), inside_orefs, outside_orefs


    # -------------------------------------------------------------------
    # methods implementing IArchivist
    # -------------------------------------------------------------------

    security.declarePrivate('prepare')
    def prepare(self, obj, app_metadata=None, sys_metadata={}):
        """
        """
        storage = getToolByName(self, 'portal_historiesstorage')
        modifier = getToolByName(self, 'portal_modifier')
        
        obj, history_id = dereference(obj, zodb_hook=self)
        if storage.isRegistered(history_id):
            # already registered
            version_id = len(self.queryHistory(obj))
            is_registered = True
        else:
            # object isn't under version control yet
            # A working copy being under version control needs to have
            # a history_id, version_id (starts with 0) and a location_id
            # (the current implementation isn't able yet to handle multiple
            # locations. Nevertheless lets set the location id to a well
            # known default value)
            uidhandler = getToolByName(self, 'portal_uidhandler')
            history_id = uidhandler.register(obj)
            version_id = obj.version_id = 0
            obj.location_id = 0
            is_registered = False
        
        # the hard work done here is:
        # 1. ask for all attributes that have to be passed to the 
        #    history storage by reference
        # 2. clone the object with some modifications
        # 3. modify the clone further
        referenced_data = modifier.getReferencedAttributes(obj)
        clone, inside_orefs, outside_orefs = self._cloneByPickle(obj)
        inside_crefs, outside_crefs = modifier.beforeSaveModifier(obj, clone)
        
        # set the version id of the clone to be saved to the repository
        # location_id and history_id are the same as on the working copy
        # and remain unchanged
        clone.version_id = version_id
        
        # return the prepared infos (clone, refs, etc.)
        clone_info = ObjectData(clone, inside_crefs, outside_crefs)
        obj_info = ObjectData(obj, inside_orefs, outside_orefs)
        return PreparedObject(history_id, obj_info, clone_info, 
                              referenced_data, app_metadata, 
                              sys_metadata, is_registered)
        
    security.declarePrivate('register')
    def register(self, prepared_obj):
        """
        """
        # only register at the storage layer if not yet registered
        if not prepared_obj.is_registered:
            storage = getToolByName(self, 'portal_historiesstorage')
            return storage.register(prepared_obj.history_id, 
                                    prepared_obj.clone, 
                                    prepared_obj.referenced_data,
                                    prepared_obj.metadata)

    security.declarePrivate('isUpToDate')
    def isUpToDate(self, obj=None, history_id=None, selector=None):
        """
        """
        storage = getToolByName(self, 'portal_historiesstorage')
        obj, history_id = dereference(obj, history_id, self)
        if not storage.isRegistered(history_id):
            raise ArchivistUnregisteredError(
                "The object %s is not registered" % obj)
        
        modified = storage.getModificationDate(history_id, selector)
        return modified == obj.modified()

    security.declarePrivate('save')
    def save(self, prepared_obj, autoregister=None):
        """
        """
        if not prepared_obj.is_registered:
            if autoregister:
                return self.register(prepared_obj)
            raise ArchivistSaveError(
                "Saving an unregistered object is not possible. Register "
                "the object '%s' first. "% prepared_obj.original.object)
        
        storage = getToolByName(self, 'portal_historiesstorage')
        return storage.save(prepared_obj.history_id, 
                            prepared_obj.clone, 
                            prepared_obj.referenced_data, 
                            prepared_obj.metadata)
            
    security.declarePrivate('retrieve')
    def retrieve(self, obj=None, history_id=None, selector=None, preserve=()):
        """
        """
        # retrieve the object by accessing the right history entry
        # the histories storage called by LazyHistory knows what to do
        # with a None selector
        history = self.getHistory(obj, history_id, preserve)
        try:
            return history[selector]
        except StorageRetrieveError:
            raise ArchivistRetrieveError(
                "Retrieving of '%s' failed. Version '%s' does not exist. "
                % (obj, selector))
    
    security.declarePrivate('getHistory')
    def getHistory(self, obj=None, history_id=None, preserve=()):
        """
        """
        try:
            return LazyHistory(self, obj, history_id, preserve)
        except StorageUnregisteredError:
            raise ArchivistUnregisteredError(
                "Retrieving a version of an unregistered object is not "
                "possible. Register the object '%s' first. " % obj)
        
    security.declarePrivate('queryHistory')
    def queryHistory(self, obj=None, history_id=None, preserve=(), default=[]):
        """
        """
        try:
            return LazyHistory(self, obj, history_id, preserve)
        except StorageUnregisteredError:
            return default

InitializeClass(ArchivistTool)

def getUserId():
    # XXX This is way too simple. 
    # Needn't this be something unique over time?
    return getSecurityManager().getUser().getUserName()


class ObjectData(Persistent):
    """
    """
    __implements__ = (IObjectData, )
    
    def __init__(self, obj, inside_refs=(), outside_refs=()):
        self.object = obj
        self.inside_refs = inside_refs
        self.outside_refs = outside_refs


class PreparedObject:
    """
    """
    __implements__ = (IPreparedObject, )
    
    def __init__(self, history_id, original, clone, referenced_data, 
                 app_metadata, sys_metadata, is_registered):
        # extend metadata information
        comment = sys_metadata.get('comment', '')
        timestamp = sys_metadata.get('timestamp', int(time.time()))
        originator = sys_metadata.get('originator', None)
        metadata = {
            'sys_metadata': {
                'comment': comment,
                'timestamp': timestamp,
                'originator': originator,
                'principal': getUserId(),
            },
            'app_metadata': app_metadata,
        }
        
        self.history_id = history_id
        self.original = original
        self.clone = clone
        self.referenced_data = referenced_data
        self.metadata = metadata
        self.is_registered = is_registered

    def copyVersionIdFromClone(self):
        self.original.object.version_id = self.clone.object.version_id


class LazyHistory:
    """Lazy history.
    """
    __implements__ = (IHistory, )
    
    def __init__(self, archivist, obj, history_id, preserve=()):
        """Sets up a lazy history. Takes an object which should be the original object
           in the portal, and a history_id for the storage lookup.  If the history id
           is omitted then the history_id will be determined by dereferencing the obj.
           If the obj is omitted, then the obj will be obtained by ddereferencing the
           history_id.
        """
        self._modifier = getToolByName(archivist, 'portal_modifier')
        storage = getToolByName(archivist, 'portal_historiesstorage')
        self._obj, history_id = dereference(obj, history_id, archivist)
        self._preserve = preserve
        self._history = storage.getHistory(history_id)
        
    def __len__(self):
        """See IHistory
        """
        return len(self._history)
        
    def __getitem__(self, selector):
        """See IHistory
        """
        # To retrieve an object from the storage the following
        # steps have to be carried out:
        #
        # 1. get the appropriate data from the storage
        vdata = self._history[selector]
        
        # 2. clone the data and add the version id
        data = deepcopy(vdata.object)
        repo_clone = aq_base(data.object)
        
        # 3. the separately saved attributes need not be cloned
        referenced_data = vdata.referenced_data
        
        # 4. clone the metadata
        metadata = deepcopy(vdata.metadata)
        
        # 5. reattach the separately saved attributes
        self._modifier.reattachReferencedAttributes(repo_clone, 
                                                    referenced_data)
        
        # 6. call the after retrieve modifier
        refs_to_be_deleted, attr_handling_references, preserved_data = \
            self._modifier.afterRetrieveModifier(self._obj, repo_clone, 
                                                 self._preserve)
        
        return VersionData(data, refs_to_be_deleted, 
                           attr_handling_references, preserved_data, 
                           metadata)
        
    def __iter__(self):
        """See IHistory
        """
        return Iterator(self.__getitem__, StorageRetrieveError)


class Iterator:
    """Iterator object using the passed getitem implementation.
    """
    def __init__(self, getItem, stopExceptions):
        self._getItem = getItem
        self._stopExceptions = stopExceptions
        self._pos = -1

    def __iter__(self):
        return self
        
    def next(self):
        try:
            self._pos += 1
            return self._getItem(self._pos)
        except self._stopExceptions:
            raise StopIteration()
