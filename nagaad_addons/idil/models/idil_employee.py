from datetime import date

from odoo import models, fields, api


class IdilEmployee(models.Model):
    _name = 'idil.employee'
    _description = 'Employee'
    _order = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True)
    department_id = fields.Many2one('idil.employee_department')

    private_phone = fields.Char(string='Private Phone')
    private_email = fields.Char(string='Private Email')
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string='Gender')
    marital = fields.Selection([
        ('single', 'Single'),
        ('married', 'Married'),
        ('cohabitant', 'Legal Cohabitant'),
        ('widower', 'Widower'),
        ('divorced', 'Divorced')
    ], string='Marital Status')
    employee_type = fields.Selection([
        ('employee', 'Employee'),
        ('student', 'Student'),
        ('trainee', 'Trainee'),
        ('contractor', 'Contractor'),
        ('freelance', 'Freelancer')
    ], string='Employee Type')
    pin = fields.Char(string='PIN', copy=False,
                      help='PIN used to Check In/Out in the Kiosk Mode of the Attendance application '
                           '(if enabled in Configuration) and to change the cashier in the Point of Sale application.')
    image_1920 = fields.Image(string="Image", max_width=1920, max_height=1920)

    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.company.currency_id)

    account_id = fields.Many2one('idil.chart.account', string='Commission Account',
                                 domain="[('account_type', 'like', 'commission'), ('code', 'like', '2%'), "
                                        "('currency_id', '=', currency_id)]"
                                 )

    commission = fields.Float(string='Commission Percentage')

    # Salary and bonus information
    salary = fields.Monetary(string='Basic Salary', currency_field='currency_id')
    bonus = fields.Monetary(string='Bonus', currency_field='currency_id')
    total_compensation = fields.Monetary(string='Total Compensation', compute='_compute_total_compensation',
                                         currency_field='currency_id', store=True)
    # Contract details
    contract_start_date = fields.Date(string='Contract Start Date')
    contract_end_date = fields.Date(string='Contract End Date')
    contract_type = fields.Selection([
        ('permanent', 'Permanent'),
        ('temporary', 'Temporary'),
        ('internship', 'Internship'),
        ('freelance', 'Freelance')
    ], string='Contract Type')

    # Leaves and attendance
    leave_balance = fields.Float(string='Leave Balance', defualt=100.0)
    maker_checker = fields.Boolean(string='Maker & Checker', default=False)
    salary_history_ids = fields.One2many(
        'idil.employee.salary',
        'employee_id',
        string="Salary History"
    )

    advance_history_ids = fields.One2many(
        'idil.employee.salary.advance',
        'employee_id',
        string="Advance History"
    )
    # Status field
    status = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ], string='Status', compute='_compute_status', store=True)

    @api.depends('contract_end_date')
    def _compute_status(self):
        today = date.today()
        for record in self:
            if record.contract_end_date and record.contract_end_date < today:
                record.status = 'inactive'
            elif not record.contract_end_date and record.contract_start_date:
                record.status = 'inactive'
            else:
                record.status = 'active'

    @api.depends('salary', 'bonus')
    def _compute_total_compensation(self):
        for record in self:
            record.total_compensation = (record.salary or 0.0) + (record.bonus or 0.0)

    @api.onchange('currency_id')
    def _onchange_currency_id(self):
        """Updates the domain for account_id based on the selected currency."""
        for employee in self:
            if employee.currency_id:
                return {
                    'domain': {
                        'account_id': [
                            ('account_type', 'like', 'commission'),
                            ('code', 'like', '2%'),
                            ('currency_id', '=', employee.currency_id.id)
                        ]
                    }
                }
            else:
                return {
                    'domain': {
                        'account_id': [
                            ('account_type', 'like', 'commission'),
                            ('code', 'like', '2%')
                        ]
                    }
                }

    @api.model
    def create(self, vals):
        # Create the record in idil.employee
        record = super(IdilEmployee, self).create(vals)
        # Create the same record in hr.employee
        self.env['hr.employee'].create({
            'name': record.name,
            'company_id': record.company_id.id,
            'private_phone': record.private_phone,
            'private_email': record.private_email,
            'gender': record.gender,
            'marital': record.marital,
            'employee_type': record.employee_type,
            'pin': record.pin,
            'image_1920': record.image_1920,

        })
        return record

    def write(self, vals):
        # Update the record in idil.employee
        res = super(IdilEmployee, self).write(vals)
        # Update the same record in hr.employee
        for record in self:
            hr_employee = self.env['hr.employee'].search([('name', '=', record.name)])
            if hr_employee:
                hr_employee.write({
                    'name': vals.get('name', record.name),
                    'company_id': vals.get('company_id', record.company_id.id),
                    'private_phone': vals.get('private_phone', record.private_phone),
                    'private_email': vals.get('private_email', record.private_email),
                    'gender': vals.get('gender', record.gender),
                    'marital': vals.get('marital', record.marital),
                    'employee_type': vals.get('employee_type', record.employee_type),
                    'pin': vals.get('pin', record.pin),
                    'image_1920': record.image_1920,

                })
        return res


class IdilEmployeeDepartment(models.Model):
    _name = 'idil.employee_department'
    _description = 'Employee Department'
    _order = 'name'

    name = fields.Char(required=True)
