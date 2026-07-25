from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class HrTrainingRequest(models.Model):
    _name = 'hr.training.request'
    _description = 'Training Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    # Allowed target states per source state. Anything not listed here is an
    # illegal transition and is refused in write().
    _TRANSITIONS = {
        'draft': {'submitted', 'cancelled'},
        'submitted': {'manager_approved', 'rejected', 'cancelled'},
        'manager_approved': {'hr_approved', 'rejected'},
        'hr_approved': set(),
        'rejected': set(),
        'cancelled': set(),
    }

    name = fields.Char(
        string='Reference', default='New', copy=False, readonly=True,
        required=True, index=True)

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, tracking=True,
        index=True, ondelete='restrict',
        default=lambda self: self.env.user.employee_id)
    manager_id = fields.Many2one(
        'hr.employee', string='Manager', related='employee_id.parent_id',
        store=True, readonly=True)

    course_name = fields.Char(string='Course Name', required=True, tracking=True)
    training_provider = fields.Char(string='Training Provider')
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')

    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        ondelete='restrict', default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True)
    cost = fields.Monetary(
        string='Cost', currency_field='currency_id', tracking=True)

    justification = fields.Text(string='Description')

    # Field-level groups: the ORM removes this field from reads and writes for
    # anyone outside the HR approver group, so it stays hidden over RPC too.
    hr_notes = fields.Text(
        string='Internal HR Notes',
        groups='hr_training_request.group_training_hr_approver')

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('manager_approved', 'Manager Approved'),
            ('hr_approved', 'HR Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', required=True, tracking=True,
        copy=False, index=True)

    rejection_reason = fields.Text(
        string='Rejection Reason', readonly=True, copy=False, tracking=True)

    # These drive button visibility in the form. They reuse the same role
    # checks as the write() guard, so the UI and the server never disagree.
    can_submit = fields.Boolean(compute='_compute_permissions')
    can_cancel = fields.Boolean(compute='_compute_permissions')
    can_manager_review = fields.Boolean(compute='_compute_permissions')
    can_hr_review = fields.Boolean(compute='_compute_permissions')

    # depends_context('uid') keys the cache per user, so button visibility is
    # evaluated for the current user rather than shared within a transaction.
    @api.depends('state', 'employee_id', 'manager_id', 'create_uid')
    @api.depends_context('uid')
    def _compute_permissions(self):
        for request in self:
            request.can_submit = (
                request.state == 'draft' and request._is_owner())
            request.can_cancel = (
                request.state in ('draft', 'submitted') and request._is_owner())
            request.can_manager_review = (
                request.state == 'submitted' and request._is_manager())
            request.can_hr_review = (
                request.state == 'manager_approved' and request._is_hr_approver())

    def _is_owner(self):
        self.ensure_one()
        user = self.env.user
        return self.employee_id.user_id == user or self.create_uid == user

    def _is_manager(self):
        self.ensure_one()
        return (
            self.env.user.has_group(
                'hr_training_request.group_training_manager_approver')
            and self.manager_id.user_id == self.env.user)

    def _is_hr_approver(self):
        return self.env.user.has_group(
            'hr_training_request.group_training_hr_approver')

    @api.constrains('cost')
    def _check_cost(self):
        for request in self:
            if request.cost and request.cost < 0:
                raise ValidationError(_("Cost cannot be negative."))

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for request in self:
            if (request.start_date and request.end_date
                    and request.end_date < request.start_date):
                raise ValidationError(
                    _("End date must be on or after the start date."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hr.training.request') or 'New'
        return super().create(vals_list)

    def write(self, vals):
        # Every state change is validated here, so no illegal or unauthorised
        # transition can slip through the UI, RPC or the shell.
        if 'state' in vals:
            for request in self:
                request._check_transition(vals['state'])
        return super().write(vals)

    def _check_transition(self, new_state):
        self.ensure_one()
        if new_state == self.state:
            return

        if new_state not in self._TRANSITIONS.get(self.state, ()):
            raise ValidationError(
                _("Cannot move a request from '%s' to '%s'.")
                % (self.state, new_state))

        if new_state == 'submitted':
            if not self._is_owner():
                raise AccessError(_("Only the requester can submit this request."))
        elif new_state == 'cancelled':
            if not self._is_owner():
                raise AccessError(_("Only the requester can cancel this request."))
        elif new_state == 'manager_approved':
            if not self._is_manager():
                raise AccessError(
                    _("Only the employee's manager can approve at this stage."))
        elif new_state == 'hr_approved':
            if not self._is_hr_approver():
                raise AccessError(_("Only HR can give final approval."))
        elif new_state == 'rejected':
            # A rejection can come from the manager (submitted) or from HR
            # (manager_approved); each stage requires its own role.
            if self.state == 'submitted' and not self._is_manager():
                raise AccessError(
                    _("Only the employee's manager can reject at this stage."))
            if self.state == 'manager_approved' and not self._is_hr_approver():
                raise AccessError(_("Only HR can reject at this stage."))

    # Activity used to push the request to the next approver's inbox.
    _APPROVAL_ACTIVITY = 'mail.mail_activity_data_todo'

    def _schedule_review_activity(self, user):
        if user:
            self.activity_schedule(
                self._APPROVAL_ACTIVITY, user_id=user.id,
                summary=_("Training request to review"))

    def _clear_review_activities(self):
        self.activity_unlink([self._APPROVAL_ACTIVITY])

    def _hr_approver_users(self):
        # sudo() is used only to look up who belongs to the HR approver group so
        # we can notify them. It reads group membership; it does not bypass any
        # access rule on the training request itself.
        group = self.env.ref('hr_training_request.group_training_hr_approver')
        return group.sudo().users.filtered('active')

    def _notify_requester(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            return
        for request in self:
            if request.employee_id.user_id:
                template.send_mail(request.id, force_send=False)

    def action_submit(self):
        self.write({'state': 'submitted'})
        self.message_post(body=_("Submitted for manager approval."))
        for request in self:
            request._schedule_review_activity(request.manager_id.user_id)
        return True

    def action_manager_approve(self):
        self.write({'state': 'manager_approved'})
        self.message_post(body=_("Approved by manager."))
        for request in self:
            request._clear_review_activities()
            for hr_user in request._hr_approver_users():
                request._schedule_review_activity(hr_user)
        return True

    def action_hr_approve(self):
        self.write({'state': 'hr_approved'})
        self._clear_review_activities()
        self.message_post(body=_("Final approval granted by HR."))
        self._notify_requester('hr_training_request.mail_template_training_approved')
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        self._clear_review_activities()
        self.message_post(body=_("Cancelled by the requester."))
        return True

    # Rejections capture a mandatory reason, so both reject buttons open the
    # wizard rather than rejecting straight away.
    def action_manager_reject(self):
        return self._open_reject_wizard()

    def action_hr_reject(self):
        return self._open_reject_wizard()

    def _open_reject_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Reject Request"),
            'res_model': 'hr.training.request.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    def _apply_rejection(self, reason):
        self.ensure_one()
        # write() re-checks the role for the current stage, so only the manager
        # (at submitted) or HR (at manager_approved) can actually reject.
        self.write({'state': 'rejected', 'rejection_reason': reason})
        self._clear_review_activities()
        self.message_post(body=_("Rejected. Reason: %s") % reason)
        self._notify_requester('hr_training_request.mail_template_training_rejected')
        return True
