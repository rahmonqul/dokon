from odoo import models, api, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    owner_id = fields.Many2one(
        'res.partner',
        string='Product egasi'
    )
