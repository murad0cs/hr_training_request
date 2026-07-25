from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestHrTrainingRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = new_test_user(
            cls.env, login='ttr_emp',
            groups='hr_training_request.group_training_requester')
        cls.manager = new_test_user(
            cls.env, login='ttr_mgr',
            groups='hr_training_request.group_training_manager_approver')
        cls.hr = new_test_user(
            cls.env, login='ttr_hr',
            groups='hr_training_request.group_training_hr_approver')
        cls.outsider = new_test_user(
            cls.env, login='ttr_out',
            groups='hr_training_request.group_training_requester')

        employee_model = cls.env['hr.employee']
        cls.manager_emp = employee_model.create({
            'name': 'Manager', 'user_id': cls.manager.id})
        cls.employee_emp = employee_model.create({
            'name': 'Employee', 'user_id': cls.requester.id,
            'parent_id': cls.manager_emp.id})
        cls.outsider_emp = employee_model.create({
            'name': 'Outsider', 'user_id': cls.outsider.id})

    def _create(self, user=None, **values):
        user = user or self.requester
        vals = {'course_name': 'Test course', 'employee_id': self.employee_emp.id}
        vals.update(values)
        return self.env['hr.training.request'].with_user(user).create(vals)

    def _submitted(self):
        request = self._create()
        request.with_user(self.requester).action_submit()
        return request

    def _manager_approved(self):
        request = self._submitted()
        request.with_user(self.manager).action_manager_approve()
        return request

    # State transitions ------------------------------------------------

    def test_owner_submits(self):
        request = self._create()
        request.with_user(self.requester).action_submit()
        self.assertEqual(request.state, 'submitted')

    def test_non_owner_cannot_submit(self):
        request = self._create()
        with self.assertRaises(AccessError):
            request.with_user(self.manager).action_submit()

    def test_manager_approves(self):
        request = self._submitted()
        request.with_user(self.manager).action_manager_approve()
        self.assertEqual(request.state, 'manager_approved')

    def test_owner_cannot_manager_approve(self):
        request = self._submitted()
        with self.assertRaises(AccessError):
            request.with_user(self.requester).action_manager_approve()

    def test_hr_final_approves(self):
        request = self._manager_approved()
        request.with_user(self.hr).action_hr_approve()
        self.assertEqual(request.state, 'hr_approved')

    def test_manager_cannot_hr_approve(self):
        request = self._manager_approved()
        with self.assertRaises(AccessError):
            request.with_user(self.manager).action_hr_approve()

    def test_manager_rejects(self):
        request = self._submitted()
        request.with_user(self.manager).action_manager_reject()
        self.assertEqual(request.state, 'rejected')

    def test_hr_rejects(self):
        request = self._manager_approved()
        request.with_user(self.hr).action_hr_reject()
        self.assertEqual(request.state, 'rejected')

    def test_owner_cancels(self):
        request = self._create()
        request.with_user(self.requester).action_cancel()
        self.assertEqual(request.state, 'cancelled')

    def test_cannot_cancel_after_manager_approval(self):
        request = self._manager_approved()
        with self.assertRaises(ValidationError):
            request.with_user(self.requester).action_cancel()

    def test_illegal_jump_is_blocked(self):
        request = self._create()
        with self.assertRaises(ValidationError):
            request.with_user(self.requester).write({'state': 'hr_approved'})

    # Record rules -----------------------------------------------------

    def test_record_rule_visibility(self):
        request = self._create()
        model = self.env['hr.training.request']
        self.assertTrue(model.with_user(self.requester).search([('id', '=', request.id)]))
        self.assertFalse(model.with_user(self.outsider).search([('id', '=', request.id)]))
        self.assertTrue(model.with_user(self.manager).search([('id', '=', request.id)]))
        self.assertTrue(model.with_user(self.hr).search([('id', '=', request.id)]))

    # Field-level access -----------------------------------------------

    def test_hr_notes_hidden_from_non_hr(self):
        model = self.env['hr.training.request']
        self.assertNotIn('hr_notes', model.with_user(self.requester).fields_get())
        self.assertNotIn('hr_notes', model.with_user(self.manager).fields_get())
        self.assertIn('hr_notes', model.with_user(self.hr).fields_get())

    # Validation -------------------------------------------------------

    def test_negative_cost_rejected(self):
        with self.assertRaises(ValidationError):
            self._create(cost=-10)

    def test_end_before_start_rejected(self):
        with self.assertRaises(ValidationError):
            self._create(start_date='2026-05-10', end_date='2026-05-01')

    def test_same_day_allowed(self):
        request = self._create(start_date='2026-05-10', end_date='2026-05-10')
        self.assertTrue(request)

    # Misc -------------------------------------------------------------

    def test_reference_is_sequenced(self):
        request = self._create()
        self.assertTrue(request.name.startswith('TR'))

    def test_smart_button_count_respects_rules(self):
        self._create()
        self._create()
        as_manager = self.employee_emp.with_user(self.manager)
        self.assertEqual(as_manager.training_request_count, 2)
        as_outsider = self.employee_emp.with_user(self.outsider)
        self.assertEqual(as_outsider.training_request_count, 0)
