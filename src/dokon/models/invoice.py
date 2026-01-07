from odoo import models, fields

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    owner_id = fields.Many2one(
        'res.partner',
        string='Product egasi',
        ondelete='set null',  # 👈 MUHIM
        index=True,
        store=True
    )

    owner_share = fields.Monetary(
        string='Egaga 25% ulush',
        store=True,
    )
