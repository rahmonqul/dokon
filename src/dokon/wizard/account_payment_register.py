# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        help='Sale Order ID for payment wizard'
    )
    
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        help='Purchase Order ID for payment wizard'
    )

    @api.model
    def default_get(self, fields_list):
        """
        Context'dan sale_order_id va purchase_order_id ni olish va wizard maydoniga o'rnatish
        """
        res = super().default_get(fields_list)
        sale_order_id = self._context.get('sale_order_id')
        purchase_order_id = self._context.get('purchase_order_id')
        
        if sale_order_id and 'sale_order_id' in fields_list:
            res['sale_order_id'] = sale_order_id
            _logger.info("Setting sale_order_id from context | Sale Order ID: %s", sale_order_id)
        
        if purchase_order_id and 'purchase_order_id' in fields_list:
            res['purchase_order_id'] = purchase_order_id
            _logger.info("Setting purchase_order_id from context | Purchase Order ID: %s", purchase_order_id)
        
        return res

    def _revert_sale_order_if_needed(self):
        """
        Agar to'lov qilinmagan bo'lsa, buyurtmani qaytarib draft holatiga o'tkazish
        Bu metod unlink() va action_cancel() tomonidan ishlatiladi
        """
        # Context'dan yoki wizard maydonidan sale_order_id ni olish
        sale_order_id = self._context.get('sale_order_id')
        
        # Agar context'da yo'q bo'lsa, wizard maydonidan olish
        if not sale_order_id and hasattr(self, 'sale_order_id') and self.sale_order_id:
            sale_order_id = self.sale_order_id.id
        
        # Agar hali ham yo'q bo'lsa, context'dan active_ids orqali invoice'larni topish va sale_order_id ni olish
        if not sale_order_id:
            try:
                # Context'dan active_ids ni olish (invoice line IDs)
                active_ids = self._context.get('active_ids', [])
                active_model = self._context.get('active_model', '')
                
                _logger.info("Trying to get sale_order_id from active_ids | active_model: %s | active_ids: %s", active_model, active_ids)
                
                if active_ids and active_model == 'account.move.line':
                    # Invoice line'lardan invoice'ni topish
                    invoice_lines = self.env['account.move.line'].browse(active_ids)
                    if invoice_lines:
                        invoice = invoice_lines[0].move_id
                        if invoice and invoice.move_type == 'out_invoice':
                            # Invoice'dan sale_order_id ni topish
                            sale_orders = self.env['sale.order'].search([('invoice_ids', 'in', [invoice.id])])
                            if sale_orders:
                                sale_order_id = sale_orders[0].id
                                _logger.info("Sale Order ID from active_ids (invoice lines): %s", sale_order_id)
            except Exception as e:
                _logger.warning("Error getting sale_order_id from active_ids | Error: %s", str(e))
        
        _logger.info("Sale Order ID from context: %s | From field: %s | Final: %s", 
                    self._context.get('sale_order_id'), 
                    self.sale_order_id.id if hasattr(self, 'sale_order_id') and self.sale_order_id else None,
                    sale_order_id)
        
        if sale_order_id:
            sale_order = self.env['sale.order'].browse(sale_order_id)
            _logger.info("Sale Order found | Order ID: %s | State: %s | Name: %s", sale_order.id, sale_order.state, sale_order.name)
            
            # Agar buyurtma tasdiqlangan bo'lsa va invoice yaratilgan bo'lsa
            # Lekin to'lov qilinmagan bo'lsa (chunki to'lov qilinganda action_create_payments() chaqiriladi)
            if sale_order.state == 'sale' and sale_order.invoice_ids:
                _logger.info("Order is in 'sale' state with invoices, returning to draft | Order ID: %s | Invoice IDs: %s", sale_order.id, sale_order.invoice_ids.ids)
                
                # Delivery'larni bekor qilish
                if sale_order.picking_ids:
                    _logger.info("Cancelling pickings | Picking IDs: %s", sale_order.picking_ids.ids)
                    for picking in sale_order.picking_ids:
                        if picking.state not in ('done', 'cancel'):
                            picking.action_cancel()
                            _logger.info("Picking cancelled | Picking ID: %s", picking.id)
                
                # Invoice'larni o'chirish
                for invoice in sale_order.invoice_ids:
                    _logger.info("Deleting invoice | Invoice ID: %s | State: %s", invoice.id, invoice.state)
                    if invoice.state == 'draft':
                        invoice.unlink()
                        _logger.info("Invoice deleted (draft) | Invoice ID: %s", invoice.id)
                    elif invoice.state == 'posted':
                        # Agar invoice tasdiqlangan bo'lsa, uni bekor qilish
                        invoice.button_draft()
                        invoice.unlink()
                        _logger.info("Invoice deleted (posted) | Invoice ID: %s", invoice.id)
                
                # Buyurtmani qaytarib draft holatiga o'tkazish
                # action_draft() faqat 'cancel' yoki 'sent' holatidagi buyurtmalarni draft ga o'tkazadi
                # Bizning holatda buyurtma 'sale' holatida, shuning uchun to'g'ridan-to'g'ri write() qilamiz
                _logger.info("Returning order to draft state | Order ID: %s | Current state: %s", sale_order.id, sale_order.state)
                sale_order.write({'state': 'draft'})
                _logger.info("Order returned to draft state | Order ID: %s | New state: %s", sale_order.id, sale_order.state)
                _logger.info("Oplatit tugmasi endi yana ko'rinadi!")

    def _revert_purchase_order_if_needed(self):
        """
        Agar to'lov qilinmagan bo'lsa, purchase order'ni qaytarib draft holatiga o'tkazish
        Bu metod unlink() va action_cancel() tomonidan ishlatiladi
        """
        # Context'dan yoki wizard maydonidan purchase_order_id ni olish
        purchase_order_id = self._context.get('purchase_order_id')
        
        # Agar context'da yo'q bo'lsa, wizard maydonidan olish
        if not purchase_order_id and hasattr(self, 'purchase_order_id') and self.purchase_order_id:
            purchase_order_id = self.purchase_order_id.id
        
        # Agar hali ham yo'q bo'lsa, context'dan active_ids orqali bill'larni topish va purchase_order_id ni olish
        if not purchase_order_id:
            try:
                # Context'dan active_ids ni olish (bill line IDs)
                active_ids = self._context.get('active_ids', [])
                active_model = self._context.get('active_model', '')
                
                _logger.info("Trying to get purchase_order_id from active_ids | active_model: %s | active_ids: %s", active_model, active_ids)
                
                if active_ids and active_model == 'account.move.line':
                    # Bill line'lardan bill'ni topish
                    bill_lines = self.env['account.move.line'].browse(active_ids)
                    if bill_lines:
                        bill = bill_lines[0].move_id
                        if bill and bill.move_type == 'in_invoice':
                            # Bill'dan purchase_order_id ni topish
                            # Purchase order'da vendor bill'lar invoice_ids orqali bog'langan
                            purchase_orders = self.env['purchase.order'].search([('invoice_ids', 'in', [bill.id])])
                            if purchase_orders:
                                purchase_order_id = purchase_orders[0].id
                                _logger.info("Purchase Order ID from active_ids (bill lines): %s", purchase_order_id)
            except Exception as e:
                _logger.warning("Error getting purchase_order_id from active_ids | Error: %s", str(e))
        
        _logger.info("Purchase Order ID from context: %s | From field: %s | Final: %s", 
                    self._context.get('purchase_order_id'), 
                    self.purchase_order_id.id if hasattr(self, 'purchase_order_id') and self.purchase_order_id else None,
                    purchase_order_id)
        
        if purchase_order_id:
            purchase_order = self.env['purchase.order'].browse(purchase_order_id)
            _logger.info("Purchase Order found | Order ID: %s | State: %s | Name: %s", purchase_order.id, purchase_order.state, purchase_order.name)
            
            # Agar buyurtma tasdiqlangan bo'lsa va bill yaratilgan bo'lsa
            # Lekin to'lov qilinmagan bo'lsa (chunki to'lov qilinganda action_create_payments() chaqiriladi)
            # Purchase order'da vendor bill'lar invoice_ids orqali bog'langan
            bills = purchase_order.invoice_ids.filtered(lambda inv: inv.move_type == 'in_invoice')
            if purchase_order.state == 'purchase' and bills:
                _logger.info("Order is in 'purchase' state with bills, returning to draft | Order ID: %s | Bill IDs: %s", purchase_order.id, bills.ids)
                
                # Bill'larni o'chirish
                for bill in bills:
                    _logger.info("Deleting bill | Bill ID: %s | State: %s", bill.id, bill.state)
                    if bill.state == 'draft':
                        bill.unlink()
                        _logger.info("Bill deleted (draft) | Bill ID: %s", bill.id)
                    elif bill.state == 'posted':
                        # Agar bill tasdiqlangan bo'lsa, uni bekor qilish
                        bill.button_draft()
                        bill.unlink()
                        _logger.info("Bill deleted (posted) | Bill ID: %s", bill.id)
                
                # Buyurtmani qaytarib draft holatiga o'tkazish
                _logger.info("Returning purchase order to draft state | Order ID: %s | Current state: %s", purchase_order.id, purchase_order.state)
                purchase_order.write({'state': 'draft'})
                _logger.info("Purchase order returned to draft state | Order ID: %s | New state: %s", purchase_order.id, purchase_order.state)
                _logger.info("Pay tugmasi endi yana ko'rinadi!")

    def unlink(self):
        """
        Wizard oynasini yopishda (X tugmasi bosilganda) buyurtmani qaytarib draft holatiga o'tkazish
        """
        _logger.info("=" * 80)
        _logger.info("WIZARD OYNASI YOPILMOQDA (X tugmasi)")
        _logger.info("=" * 80)
        
        # Buyurtmani qaytarib draft holatiga o'tkazish
        # _revert_sale_order_if_needed() va _revert_purchase_order_if_needed() metodlarini chaqirish
        self._revert_sale_order_if_needed()
        self._revert_purchase_order_if_needed()
        
        return super().unlink()
    
    def action_cancel(self):
        """
        Cancel tugmasi bosilganda buyurtmani qaytarib draft holatiga o'tkazish
        """
        _logger.info("=" * 80)
        _logger.info("CANCEL TUGMASI BOSILDI")
        _logger.info("=" * 80)
        
        # Buyurtmani qaytarib draft holatiga o'tkazish
        self._revert_sale_order_if_needed()
        self._revert_purchase_order_if_needed()
        
        # Wizard oynasini yopish
        return {'type': 'ir.actions.act_window_close'}

    def action_create_payments(self):
        """
        To'lov qilingandan keyin:
        1. To'lovni avtomatik tasdiqlash
        2. Delivery ni avtomatik tasdiqlash
        3. Yashil xabar ko'rsatish
        4. Sale Order oynasida qolish
        """
        _logger.info("=" * 80)
        _logger.info("CREATE PAYMENT TUGMASI BOSILDI")
        _logger.info("=" * 80)
        
        # To'lovlarni yaratish
        _logger.info("Creating payments...")
        payments = self._create_payments()
        _logger.info("Payments created | Payment IDs: %s | Count: %s", payments.ids, len(payments))
        
        # Context'dan sale_order_id va purchase_order_id ni olish
        sale_order_id = self._context.get('sale_order_id')
        purchase_order_id = self._context.get('purchase_order_id')
        _logger.info("Sale Order ID from context: %s | Purchase Order ID from context: %s", sale_order_id, purchase_order_id)
        
        # Sale Order uchun ishlash
        if sale_order_id and payments:
            sale_order = self.env['sale.order'].browse(sale_order_id)
            _logger.info("Processing Sale Order | Order ID: %s | State: %s | Name: %s", sale_order.id, sale_order.state, sale_order.name)
            
            # To'lovlarni avtomatik tasdiqlash
            _logger.info("Processing payments | Count: %s", len(payments))
            for payment in payments:
                _logger.info("Processing Payment | Payment ID: %s | State: %s | Amount: %s", payment.id, payment.state, payment.amount)
                
                # To'lovni tasdiqlash (draft -> in_process)
                if payment.state == 'draft':
                    _logger.info("Posting payment | Payment ID: %s", payment.id)
                    payment.action_post()
                    _logger.info("Payment posted | Payment ID: %s | New state: %s", payment.id, payment.state)
                
                # To'lovni to'liq tasdiqlash (in_process -> paid)
                if payment.state == 'in_process':
                    _logger.info("Validating payment | Payment ID: %s", payment.id)
                    payment.action_validate()
                    _logger.info("Payment validated | Payment ID: %s | New state: %s", payment.id, payment.state)
            
            # Delivery ni avtomatik tasdiqlash
            _logger.info("Processing deliveries | Picking IDs: %s | Count: %s", sale_order.picking_ids.ids, len(sale_order.picking_ids))
            if sale_order.picking_ids:
                for picking in sale_order.picking_ids:
                    _logger.info("Processing Picking | Picking ID: %s | State: %s | Name: %s", picking.id, picking.state, picking.name)
                    # State'ni yangilash uchun refresh qilish
                    picking.invalidate_recordset(['state'])
                    picking = self.env['stock.picking'].browse(picking.id)
                    _logger.info("Picking state after refresh | Picking ID: %s | State: %s", picking.id, picking.state)
                    
                    if picking.state == 'draft':
                        _logger.info("Confirming picking | Picking ID: %s", picking.id)
                        try:
                            picking.action_confirm()
                            # State'ni yangilash
                            picking.invalidate_recordset(['state'])
                            picking = self.env['stock.picking'].browse(picking.id)
                            _logger.info("Picking confirmed | Picking ID: %s | New state: %s", picking.id, picking.state)
                        except Exception as e:
                            _logger.error("Error confirming picking | Picking ID: %s | Error: %s", picking.id, str(e))
                            continue
                    
                    # State'ni yana yangilash
                    picking.invalidate_recordset(['state'])
                    picking = self.env['stock.picking'].browse(picking.id)
                    _logger.info("Picking state before assign | Picking ID: %s | State: %s", picking.id, picking.state)
                    
                    if picking.state == 'confirmed':
                        _logger.info("Assigning picking | Picking ID: %s", picking.id)
                        try:
                            picking.action_assign()
                            # State'ni yangilash
                            picking.invalidate_recordset(['state'])
                            picking = self.env['stock.picking'].browse(picking.id)
                            _logger.info("Picking assigned | Picking ID: %s | New state: %s", picking.id, picking.state)
                        except Exception as e:
                            _logger.error("Error assigning picking | Picking ID: %s | Error: %s", picking.id, str(e))
                            # Xatolik bo'lsa ham davom etish
                    
                    # Agar mahsulot omborda yetarli bo'lmasa, "create brokered" (minusga sotish) qilish
                    # Barcha move'lar uchun qty_done ni belgilash
                    for move in picking.move_ids:
                        if not move.move_line_ids:
                            # Agar move_line yo'q bo'lsa, yaratish
                            move._action_assign()
                        
                        # Barcha move_line'lar uchun qty_done ni belgilash
                        # quantity_product_uom - bu reserved qty (product UoM da)
                        total_reserved = sum(move.move_line_ids.mapped('quantity_product_uom'))
                        if total_reserved < move.product_uom_qty:
                            # Agar reserved qty kam bo'lsa, "create brokered" (minusga sotish) qilish
                            # Mavjud move_line'ni yangilash yoki yangi yaratish
                            if move.move_line_ids:
                                # Mavjud move_line'ni yangilash
                                for move_line in move.move_line_ids:
                                    move_line.qty_done = move.product_uom_qty
                            else:
                                # Yangi move_line yaratish
                                self.env['stock.move.line'].create({
                                    'move_id': move.id,
                                    'product_id': move.product_id.id,
                                    'product_uom_id': move.product_uom.id,
                                    'location_id': move.location_id.id,
                                    'location_dest_id': move.location_dest_id.id,
                                    'picking_id': picking.id,
                                    'qty_done': move.product_uom_qty,
                                })
                        else:
                            # Agar reserved qty yetarli bo'lsa, qty_done ni quantity ga tenglashtirish
                            for move_line in move.move_line_ids:
                                # quantity - bu move_line'dagi reserved qty
                                if move_line.quantity > 0:
                                    move_line.qty_done = move_line.quantity
                                else:
                                    move_line.qty_done = move.product_uom_qty
                    
                    # Validate qilish - agar mahsulot yetarli bo'lmasa, "create brokered" (minusga sotish) qilish
                    # State'ni yangilash
                    picking.invalidate_recordset(['state'])
                    picking = self.env['stock.picking'].browse(picking.id)
                    _logger.info("Picking state before validate | Picking ID: %s | State: %s", picking.id, picking.state)
                    
                    if picking.state in ('assigned', 'partially_available', 'waiting', 'confirmed'):
                        _logger.info("Validating picking | Picking ID: %s | State: %s", picking.id, picking.state)
                        try:
                            # Context orqali backorder yaratmaslik va immediate transfer qilish
                            # skip_backorder=True - backorder wizard'ni ochmaslik
                            # cancel_backorder=True - backorder yaratmaslik
                            result = picking.with_context(
                                skip_backorder=True,
                                cancel_backorder=True,
                                skip_sanity_check=True
                            ).button_validate()
                            _logger.info("Picking validated | Picking ID: %s | Result: %s", picking.id, result)
                            
                            # Agar backorder wizard ochilsa, uni yopish va to'g'ridan-to'g'ri validate qilish
                            if result and isinstance(result, dict) and result.get('res_model') == 'stock.backorder.confirmation':
                                _logger.info("Backorder wizard detected, closing and validating directly | Picking ID: %s", picking.id)
                                # Backorder wizard'ni yopish va to'g'ridan-to'g'ri validate qilish
                                picking.with_context(
                                    cancel_backorder=True,
                                    skip_sanity_check=True
                                )._action_done()
                                _logger.info("Picking validated directly | Picking ID: %s | New state: %s", picking.id, picking.state)
                        except Exception as e:
                            _logger.error("Error validating picking | Picking ID: %s | Error: %s", picking.id, str(e))
                            # Xatolik bo'lsa ham davom etish
            
            # Muvaffaqiyatli xabar ko'rsatish va wizard oynasini yopish
            _logger.info("=" * 80)
            _logger.info("BARCHA JARAYONLAR MUVAFFAQIYATLI TUGALLANDI")
            _logger.info("Order ID: %s | Payment IDs: %s | Picking IDs: %s", sale_order.id, payments.ids, sale_order.picking_ids.ids)
            _logger.info("=" * 80)
            
            # Wizard oynasini yopish
            return {
                'type': 'ir.actions.act_window_close',
            }
        
        # Purchase Order uchun ishlash
        if purchase_order_id and payments:
            purchase_order = self.env['purchase.order'].browse(purchase_order_id)
            _logger.info("Processing Purchase Order | Order ID: %s | State: %s | Name: %s", purchase_order.id, purchase_order.state, purchase_order.name)
            
            # To'lovlarni avtomatik tasdiqlash
            _logger.info("Processing payments | Count: %s", len(payments))
            for payment in payments:
                _logger.info("Processing Payment | Payment ID: %s | State: %s | Amount: %s", payment.id, payment.state, payment.amount)
                
                # To'lovni tasdiqlash (draft -> in_process)
                if payment.state == 'draft':
                    _logger.info("Posting payment | Payment ID: %s", payment.id)
                    payment.action_post()
                    _logger.info("Payment posted | Payment ID: %s | New state: %s", payment.id, payment.state)
                
                # To'lovni to'liq tasdiqlash (in_process -> paid)
                if payment.state == 'in_process':
                    _logger.info("Validating payment | Payment ID: %s", payment.id)
                    payment.action_validate()
                    _logger.info("Payment validated | Payment ID: %s | New state: %s", payment.id, payment.state)
            
            # Delivery ni avtomatik tasdiqlash (incoming shipment)
            _logger.info("Processing incoming shipments | Picking IDs: %s | Count: %s", purchase_order.picking_ids.ids, len(purchase_order.picking_ids))
            if purchase_order.picking_ids:
                for picking in purchase_order.picking_ids:
                    _logger.info("Processing Picking | Picking ID: %s | State: %s | Name: %s", picking.id, picking.state, picking.name)
                    # State'ni yangilash uchun refresh qilish
                    picking.invalidate_recordset(['state'])
                    picking = self.env['stock.picking'].browse(picking.id)
                    _logger.info("Picking state after refresh | Picking ID: %s | State: %s", picking.id, picking.state)
                    
                    if picking.state == 'draft':
                        _logger.info("Confirming picking | Picking ID: %s", picking.id)
                        try:
                            picking.action_confirm()
                            # State'ni yangilash
                            picking.invalidate_recordset(['state'])
                            picking = self.env['stock.picking'].browse(picking.id)
                            _logger.info("Picking confirmed | Picking ID: %s | New state: %s", picking.id, picking.state)
                        except Exception as e:
                            _logger.error("Error confirming picking | Picking ID: %s | Error: %s", picking.id, str(e))
                            continue
                    
                    # State'ni yana yangilash
                    picking.invalidate_recordset(['state'])
                    picking = self.env['stock.picking'].browse(picking.id)
                    _logger.info("Picking state before assign | Picking ID: %s | State: %s", picking.id, picking.state)
                    
                    if picking.state == 'confirmed':
                        _logger.info("Assigning picking | Picking ID: %s", picking.id)
                        try:
                            picking.action_assign()
                            # State'ni yangilash
                            picking.invalidate_recordset(['state'])
                            picking = self.env['stock.picking'].browse(picking.id)
                            _logger.info("Picking assigned | Picking ID: %s | New state: %s", picking.id, picking.state)
                        except Exception as e:
                            _logger.error("Error assigning picking | Picking ID: %s | Error: %s", picking.id, str(e))
                            # Xatolik bo'lsa ham davom etish
                    
                    # Barcha move'lar uchun qty_done ni belgilash
                    for move in picking.move_ids:
                        if not move.move_line_ids:
                            # Agar move_line yo'q bo'lsa, yaratish
                            move._action_assign()
                        
                        # Barcha move_line'lar uchun qty_done ni belgilash
                        total_reserved = sum(move.move_line_ids.mapped('quantity_product_uom'))
                        if total_reserved < move.product_uom_qty:
                            # Agar reserved qty kam bo'lsa, qty_done ni product_uom_qty ga tenglashtirish
                            if move.move_line_ids:
                                for move_line in move.move_line_ids:
                                    move_line.qty_done = move.product_uom_qty
                            else:
                                # Yangi move_line yaratish
                                self.env['stock.move.line'].create({
                                    'move_id': move.id,
                                    'product_id': move.product_id.id,
                                    'product_uom_id': move.product_uom.id,
                                    'location_id': move.location_id.id,
                                    'location_dest_id': move.location_dest_id.id,
                                    'picking_id': picking.id,
                                    'qty_done': move.product_uom_qty,
                                })
                        else:
                            # Agar reserved qty yetarli bo'lsa, qty_done ni quantity ga tenglashtirish
                            for move_line in move.move_line_ids:
                                if move_line.quantity > 0:
                                    move_line.qty_done = move_line.quantity
                                else:
                                    move_line.qty_done = move.product_uom_qty
                    
                    # Validate qilish
                    # State'ni yangilash
                    picking.invalidate_recordset(['state'])
                    picking = self.env['stock.picking'].browse(picking.id)
                    _logger.info("Picking state before validate | Picking ID: %s | State: %s", picking.id, picking.state)
                    
                    if picking.state in ('assigned', 'partially_available', 'waiting', 'confirmed'):
                        _logger.info("Validating picking | Picking ID: %s | State: %s", picking.id, picking.state)
                        try:
                            result = picking.with_context(
                                skip_backorder=True,
                                cancel_backorder=True,
                                skip_sanity_check=True
                            ).button_validate()
                            _logger.info("Picking validated | Picking ID: %s | Result: %s", picking.id, result)
                            
                            # Agar backorder wizard yoki SMS wizard ochilsa, uni yopish va to'g'ridan-to'g'ri validate qilish
                            if result and isinstance(result, dict):
                                res_model = result.get('res_model')
                                if res_model == 'stock.backorder.confirmation':
                                    _logger.info("Backorder wizard detected, closing and validating directly | Picking ID: %s", picking.id)
                                    picking.with_context(
                                        cancel_backorder=True,
                                        skip_sanity_check=True
                                    )._action_done()
                                    _logger.info("Picking validated directly | Picking ID: %s | New state: %s", picking.id, picking.state)
                                elif res_model == 'confirm.stock.sms':
                                    _logger.info("SMS confirmation wizard detected, closing and validating directly | Picking ID: %s", picking.id)
                                    # SMS wizard'ni yopish va to'g'ridan-to'g'ri validate qilish
                                    # SMS wizard'ni o'tkazib yuborish uchun to'g'ridan-to'g'ri _action_done() chaqiramiz
                                    picking.with_context(
                                        cancel_backorder=True,
                                        skip_sanity_check=True
                                    )._action_done()
                                    _logger.info("Picking validated directly (SMS skipped) | Picking ID: %s | New state: %s", picking.id, picking.state)
                        except Exception as e:
                            _logger.error("Error validating picking | Picking ID: %s | Error: %s", picking.id, str(e))
                            # Xatolik bo'lsa ham davom etish
            
            # Muvaffaqiyatli xabar ko'rsatish va wizard oynasini yopish
            _logger.info("=" * 80)
            _logger.info("BARCHA JARAYONLAR MUVAFFAQIYATLI TUGALLANDI (PURCHASE)")
            _logger.info("Order ID: %s | Payment IDs: %s | Picking IDs: %s", purchase_order.id, payments.ids, purchase_order.picking_ids.ids)
            _logger.info("=" * 80)
            
            # Wizard oynasini yopish
            return {
                'type': 'ir.actions.act_window_close',
            }
        
        # Agar sale_order_id yoki purchase_order_id bo'lmasa yoki to'lov qilinmagan bo'lsa, odatiy xatti-harakatni qaytarish
        if self._context.get('dont_redirect_to_payments'):
            return True
        
        action = {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'context': {'create': False},
        }
        if len(payments) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': payments.id,
            })
        else:
            action.update({
                'view_mode': 'list,form',
                'domain': [('id', 'in', payments.ids)],
            })
        return action

