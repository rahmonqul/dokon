# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def button_confirm(self):
        res = super().button_confirm()

        # Agar action_pay() dan chaqirilsa, bill yaratmaslik kerak
        # Chunki action_pay() o'zi bill yaratadi
        if self._context.get('from_action_pay'):
            _logger.info("button_confirm called from action_pay, skipping bill creation | Order ID: %s", self.id)
            return res

        return res

    def action_create_invoice(self):
        """
        Override: Agar from_action_pay context bo'lsa, to'g'ridan-to'g'ri bill yaratish (wizard ochmaslik)
        """
        if self._context.get('from_action_pay'):
            # To'g'ridan-to'g'ri bill yaratish (wizard ochmaslik)
            _logger.info("Creating vendor bill directly (from action_pay) | Order ID: %s", self.id)
            from odoo.tools.float_utils import float_is_zero
            from itertools import groupby
            
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            invoice_vals_list = []
            sequence = 10
            
            for order in self:
                # invoice_status ni tekshirish - agar 'to invoice' bo'lmasa, o'tkazib yuborish
                # Lekin biz barcha line'larni invoice qilishimiz kerak
                order = order.with_company(order.company_id)
                pending_section = None
                invoice_vals = order._prepare_invoice()
                invoice_vals['date'] = fields.Date.today()
                invoice_vals['invoice_date'] = fields.Date.today()
                
                # Barcha line'larni invoice qilish (qty_to_invoice ni tekshirish)
                for line in order.order_line:
                    if line.display_type == 'line_section':
                        pending_section = line
                        continue
                    # qty_to_invoice ni tekshirish - agar 0 bo'lsa, product_qty ni ishlatish
                    qty_to_invoice = line.qty_to_invoice if line.qty_to_invoice > 0 else line.product_qty
                    if not float_is_zero(qty_to_invoice, precision_digits=precision):
                        if pending_section:
                            line_vals = pending_section._prepare_account_move_line()
                            line_vals.update({'sequence': sequence})
                            invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
                            sequence += 1
                            pending_section = None
                        line_vals = line._prepare_account_move_line()
                        # quantity ni to'g'ri o'rnatish
                        line_vals['quantity'] = qty_to_invoice
                        line_vals.update({'sequence': sequence})
                        invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
                        sequence += 1
                
                # Agar invoice_line_ids bo'lsa, qo'shish
                if invoice_vals.get('invoice_line_ids'):
                    invoice_vals_list.append(invoice_vals)

            if not invoice_vals_list:
                from odoo.exceptions import UserError
                raise UserError(_('There is no invoiceable line.'))

            # Group by (company_id, partner_id, currency_id) for batch creation
            new_invoice_vals_list = []
            for grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: (x.get('company_id'), x.get('partner_id'), x.get('currency_id'))):
                origins = set()
                payment_refs = set()
                refs = set()
                ref_invoice_vals = None
                for invoice_vals in invoices:
                    if not ref_invoice_vals:
                        ref_invoice_vals = invoice_vals
                    else:
                        ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                    origins.add(invoice_vals['invoice_origin'])
                    payment_refs.add(invoice_vals['payment_reference'])
                    refs.add(invoice_vals['ref'])
                ref_invoice_vals['invoice_origin'] = ', '.join(origins)
                ref_invoice_vals['payment_reference'] = ', '.join(payment_refs)
                ref_invoice_vals['ref'] = ', '.join(refs)
                new_invoice_vals_list.append(ref_invoice_vals)

            # Create invoices
            moves = self.env['account.move']
            for invoice_vals in new_invoice_vals_list:
                moves |= self.env['account.move'].create(invoice_vals)
            
            _logger.info("Vendor bills created | Bill IDs: %s | Order IDs: %s", moves.ids, self.ids)
            return moves
        
        return super().action_create_invoice()

    def action_pay(self):
        """
        "Pay" tugmasi uchun metod:
        Purchase order'ni confirm qiladi, vendor bill yaratadi va to'lov wizard'ini ochadi.
        """
        _logger.info("=" * 80)
        _logger.info("PAY TUGMASI BOSILDI (PURCHASE) | Order IDs: %s", self.ids)
        _logger.info("=" * 80)

        for order in self:
            _logger.info("Processing Purchase Order | Order ID: %s | State: %s | Name: %s", order.id, order.state, order.name)

            # Agar buyurtma hali tasdiqlanmagan bo'lsa, tasdiqlash
            if order.state in ('draft', 'sent', 'to approve'):
                _logger.info("Order is in draft/sent/to approve state, confirming... | Order ID: %s", order.id)
                order.with_context(from_action_pay=True).button_confirm()
                _logger.info("Order confirmed | Order ID: %s | New state: %s", order.id, order.state)

            # Vendor bill yaratish
            if order.state == 'purchase':
                _logger.info("Creating vendor bill | Order ID: %s", order.id)
                # action_create_invoice() metodini ishlatish (to'g'ri invoice line'lar yaratadi)
                bills = order.with_context(from_action_pay=True).action_create_invoice()
                if not bills:
                    _logger.warning("No bills created | Order ID: %s", order.id)
                    continue
                
                # Agar bir nechta bill yaratilgan bo'lsa, birinchisini olish
                bill = bills[0] if isinstance(bills, models.Model) else bills
                _logger.info("Vendor bill created | Bill ID: %s | Order ID: %s | Lines count: %s", bill.id, order.id, len(bill.invoice_line_ids))

                # Bill'ni post qilish
                if bill.state == 'draft':
                    bill.action_post()
                    _logger.info("Bill posted | Bill ID: %s", bill.id)

                # To'lov wizard'ini ochish
                _logger.info("Opening payment wizard | Bill ID: %s | Order ID: %s", bill.id, order.id)
                action = bill.action_register_payment()
                if isinstance(action, dict):
                    if 'context' not in action:
                        action['context'] = {}
                    action['context']['purchase_order_id'] = order.id
                    action['context']['dont_redirect_to_payments'] = True
                _logger.info("Payment wizard opened | Action: %s | Context: %s", action, action.get('context'))
                return action

        _logger.warning("No bills created, cannot open payment wizard | Order IDs: %s", self.ids)
        return True

