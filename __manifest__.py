{
    'name': 'HR Training Request',
    'version': '17.0.1.0.0',
    'summary': 'Employee training requests with a manager and HR approval workflow',
    'description': """
Lets employees request external training or certifications and routes each
request through a role-gated manager and HR approval workflow. Access is
enforced with record rules, access rights and server-side state guards.
""",
    'author': 'Assignment Candidate',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': ['hr', 'mail'],
    'data': [
        # Security first: the CSV below references the groups it defines.
        'security/hr_training_request_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'views/hr_training_request_views.xml',
        'views/hr_training_request_reject_wizard_views.xml',
        'views/hr_training_request_menus.xml',
        'views/hr_employee_views.xml',
    ],
    'demo': [
        'demo/hr_training_request_demo.xml',
    ],
    'application': True,
    'installable': True,
}
