# -*- coding: utf-8 -*-
# from odoo import http


# class MenofiaBranchesIntegration(http.Controller):
#     @http.route('/menofia_branches_integration/menofia_branches_integration/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/menofia_branches_integration/menofia_branches_integration/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('menofia_branches_integration.listing', {
#             'root': '/menofia_branches_integration/menofia_branches_integration',
#             'objects': http.request.env['menofia_branches_integration.menofia_branches_integration'].search([]),
#         })

#     @http.route('/menofia_branches_integration/menofia_branches_integration/objects/<model("menofia_branches_integration.menofia_branches_integration"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('menofia_branches_integration.object', {
#             'object': obj
#         })
