from odoo import fields, models


class TrainingRequestRejectWizard(models.TransientModel):
    _name = 'hr.training.request.reject.wizard'
    _description = 'Reject Training Request'

    request_id = fields.Many2one(
        'hr.training.request', string='Request', required=True,
        ondelete='cascade')
    reason = fields.Text(string='Reason', required=True)

    def action_confirm(self):
        self.ensure_one()
        self.request_id._apply_rejection(self.reason)
        return {'type': 'ir.actions.act_window_close'}
