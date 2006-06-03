## Script (Python) "file_download_version"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=version_id=1
##title=Image download version
##
request = container.REQUEST
RESPONSE =  request.RESPONSE

obj = context.portal_repository.retrieve(context, version_id).object
RESPONSE.setHeader('Content-Type', obj.content_type)
RESPONSE.setHeader('Content-Length', obj.get_size())
RESPONSE.setHeader('Content-Disposition',
                   'attachment;filename=%s'%(obj.getId()))

return obj.data