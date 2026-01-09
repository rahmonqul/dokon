import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        res = super().action_confirm()

        # Agar action_pay() dan chaqirilsa, invoice yaratmaslik kerak
        # Chunki action_pay() o'zi invoice yaratadi
        if self._context.get('from_action_pay'):
            return res

        for order in self:
            # Delivered policy bo'lsa, delivered_qty ni ordered qty ga tenglab qo'yamiz
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

    def action_pay(self):
        """
        "Oplatit" tugmasi uchun metod:
        Invoice yaratish va to'lov wizard'ini ochadi.
        Agar to'lov qilinmasa, invoice o'chiriladi va buyurtma draftga qaytadi.
        """
        _logger.info("=" * 80)
        _logger.info("OPLATIT TUGMASI BOSILDI | Order IDs: %s", self.ids)
        _logger.info("=" * 80)

        # To'lov wizard'ini ochish uchun invoice line'lar kerak.
        # Shuning uchun vaqtincha invoice yaratamiz, agar to'lov qilinmasa uni o'chiramiz.
        invoices = self.env['account.move']

        for order in self:
            _logger.info("Processing Order | Order ID: %s | State: %s | Name: %s", order.id, order.state, order.name)

            # Agar buyurtma hali tasdiqlanmagan bo'lsa, invoice yaratish uchun tasdiqlash kerak
            if order.state in ('draft', 'sent'):
                _logger.info("Order is in draft/sent state, preparing for invoice creation... | Order ID: %s", order.id)

                # Barcha qatorlar uchun qty_delivered ni o'rnatish (action_confirm() dan oldin)
                _logger.info("Setting qty_delivered for order lines | Order ID: %s | Lines count: %s", order.id, len(order.order_line))
                for line in order.order_line:
                    if line.product_id.invoice_policy == "delivery":
                        line.qty_delivered = line.product_uom_qty
                        _logger.info(
                            "Set qty_delivered for delivery policy | Line ID: %s | Product: %s | Qty: %s",
                            line.id, line.product_id.name, line.qty_delivered
                        )
                    elif line.product_id.type == 'service':
                        line.qty_delivered = line.product_uom_qty
                        _logger.info(
                            "Set qty_delivered for service | Line ID: %s | Product: %s | Qty: %s",
                            line.id, line.product_id.name, line.qty_delivered
                        )
                    else:
                        line.qty_delivered = line.product_uom_qty
                        _logger.info(
                            "Set qty_delivered for other | Line ID: %s | Product: %s | Qty: %s | Policy: %s",
                            line.id, line.product_id.name, line.qty_delivered, line.product_id.invoice_policy
                        )

                # Buyurtmani tasdiqlash (invoice yaratish uchun zarur)
                _logger.info("Confirming order (temporarily for invoice) | Order ID: %s", order.id)
                order.with_context(from_action_pay=True).action_confirm()
                _logger.info("Order confirmed (temporarily) | Order ID: %s | New state: %s", order.id, order.state)

                # Invoice policy'ni "order" ga o'zgartirish (invoice yaratish uchun)
                _logger.info("Forcing invoice policy to 'order' | Order ID: %s", order.id)
                order._force_lines_to_invoice_policy_order()
                _logger.info("Invoice policy forced to 'order' | Order ID: %s", order.id)

                # Debug: qty_to_invoice ni tekshirish
                for line in order.order_line:
                    _logger.info(
                        "After _force_lines_to_invoice_policy_order | Line ID: %s | Product: %s | qty_to_invoice: %s | qty_delivered: %s | product_uom_qty: %s",
                        line.id, line.product_id.name, line.qty_to_invoice, line.qty_delivered, line.product_uom_qty
                    )

            # Invoice yaratish
            try:
                invoice = order._create_invoices()
                if invoice:
                    invoice.action_post()
                    invoices |= invoice
                    _logger.info("Invoice created successfully | Invoice ID: %s | Order ID: %s", invoice.id, order.id)
                else:
                    _logger.warning("Invoice not created | Order ID: %s | State: %s", order.id, order.state)
            except Exception as e:
                _logger.error("Error creating invoice | Order ID: %s | Error: %s", order.id, str(e))
                raise

        # Agar invoice yaratilgan bo'lsa, to'lov wizard'ini ochish
        if invoices:
            _logger.info("Opening payment wizard | Invoice IDs: %s | Order IDs: %s", invoices.ids, self.ids)
            action = invoices.action_register_payment()
            if isinstance(action, dict):
                if 'context' not in action:
                    action['context'] = {}
                action['context']['sale_order_id'] = self.id
                action['context']['dont_redirect_to_payments'] = True
            _logger.info("Payment wizard opened | Action: %s | Context: %s", action, action.get('context'))
            return action

        _logger.warning("No invoices created, cannot open payment wizard | Order IDs: %s", self.ids)
        return True




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

