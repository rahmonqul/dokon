import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        res = super().action_confirm()

        for order in self:
            # Delivered policy bo‘lsa, delivered_qty ni ordered qty ga tenglab qo‘yamiz
            for line in order.order_line:
                if line.product_id.invoice_policy == "delivery":
                    line.qty_delivered = line.product_uom_qty

            # Invoice yaratish
            invoice = order._create_invoices()
            if invoice:
                invoice.action_post()
                return {
                    "type": "ir.actions.act_window",
                    "res_model": "account.move",
                    "view_mode": "form",
                    "res_id": invoice.id,
                    "target": "new",
                }

        return res




class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    owner_share = fields.Monetary(
        string="Egaga 25% ulush",
        compute="_compute_owner_share",
        store=True,
    )

    @api.depends(
        'price_subtotal',
        'product_id',
        'product_id.product_tmpl_id',
        'product_id.product_tmpl_id.owner_id'
    )
    def _compute_owner_share(self):
        for line in self:
            owner = line.product_id.product_tmpl_id.owner_id
            if owner:
                line.owner_share = line.price_subtotal * 0.25
                _logger.info(
                    "Owner share computed | SO line ID: %s | Owner: %s | Share: %s",
                    line.id,
                    owner.name,
                    line.owner_share
                )
            else:
                line.owner_share = 0
                _logger.info(
                    "No owner | SO line ID: %s | owner_share set to 0",
                    line.id
                )

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)

        owner = self.product_id.product_tmpl_id.owner_id
        res.update({
            'owner_id': owner.id if owner else False,
            'owner_share': self.owner_share,
        })
        return res

