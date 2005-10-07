#########################################################################
# Copyright (c) 2004, 2005 Alberto Berti, Gregoire Weber.
# Reflab (Vincenzo Di Somma, Francesco Ciriaci, Riccardo Lemmi)
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
"""Top level integration tests (without UI)

$Id: test_IntegrationTests.py,v 1.15 2005/06/24 11:42:01 gregweb Exp $
"""

import os, sys

if __name__ == '__main__':
    execfile(os.path.join(sys.path[0], 'framework.py'))

from Testing import ZopeTestCase

from Interface.Verify import verifyObject
from Acquisition import aq_base

from OFS.ObjectManager import UNIQUE, REPLACEABLE

from Products.CMFEditions.interfaces.IRepository \
     import ICopyModifyMergeRepository

from Products.PloneTestCase import PloneTestCase
from Products.CMFEditions.tests import installProduct

PloneTestCase.setupPloneSite()
ZopeTestCase.installProduct('CMFUid')
ZopeTestCase.installProduct('CMFEditions')

ZopeTestCase.installProduct('Archetypes')
ZopeTestCase.installProduct('PortalTransforms')
ZopeTestCase.installProduct('MimetypesRegistry')
ZopeTestCase.installProduct('ATContentTypes')

ZopeTestCase.installProduct('Zelenium')
ZopeTestCase.installProduct('PloneSelenium')

portal_owner = PloneTestCase.portal_owner
portal_name = PloneTestCase.portal_name
default_user = PloneTestCase.default_user

