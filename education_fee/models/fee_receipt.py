# -*- coding: utf-8 -*-

import datetime
from odoo import models, fields, api, _


class FeeReceipts(models.Model):
    _inherit = 'account.invoice'

    student_id = fields.Many2one('education.student', string='Admission No')
    student_name = fields.Char(string='Name', related='student_id.partner_id.name', store=True)
    class_division_id = fields.Many2one('education.class.division', string='Class')
    fee_structure = fields.Many2one('education.fee.structure', string='Fee Structure')
    is_fee = fields.Boolean(string='Is Fee', store=True, default=False)
    from_month=fields.Many2one('education.academic.month','From')
    till_month=fields.Many2one('education.academic.month','Till')
    fee_category_id = fields.Many2one('education.fee.category', string='Category', required=True,
                                      default=lambda self: self.env['education.fee.category'].search([], limit=1))
    is_fee_structure = fields.Boolean('Have a fee structure?', related='fee_category_id.fee_structure')
    payed_line_ids = fields.One2many('payed.lines', 'partner_id', string='Payments Done',
                                     readonly=True, store=False)
    payed_from_date = fields.Date(string='From Date')
    payed_to_date = fields.Date(string='To Date')


    @api.onchange('fee_structure')
    def _get_fee_lines(self):
        """Set default fee lines based on selected fee structure"""
        lines = []
        for item in self:
            for line in item.fee_structure.fee_type_ids:
                name = line.fee_type.product_id.description_sale
                if not name:
                    name = line.fee_type.product_id.name
                # Todo here to implement logic for students last invoiced fees
                # search last invoice for the lin and take the paid_upto
                fee_type_last_paid=self.env['account.invoice.line'].search([('invoice_id.student_id','=',item.student_id.id),
                                                                            ('product_id','=',line.fee_type.product_id.id)],order='invoice_id asc', limit=1)
                if len(fee_type_last_paid)==0:
                    #Here to set feetype started from
                    fee_type_paid_upto = '2018-12-31'
                    ##fee_type_paid_upto= the date of fee_type started
                else:
                    fee_type_paid_upto=fee_type_last_paid.paid_upto

                duration_in_month = 0
                qty=0
                #todo calculate number of fee_type unit to invooice
                if line.fee_type.payment_type==0:
                    if len(fee_type_last_paid)==0:
                        qty=1

                else:
                    duration_in_month=len(self.env['education.academic.month'].search([('start_date','>',fee_type_paid_upto),
                                                                                         ('end_date','<=',item.till_month.end_date)]))

                    qty=duration_in_month//line.fee_type.payment_type

                    # if (duration_in_month%line.fee_type.payment_type)>0 :
                    #     qty=qty+1
                last_paid_month=self.env['education.academic.month'].search([('end_date','=',datetime.datetime.strptime(fee_type_paid_upto,'%Y-%m-%d'))])
                new_paid_upto=self.env['education.academic.month'].search([('id','=',last_paid_month.id+qty*line.fee_type.payment_type)]).end_date

                if qty>0:
                    # and rate applicable for students
                    fee_line = {
                        'price_unit': line.fee_amount,
                        'quantity': qty,
                        'product_id': line.fee_type.product_id,
                        'name': name,
                        'paid_upto': new_paid_upto,
                        'account_id': item.journal_id.default_debit_account_id
                    }
                    lines.append((0, 0, fee_line))
            item.invoice_line_ids = lines

    @api.onchange('student_id', 'fee_category_id', 'payed_from_date', 'payed_to_date')
    def _get_partner_details(self):
        """Student_id is inherited from res_partner. Set partner_id from student_id """
        self.ensure_one()
        lines = []
        for item in self:
            item.invoice_line_ids = lines
            item.partner_id = item.student_id.partner_id
            item.class_division_id = item.student_id.class_id
            date_today = datetime.date.today()
            company = self.env.user.company_id
            from_date = item.payed_from_date
            to_date = item.payed_to_date
            if not from_date:
                from_date = company.compute_fiscalyear_dates(date_today)['date_from']
            if not to_date:
                to_date = date_today
            if item.partner_id and item.fee_category_id:
                invoice_ids = self.env['account.invoice'].search([('partner_id', '=', item.partner_id.id),
                                                                  ('date_invoice', '>=', from_date),
                                                                  ('date_invoice', '<=', to_date),
                                                                  ('fee_category_id', '=', item.fee_category_id.id)])
                invoice_line_list = []
                for invoice in invoice_ids:
                    for line in invoice.invoice_line_ids:
                        fee_line = {
                            'price_unit': line.price_unit,
                            'quantity': line.quantity,
                            'product_id': line.product_id,
                            'price_subtotal': line.price_subtotal,
                            'invoice_line_tax_ids': line.invoice_line_tax_ids,
                            'discount': line.discount,
                            'date': line.invoice_id.date_invoice,
                            'receipt_no': line.invoice_id.number
                        }
                        invoice_line_list.append((0, 0, fee_line))
                item.payed_line_ids = invoice_line_list

    @api.onchange('student_id')
    def student_id_onchange(self):
        for rec in self:
            if rec.student_id:
                last_invoice=self.env['account.invoice'].search([('student_id','=',rec.student_id.id)],order="id desc",limit=1)
                rec.from_month=(last_invoice.till_month.id+1)
                rec.till_month=rec.from_month

    @api.onchange('fee_category_id')
    def _get_fee_structure(self):
        """ Set domain for fee structure based on category"""
        self.journal_id = self.fee_category_id.journal_id
        self.invoice_line_ids = None
        return {
            'domain': {
                'fee_structure': [('category_id', '=', self.fee_category_id.id)]
            }
        }


    @api.model
    def create(self, vals):
        """ Adding two field to invoice. is_fee use to display fee items only in fee tree view"""
        partner_id = self.env['res.partner'].browse(vals['partner_id'])
        vals.update({
            'is_fee': True,
            'student_name': partner_id.name
        })
        res = super(FeeReceipts, self).create(vals)
        return res


class InvoiceLineInherit(models.Model):
    _inherit = 'account.invoice.line'
    paid_upto=fields.Date("Paid Upto")

    @api.onchange('product_id')
    def _get_category_domain(self):
        """Set domain for invoice lines depend on selected category"""
        if self.invoice_id.fee_category_id:
            fee_types = self.env['education.fee.type'].search([('category_id', '=',  self.invoice_id.fee_category_id.id)])
            fee_list = []
            for fee in fee_types:
                fee_list.append(fee.product_id.id)
            vals = {
                'domain': {
                    'product_id': [('id', 'in', tuple(fee_list))]
                }
            }
            return vals


class PayedLinens(models.Model):
    _name = 'payed.lines'
    _inherit = 'account.invoice.line'

    date = fields.Date(string='Date', readonly=True)
    receipt_no = fields.Char('Receipt No')
