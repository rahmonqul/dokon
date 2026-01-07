from odoo import models, fields

class SaleReport(models.Model):
    _inherit = "sale.report"

    owner_id = fields.Many2one(
        'res.partner',
        string="Product Owner",
        readonly=True,
        ondelete="SET NULL",
    )

    owner_share = fields.Float(
        string="Owner Share (25%)",
        readonly=True,
        currency_field="currency_id"
    )

    # SELECT qismi
    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res.update({
            'owner_id': 'pt.owner_id',
            'owner_share': 'SUM(l.price_subtotal * 0.25)',
        })
        return res

    # FROM / JOIN qismi (MUHIM JOY)
    def _from_sale(self):
        from_clause = super()._from_sale()
        from_clause += """
            LEFT JOIN product_product pp ON pp.id = l.product_id
            LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
        """
        return from_clause

    # GROUP BY qismi
    def _group_by_sale(self):
        group_by = super()._group_by_sale()
        group_by += """
            , pt.owner_id
        """
        return group_by
