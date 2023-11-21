from odoo import fields, models, api


class Branch(models.Model):
    _name = 'consumption.branch'
    _description = 'Description'

    name = fields.Char(required=1,string="Name")
    code=fields.Char(required=1,string="Code")


