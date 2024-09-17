from odoo import models, fields, api, exceptions
import logging

_logger = logging.getLogger(__name__)


class VendorTransaction(models.Model):
    _name = 'idil.vendor_transaction'
    _description = 'Vendor Transaction'

    order_number = fields.Char(string='Order Number')
    transaction_number = fields.Char(string='Transaction Number')
    transaction_date = fields.Date(string='Transaction Date', default=lambda self: fields.Date.today())

    vendor_id = fields.Many2one('idil.vendor.registration', string='Vendor', ondelete='restrict', required=True)
    vendor_name = fields.Char(related='vendor_id.name', string='Vendor Name', readonly=True)
    vendor_phone = fields.Char(related='vendor_id.phone', string='Vendor Phone', readonly=True)
    vendor_email = fields.Char(related='vendor_id.email', string='Vendor Email', readonly=True)

    amount = fields.Float(string='Transaction Amount', store=True)
    paid_amount = fields.Float(string='Paid Amount', store=True)
    remaining_amount = fields.Float(string='Due Amount', store=True)
    amount_paying = fields.Float(string='Amount Paying', store=True)

    cheque_no = fields.Char(string='Cheque No')

    payment_method = fields.Selection(
        [('cash', 'Cash'), ('ap', 'A/P'), ('bank_transfer', 'Bank Transfer'), ('other', 'Other'),
         ('internal', 'Internal')],
        string='Payment Method'
    )
    payment_status = fields.Selection(
        [('pending', 'Pending'), ('paid', 'Paid'), ('partial_paid', 'Partial Paid')],
        string='Payment Status',
        help='Description or additional information about the payment status.'
    )

    reffno = fields.Char(string='Reference Number')

    cash_account_id = fields.Many2one(
        'idil.chart.account',
        string='Cash Account',
        domain=[('account_type', '=', 'cash')],
        help="Select the cash account for transactions."
    )

    transaction_booking_id = fields.Many2one(
        'idil.transaction_booking', string='Transaction Booking', ondelete='cascade'
    )
    payment_ids = fields.One2many('idil.vendor_payment', 'vendor_transaction_id', string='Vendor Payments')

    def write(self, vals):
        for record in self:
            if 'amount_paying' in vals:
                _logger.debug(f"Validating cash account for record {record.id}")
                cash_account_id = vals.get('cash_account_id', record.cash_account_id.id)
                if not cash_account_id:
                    raise exceptions.ValidationError("Please select a cash account before updating the paid amount.")
                if not record._check_cash_account_balance(cash_account_id, vals.get('amount_paying', 0)):
                    raise exceptions.ValidationError("The cash account balance is not enough to cover the paid amount.")

        res = super(VendorTransaction, self).write(vals)

        for record in self:
            if 'amount_paying' in vals:
                payment_id = record._create_vendor_payment(vals['amount_paying'])
                record._update_booking_payment(vals['amount_paying'], payment_id)

        return res

    def _check_cash_account_balance(self, cash_account_id, paid_amount):
        _logger.debug(f"Checking cash account balance for record {self.id}")
        total_debit = sum(self.env['idil.transaction_bookingline'].search(
            [('account_number', '=', cash_account_id), ('transaction_type', '=', 'dr')]).mapped('dr_amount'))
        total_credit = sum(self.env['idil.transaction_bookingline'].search(
            [('account_number', '=', cash_account_id), ('transaction_type', '=', 'cr')]).mapped('cr_amount'))
        available_balance = total_debit - total_credit
        _logger.debug(f"Available balance: {available_balance}, Paid amount: {paid_amount}")
        return available_balance >= paid_amount

    def _update_booking_payment(self, new_paid_amount, payment_id):
        if self.transaction_booking_id:
            previous_paid_amount = self.transaction_booking_id.amount_paid
            updated_paid_amount = previous_paid_amount + new_paid_amount
            # self.transaction_booking_id.amount_paid = updated_paid_amount

            remaining_amount = self.transaction_booking_id.amount - updated_paid_amount
            # self.transaction_booking_id.remaining_amount = remaining_amount
            self.transaction_booking_id.write({
                'amount_paid': updated_paid_amount,
                'remaining_amount': self.transaction_booking_id.amount - updated_paid_amount
            })

            # Use vendor's account payable for the debit transaction
            account_payable_id = self.vendor_id.account_payable_id.id

            # Create the debit line
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': self.transaction_booking_id.id,
                'account_number': account_payable_id,
                'transaction_type': 'dr',
                'dr_amount': new_paid_amount,
                'cr_amount': 0,
                'transaction_date': fields.Date.today(),
                'vendor_payment_id': payment_id
            })

            # Create the credit line
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': self.transaction_booking_id.id,
                'account_number': self.cash_account_id.id,
                'transaction_type': 'cr',
                'cr_amount': new_paid_amount,
                'dr_amount': 0,
                'transaction_date': fields.Date.today(),
                'vendor_payment_id': payment_id
            })

            # Recompute remaining amount after booking lines are created
            existing_payments = sum(self.env['idil.transaction_bookingline'].search([
                ('transaction_booking_id', '=', self.transaction_booking_id.id),
                ('order_line', '=', None)  # Check if order_line is null
            ]).mapped('dr_amount'))
            _logger.debug(
                f"Existing payments: {existing_payments}, Paid amount: {self.paid_amount}, Amount: {self.amount_paying}")
            self.remaining_amount = self.amount - (existing_payments)
            self.paid_amount = existing_payments

            if remaining_amount == 0:
                self.transaction_booking_id.payment_status = 'paid'
                self.payment_status = 'paid'
            elif updated_paid_amount == 0:
                self.transaction_booking_id.payment_status = 'pending'
                self.payment_status = 'pending'
            else:
                self.transaction_booking_id.payment_status = 'partial_paid'
                self.payment_status = 'partial_paid'

    def _create_vendor_payment(self, amount_paid):
        # Check if a payment with the same cheque_no already exists
        existing_payment = self.env['idil.vendor_payment'].search([('cheque_no', '=', self.cheque_no)])
        if existing_payment:
            raise exceptions.ValidationError(
                f"A payment with cheque number '{self.cheque_no}' already exists. Please use a unique cheque number.")

        vendor_payment = self.env['idil.vendor_payment'].create({
            'vendor_id': self.vendor_id.id,
            'vendor_transaction_id': self.id,
            'amount_paid': amount_paid,
            'cheque_no': self.cheque_no,
        })
        return vendor_payment.id
