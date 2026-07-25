from odoo import api, fields, models, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    training_request_ids = fields.One2many(
        'hr.training.request', 'employee_id', string='Training Requests')
    training_request_count = fields.Integer(
        string='Training Request Count',
        compute='_compute_training_request_count')

    # depends_context('uid') keys the cache per user, so the count is
    # recomputed for each viewer instead of being shared within a transaction.
    @api.depends_context('uid')
    def _compute_training_request_count(self):
        # read_group runs as the current user, so the count already honours the
        # record rules: a viewer only counts requests they are allowed to see.
        if not self.env.user.has_group(
                'hr_training_request.group_training_requester'):
            self.training_request_count = 0
            return
        grouped = self.env['hr.training.request'].read_group(
            [('employee_id', 'in', self.ids)],
            ['employee_id'],
            ['employee_id'],
        )
        counts = {
            row['employee_id'][0]: row['employee_id_count'] for row in grouped
        }
        for employee in self:
            employee.training_request_count = counts.get(employee.id, 0)

    def action_open_training_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Training Requests'),
            'res_model': 'hr.training.request',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