class TestIntegration(PloneTestCase.PloneTestCase):

    def afterSetUp(self):
        # we need to have the Manager role to be able to add things
        # to the portal root
        self.setRoles(['Manager',])
        installProduct(self.portal, 'PloneSelenium', optional=True)
        installProduct(self.portal, 'CMFEditions')

        # add an additional user
        self.portal.acl_users.userFolderAddUser('reviewer', 'reviewer',
                                                ['Manager'], '')
        # add a document
        self.portal.invokeFactory('Document', 'doc')

        # add a folder with two documents in it
        self.portal.invokeFactory('Folder', 'fol')
        self.portal.fol.invokeFactory('Document', 'doc1')
        self.portal.fol.invokeFactory('Document', 'doc2')

    def test01_assertApplyVersionControlSavesOnlyOnce(self):
        portal_repo = self.portal.portal_repository
        doc = self.portal.doc

        doc.setTitle('doc title v1')
        portal_repo.applyVersionControl(doc, comment='First version')

        # there should be only one history entry and not two or more
        self.assertEqual(len(portal_repo.getHistory(doc)), 1)

    def test02_storeAndRevertToPreviousVersion(self):
        portal_repo = self.portal.portal_repository
        doc = self.portal.doc

        doc.setTitle("v1")
        portal_repo.applyVersionControl(doc)
        doc.setTitle("v2")
        portal_repo.save(doc)
        doc.setTitle("v3")

        self.assertEqual(doc.Title(), "v3")

        portal_repo.revert(doc)
        # just a remark: we don't do "doc = self.portal.doc" to check for
        # inplace replacement
        self.assertEqual(doc.Title(), "v2")

    def test03_revertToSpecificVersion(self):
        portal_repo = self.portal.portal_repository
        doc = self.portal.doc

        # store the work edition two times
        doc.setTitle("v1")
        portal_repo.applyVersionControl(doc)
        doc.setTitle("v2")
        portal_repo.save(doc)
        doc.setTitle("v3")
        portal_repo.save(doc)
        doc.setTitle("v4")
        self.assertEqual(doc.Title(), "v4")

        # revert to the the last but one version
        portal_repo.revert(doc, 1)
        self.assertEqual(doc.Title(), "v2")

    def test04_storeAndRevertToPreviousVersionAndStoreAgain(self):
        portal_repo = self.portal.portal_repository
        doc = self.portal.doc

        doc.setTitle("v1")
        portal_repo.applyVersionControl(doc)
        doc.setTitle("v2")
        portal_repo.save(doc)
        doc.setTitle("v3")
        self.assertEqual(doc.Title(), "v3")

        portal_repo.revert(doc, 0)
        doc = self.portal.doc
        self.assertEqual(doc.Title(), "v1")
        doc.setTitle("v4")
        portal_repo.save(doc)
        self.assertEqual(doc.Title(), "v4")

    def test05_getHistory(self):
        portal_repo = self.portal.portal_repository
        doc = self.portal.doc

        # store and publish certain times
        portal_repo.applyVersionControl(doc)

        portal_repo.save(doc, metadata="v2\nsecond line")
        portal_repo.save(doc)

        history = portal_repo.getHistory(doc)

        # test the number of history entries
        self.assertEqual(len(history), 3)

        """XXX we like to test that but implementation isn't there yet
        # test some of the log entries
        h1 = history[1]
        self.assertEqual(h1.version_id, '2')
        self.assertEqual(h1.action, h1.ACTION_CHECKIN)
        self.assertEqual(h1.message, 'v2\nsecond line')
        self.failUnless(h1.user_id)
        self.assertEqual(h1.path, '/'.join(doc.getPhysicalPath()))
        self.failUnless(h1.timestamp)
        """

    def test06_retrieveSpecificVersion(self):
        portal_repo = self.portal.portal_repository
        doc = self.portal.doc

        # store the work edition two times
        doc.setTitle("v1")
        portal_repo.applyVersionControl(doc)
        doc.setTitle("v2")
        portal_repo.save(doc)
        doc.setTitle("v3")
        portal_repo.save(doc)
        doc.setTitle("v4")
        self.assertEqual(doc.Title(), "v4")

        retrieved_doc = portal_repo.retrieve(doc, 1)

        self.assertEqual(retrieved_doc.object.Title(), "v2")
        self.assertEqual(doc.Title(), "v4")
        self.assertEqual(self.portal.doc.Title(), "v4")

    def test07_cloneObjectUnderVersionControlRemovesOriginalsHistory(self):
        portal_repo = self.portal.portal_repository
        portal_historyidhandler = self.portal.portal_historyidhandler
        UniqueIdError = portal_historyidhandler.UniqueIdError
        doc = self.portal.doc

        # put the object under version control
        portal_repo.applyVersionControl(doc)

        # copy
        self.portal.manage_pasteObjects(self.portal.manage_copyObjects(ids=['doc']))
        copy = self.portal.copy_of_doc

        # the copy shall not have a history yet: that's correct
        self.failIf(portal_repo.getHistory(copy))

        # just to be sure the history is definitivels different
        self.failIfEqual(
            portal_historyidhandler.queryUid(doc),
            portal_historyidhandler.queryUid(copy)) # may be None

    def test08_loopOverHistory(self):
        portal_repo = self.portal.portal_repository
        portal_historyidhandler = self.portal.portal_historyidhandler
        UniqueIdError = portal_historyidhandler.UniqueIdError
        doc = self.portal.doc

        # put the object under version control
        portal_repo.applyVersionControl(doc)

        counter = 0
        for v in portal_repo.getHistory(doc):
            counter += 1

        # check if history iterator returned just one element
        self.assertEquals(counter, 1)

    def test09_retrieveAndRevertRetainWorkingCopiesWorkflowInfo(self):
        portal_repo = self.portal.portal_repository
        doc = self.portal.doc

        doc.review_state = "fake rev state v1"
        doc.workflow_history = {0: "fake wf history v1"}

        portal_repo.applyVersionControl(doc)

        doc.review_state = "fake rev state v2"
        doc.workflow_history = {0: "fake wf history v2"}
        portal_repo.save(doc)

        # just check the original is unchanged
        self.assertEqual(doc.review_state, "fake rev state v2")
        self.assertEqual(doc.workflow_history[0], "fake wf history v2")

        # ----- retrieve
        # check if retrieved object carries the working copies workflow info
        retrieved_data = portal_repo.retrieve(doc, 0, preserve=['review_state',
                                                      'workflow_history'])
        self.assertEqual(retrieved_data.object.review_state,
                         "fake rev state v2")
        self.assertEqual(retrieved_data.object.workflow_history[0],
                         "fake wf history v2")

        # check that the working copies workflow info is unchanged
        self.assertEqual(doc.review_state, "fake rev state v2")
        self.assertEqual(doc.workflow_history[0], "fake wf history v2")

        # check if the preserved data is returned correctly
        preserved_rvs = retrieved_data.preserved_data['review_state']
        self.assertEqual(preserved_rvs, "fake rev state v1")
        preserved_wfh = retrieved_data.preserved_data['workflow_history'][0]
        self.assertEqual(preserved_wfh, "fake wf history v1")

        # ----- revert
        # check that the working copies workflow info is unchanged after
        portal_repo.revert(doc, 0)
        self.assertEqual(doc.review_state, "fake rev state v2")
        self.assertEqual(doc.workflow_history[0], "fake wf history v2")

    def test10_versionAStandardFolder(self):
        portal_repo = self.portal.portal_repository
        fol = self.portal.fol
        doc1 = fol.doc1
        doc2 = fol.doc2

        # save change no 1
        fol.setTitle('v1 of fol')
        doc1.setTitle("v1 of doc1")
        doc2.setTitle("v1 of doc2")

        portal_repo.applyVersionControl(fol, comment='first save')

        # save change no 2
        fol.setTitle('v2 of fol')
        doc1.setTitle("v2 of doc1")
        doc2.setTitle("v2 of doc2")
        portal_repo.save(fol, comment='second save')

        # change no 3 (without saving)
        fol.setTitle('v3 of fol')
        doc1.setTitle("v3 of doc1")
        doc2.setTitle("v3 of doc2")

        # revert to change no 2
        portal_repo.revert(fol)

        # check if revertion worked correctly
        fol = self.portal.fol
        doc1 = fol.doc1
        doc2 = fol.doc2
        self.assertEqual(fol.Title(), "v2 of fol")
        self.assertEqual(doc1.Title(), "v3 of doc1")
        self.assertEqual(doc2.Title(), "v3 of doc2")

    def test11_versionAFolderishObjectThatTreatsChildrensAsInsideRefs(self):
        portal_repo = self.portal.portal_repository
        fol = self.portal.fol
        doc1 = fol.doc1
        doc2 = fol.doc2

        # just configure the standard folder to treat the childrens as
        # inside refrences. For this we reconfigure the standard modifiers.
        portal_modifier = self.portal.portal_modifier
        portal_modifier.edit("OMOutsideChildrensModifier", enabled=False, 
                             condition="python: False")
        portal_modifier.edit("OMInsideChildrensModifier", enabled=True, 
                             condition="python: portal_type=='Folder'")

        # save change no 1
        fol.setTitle('v1 of fol')
        doc1.setTitle("v1 of doc1")
        doc2.setTitle("v1 of doc2")
        portal_repo.applyVersionControl(fol, comment='first save')

        # save change no 2
        fol.setTitle('v2 of fol')
        doc1.setTitle("v2 of doc1")
        fol.manage_delObjects(ids=['doc2'])
        portal_repo.save(fol, comment='second save after we deleted doc2')

        # save change no 3
        fol.setTitle('v3 of fol')
        doc1.setTitle("v3 of doc1")
        fol.invokeFactory('Document', 'doc3')
        doc1.setTitle("v1 of doc3")
        portal_repo.save(fol, comment='second save with new doc3')

        # revert to change no 1 (version idexes start with index 0)
        portal_repo.revert(fol, selector=0)

        # check if revertion worked correctly
        fol = self.portal.fol
        doc1 = fol.doc1
        self.failUnless('doc2' in fol.objectIds())
        self.failIf('doc3' in fol.objectIds())
        doc2 = fol.doc2
        self.assertEqual(fol.Title(), "v1 of fol")
        self.assertEqual(doc1.Title(), "v1 of doc1")
        self.assertEqual(doc2.Title(), "v1 of doc2")

    def test12_retrieveAndRevertRetainWorkingCopiesPermissions(self):
        portal_repo = self.portal.portal_repository
        doc = self.portal.doc
        perm = 'Access contents information'
        roles = list(doc.valid_roles())
        member_role = 'p0r%s' % roles.index('Member')
        manager_role = 'p0r%s' % roles.index('Manager')

        doc.manage_permission(perm, ('Manager',), 0)

        portal_repo.applyVersionControl(doc)

        doc.manage_permission(perm, ('Manager', 'Member'), 1)
        portal_repo.save(doc)

        # just check the original is unchanged
        settings = doc.permission_settings(perm)[0]
        self.failUnless(settings['acquire'])
        role_enabled = [r for r in settings['roles']
                                        if r['name'] == member_role][0]
        self.failUnless(role_enabled['checked'])

        # ----- retrieve
        # check if retrieved object carries the working copy's permissions
        retrieved_data = portal_repo.retrieve(doc, 0,
                        preserve=['_Access_contents_information_Permission'])
        settings = retrieved_data.object.permission_settings(perm)[0]
        self.failUnless(settings['acquire'])
        role_enabled = [r for r in settings['roles']
                                        if r['name'] == member_role][0]
        self.failUnless(role_enabled['checked'])

        # check that the working copy's permissions are unchanged
        settings = doc.permission_settings(perm)[0]
        self.failUnless(settings['acquire'])
        role_enabled = [r for r in settings['roles']
                                        if r['name'] == member_role][0]
        self.failUnless(role_enabled['checked'])

        # check if the preserved data is returned correctly
        preserved = retrieved_data.preserved_data['_Access_contents_information_Permission']
        self.assertEqual(preserved, ('Manager',))

        # ----- revert
        # check that the working copies permissions are unchanged after revert
        portal_repo.revert(doc, 0)
        settings = doc.permission_settings(perm)[0]
        self.failUnless(settings['acquire'])
        role_enabled = [r for r in settings['roles']
                                        if r['name'] == member_role][0]
        self.failUnless(role_enabled['checked'])

    def test13_revertUpdatesCatalog(self):
        portal_repo = self.portal.portal_repository
        cat = self.portal.portal_catalog
        doc = self.portal.doc

        doc.edit(text='Plain text')
        portal_repo.applyVersionControl(doc)
        doc.edit(text='blahblah')
        portal_repo.save(doc)
        # Test that catalog has current value
        results = cat(SearchableText='Plain Text')
        self.assertEqual(len(results), 0)
        results = cat(SearchableText='blahblah')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].getObject(), doc)

        retrieved_data = portal_repo.retrieve(doc, 0,
                        preserve=['_Access_contents_information_Permission'])
        retrieved_doc = retrieved_data.object
        self.failUnless('Plain text' in retrieved_doc.getText())
        # Test that basic retrieval did not alter the catalog
        results = cat(SearchableText='Plain Text')
        self.assertEqual(len(results), 0)
        results = cat(SearchableText='blahblah')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].getObject(), doc)

        portal_repo.revert(doc, 0)
        # Test that the catalog is updated on revert
        results = cat(SearchableText='blahblah')
        self.assertEqual(len(results), 0)
        results = cat(SearchableText='Plain Text')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].getObject().getRawText(), 'Plain text')

    def test14_retrieveFolderWithAddedOrDeletedObjects(self):
        portal_repo = self.portal.portal_repository
        fol = self.portal.fol
        doc1 = fol.doc1
        doc2 = fol.doc2

        # save change no 1
        fol.setTitle('v1 of fol')
        doc1.setTitle("v1 of doc1")
        doc2.setTitle("v1 of doc2")

        portal_repo.applyVersionControl(fol, comment='first save')

        retrieved_data = portal_repo.retrieve(fol, 0)
        ret_folder = retrieved_data.object
        self.assertEqual(ret_folder.objectIds(), fol.objectIds())
        self.assertEqual(ret_folder.objectValues(), fol.objectValues())

        # remove an item
        fol.manage_delObjects('doc2')

        # retrieve should update sub-objects
        retrieved_data = portal_repo.retrieve(fol, 0)
        ret_folder = retrieved_data.object
        self.assertEqual(ret_folder.objectIds(), fol.objectIds())
        self.assertEqual(ret_folder.objectValues(), fol.objectValues())

        # add it back
        fol.invokeFactory('Document', 'doc2')
        doc2 = fol.doc2
        doc2.setTitle('v2 of doc2')

        # retrieve should update sub-objects
        retrieved_data = portal_repo.retrieve(fol, 0)
        ret_folder = retrieved_data.object
        self.assertEqual(ret_folder.objectIds(), fol.objectIds())
        self.assertEqual(ret_folder.objectValues(), fol.objectValues())
        self.assertEqual(ret_folder.doc2.Title(), 'v2 of doc2')

        # add new item
        fol.invokeFactory('Document', 'doc3')
        doc3 = fol.doc3
        doc3.setTitle('v1 of doc3')

        # retrieve should copy new sub-objects
        retrieved_data = portal_repo.retrieve(fol, 0)
        ret_folder = retrieved_data.object
        self.assertEqual(ret_folder.objectIds(), fol.objectIds())
        self.assertEqual(ret_folder.objectValues(), fol.objectValues())
        self.assertEqual(ret_folder.doc3.Title(), 'v1 of doc3')

        orig_ids = fol.objectIds()
        orig_values = fol.objectValues()
        # revert to original state, ensure that subobject changes are
        # preserved
        portal_repo.revert(fol, 0)

        # check if reversion worked correctly
        self.assertEqual(fol.objectIds(), orig_ids)
        self.assertEqual(fol.objectValues(), orig_values)

        # XXX we should be preserving order as well

    def test15_retrieveInsideRefsFolderWithAddedOrDeletedObjects(self):
        portal_repo = self.portal.portal_repository
        fol = self.portal.fol
        doc1 = fol.doc1
        doc2 = fol.doc2

        # just configure the standard folder to treat the childrens as
        # inside refrences. For this we reconfigure the standard modifiers.
        portal_modifier = self.portal.portal_modifier
        portal_modifier.edit("OMOutsideChildrensModifier", enabled=False, 
                             condition="python: False")
        portal_modifier.edit("OMInsideChildrensModifier", enabled=True, 
                             condition="python: portal_type=='Folder'")

        # save change no 1
        fol.setTitle('v1 of fol')
        doc1.setTitle("v1 of doc1")
        doc2.setTitle("v1 of doc2")

        orig_ids = fol.objectIds()
        orig_values = fol.objectValues()

        portal_repo.applyVersionControl(fol, comment='first save')

        retrieved_data = portal_repo.retrieve(fol, 0)
        ret_folder = retrieved_data.object
        self.assertEqual(ret_folder.objectIds(), orig_ids)
        ret_values = ret_folder.objectValues()
        # The values are not identical to the stored values because they are
        # retrieved from the repository.
        for i in range(len(ret_values)):
            self.assertEqual(ret_values[i].getId(), orig_values[i].getId())
            self.assertEqual(ret_values[i].Title(), orig_values[i].Title())

        # remove an item
        fol.manage_delObjects('doc2')

        # retrieve should retrieve missing sub-objects
        retrieved_data = portal_repo.retrieve(fol, 0)
        ret_folder = retrieved_data.object
        self.assertEqual(ret_folder.objectIds(), orig_ids)
        ret_values = ret_folder.objectValues()
        for i in range(len(ret_values)):
            self.assertEqual(ret_values[i].getId(), orig_values[i].getId())
            self.assertEqual(ret_values[i].Title(), orig_values[i].Title())

        # add new item
        fol.invokeFactory('Document', 'doc3')
        doc3 = fol.doc3
        doc3.setTitle('v1 of doc3')

        # retrieve should not add new sub-objects
        retrieved_data = portal_repo.retrieve(fol, 0)
        ret_folder = retrieved_data.object
        self.assertEqual(ret_folder.objectIds(), orig_ids)
        ret_values = ret_folder.objectValues()
        for i in range(len(ret_values)):
            self.assertEqual(ret_values[i].getId(), orig_values[i].getId())
            self.assertEqual(ret_values[i].Title(), orig_values[i].Title())

        # revert to original state, ensure that subobject changes are
        # reverted
        portal_repo.revert(fol, 0)
        fol = self.portal.fol

        # check if reversion worked correctly
        self.assertEqual(fol.objectIds(), orig_ids)
        rev_values = fol.objectValues()
        for i in range(len(ret_values)):
            self.assertEqual(ret_values[i].getId(), orig_values[i].getId())
            self.assertEqual(ret_values[i].Title(), orig_values[i].Title())

if __name__ == '__main__':
    framework()
else:
    from unittest import TestSuite, makeSuite
    def test_suite():
        suite = TestSuite()
        suite.addTest(makeSuite(TestIntegration))
        return suite
