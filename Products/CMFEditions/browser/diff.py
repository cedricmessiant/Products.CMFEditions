from zope.i18n import translate

from Acquisition import aq_inner
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName
from Products.CMFEditions import CMFEditionsMessageFactory as _


class DiffView(BrowserView):
    template = ViewPageTemplateFile("diff.pt")

    def __init__(self, *args):
        super(DiffView, self).__init__(*args)
        self.repo_tool=getToolByName(self.context, "portal_repository")


    def getVersion(self, version):
        context=aq_inner(self.context)
        if version=="current":
            return context
        else:
            return self.repo_tool.retrieve(context, int(version)).object


    def versionTitle(self, version):
        return translate(
            _(u"version ${version}",
              mapping=dict(version=version)),
            context=self.request
        )


    def __call__(self):
        version1=self.request.get("one", "current")
        version2=self.request.get("two", "current")

        self.history=self.repo_tool.getHistory(self.context, countPurged=False)
        dt=getToolByName(self.context, "portal_diff")
        changeset=dt.createChangeSet(
                self.getVersion(version2),
                self.getVersion(version1),
                id1=self.versionTitle(version2),
                id2=self.versionTitle(version1))
        self.changes=[change for change in changeset.getDiffs()
                      if not change.same]

        return self.template()

