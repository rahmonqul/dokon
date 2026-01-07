# -*- coding: utf-8 -*-
# from odoo import http


# class Dokon(http.Controller):
#     @http.route('/dokon/dokon', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/dokon/dokon/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('dokon.listing', {
#             'root': '/dokon/dokon',
#             'objects': http.request.env['dokon.dokon'].search([]),
#         })

#     @http.route('/dokon/dokon/objects/<model("dokon.dokon"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('dokon.object', {
#             'object': obj
#         })

