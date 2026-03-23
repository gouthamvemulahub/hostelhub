from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = 'Creates the Warden group with appropriate permissions'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Username for warden account')
        parser.add_argument('--password', type=str, help='Password for warden account')
        parser.add_argument('--email',    type=str, help='Email for warden account', default='')

    def handle(self, *args, **options):
        # Create Warden group
        group, created = Group.objects.get_or_create(name='Warden')
        if created:
            self.stdout.write('✅ Warden group created')
        else:
            self.stdout.write('ℹ️  Warden group already exists')

        # Define warden permissions
        warden_perms = [
            ('hostelapp', 'studentprofile',  'view'),
            ('hostelapp', 'room',            'view'),
            ('hostelapp', 'roomallotment',   'view'),
            ('hostelapp', 'complaint',       'view'),
            ('hostelapp', 'complaint',       'change'),
            ('hostelapp', 'notice',          'view'),
            ('hostelapp', 'notice',          'add'),
            ('hostelapp', 'notice',          'change'),
            ('hostelapp', 'attendance',      'view'),
            ('hostelapp', 'attendance',      'add'),
            ('hostelapp', 'attendance',      'change'),
            ('hostelapp', 'leaverequest',    'view'),
            ('hostelapp', 'leaverequest',    'change'),
            ('hostelapp', 'feepayment',      'view'),
            ('hostelapp', 'message',         'view'),
            ('hostelapp', 'message',         'add'),
        ]

        group.permissions.clear()
        for app, model, action in warden_perms:
            try:
                ct   = ContentType.objects.get(app_label=app, model=model)
                perm = Permission.objects.get(content_type=ct, codename=f'{action}_{model}')
                group.permissions.add(perm)
            except Exception as e:
                self.stdout.write(f'⚠️  Could not add {action}_{model}: {e}')

        self.stdout.write(f'✅ {group.permissions.count()} permissions assigned to Warden group')

        # Create warden user if provided
        username = options.get('username')
        password = options.get('password')
        if username and password:
            email = options.get('email', '')
            user, created = User.objects.get_or_create(username=username, defaults={'email': email, 'is_staff': True})
            if created:
                user.set_password(password)
                user.is_staff = True
                user.save()
                self.stdout.write(f'✅ Warden user "{username}" created')
            else:
                self.stdout.write(f'ℹ️  User "{username}" already exists')
            user.groups.add(group)
            self.stdout.write(f'✅ User "{username}" added to Warden group')

        self.stdout.write('\n🎉 Warden setup complete!')
        self.stdout.write('Run: python3 manage.py setup_warden --username warden1 --password warden123')